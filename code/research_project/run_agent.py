"""Run the real JiuwenSwarm PAPER service with the frozen reasoning study."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import inspect
import json
import os
import sys
import time
from decimal import Decimal
from pathlib import Path

import httpx
from openjiuwen.core.foundation.llm import Model
from openjiuwen.core.foundation.llm.schema.config import ModelClientConfig, ModelRequestConfig
from jiuwenswarm.agents.harness.common.rsi import build_rsi_service_context
from jiuwenswarm.agents.harness.common.rsi.paper_provider import PaperProvider
from jiuwenswarm.agents.harness.common.rsi.iclr_reporting import IclrReportingAgent


async def run(args):
    started = time.perf_counter()
    with httpx.Client(timeout=5) as client:
        health = client.get("http://127.0.0.1:19081/health").raise_for_status().json()
    authorized_control_limit = Decimal(os.environ.get("RSI_AUTHORIZED_CONTROL_BUDGET_CNY", "40"))
    if health["model"] != "deepseek-flash" or Decimal(health["budget_cny"]) > authorized_control_limit:
        raise RuntimeError("The shared proxy exceeds the explicitly authorized control limit")
    if float(health["remaining_cny"]) < 2.359296:
        raise RuntimeError("Insufficient remaining budget for a safe worst-case reservation")
    # Windows service PATH may contain inaccessible WindowsApps directories;
    # upstream LaTeX discovery calls Path.is_dir() on every entry.
    host_paths = [entry for entry in os.environ["PATH"].split(os.pathsep)
                  if entry and os.path.isdir(entry)]
    os.environ["PATH"] = os.pathsep.join([str(Path(sys.executable).parent), *host_paths])
    os.environ["PYTHONIOENCODING"] = "utf-8"
    os.environ["JIUWENSWARM_HOME"] = str(args.tasks_root.parent / "runtime-home")
    model = Model(
        model_client_config=ModelClientConfig(
            client_provider="OpenAI", api_key="local", api_base="http://127.0.0.1:19081/v1",
            timeout=300, max_retries=0,
        ),
        model_config=ModelRequestConfig(
            model="deepseek-flash", temperature=0, max_tokens=16384,
            extra_body={"thinking": {"type": "disabled"}},
        ),
    )
    context = build_rsi_service_context(args.tasks_root)
    provider = PaperProvider(args.tasks_root, config_path=args.pipeline)
    context.register_artifact_providers(paper=provider, model_resolver=lambda ref: model)
    created = context.task_service.create({
        "scenario": "ARTIFACT", "artifact_type": "PAPER", "name": "reasoning-paired-study",
        "artifact_path": str(args.source.resolve()), "model_refs": {"optimizer": "deepseek-flash"},
        "max_iterations": 1,
        "optimization_instruction": args.instruction.read_text(encoding="utf-8"),
    })
    task_id = created["task_id"]
    task_dir = args.tasks_root / task_id
    source_root = Path(sys.modules["jiuwenswarm"].__file__).resolve().parents[1]
    runtime_files = {
        "package": Path(sys.modules["jiuwenswarm"].__file__).resolve(),
        "provider": Path(inspect.getfile(PaperProvider)).resolve(),
        "reporter": Path(inspect.getfile(IclrReportingAgent)).resolve(),
        "worker": Path(inspect.getfile(type(context.worker))).resolve(),
    }
    if not all(path.is_relative_to(source_root) for path in runtime_files.values()):
        raise RuntimeError("The live framework files do not share the selected source root")
    origin = {
        "python": sys.version, "executable": sys.executable, "source_root": str(source_root),
        "files": {name: {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                  for name, path in runtime_files.items()},
    }
    (task_dir / "runtime_origin.json").write_text(json.dumps(origin, indent=2), encoding="utf-8")
    print(json.dumps({"task_id": task_id, "task_dir": str(task_dir)}, ensure_ascii=False), flush=True)

    async def push(event_type, event_task_id, payload):
        with (task_dir / "public_events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"type": event_type, "task_id": event_task_id, "payload": payload},
                                    ensure_ascii=False, default=str) + "\n")

    context.worker.register_push_callbacks({key: push for key in (
        "rsi.task.status.changed", "rsi.training.progress", "rsi.training.tree.delta",
        "rsi.training.completed", "rsi.training.failed", "rsi.training.status",
    )})
    context.worker.enqueue(task_id)
    last_progress = None
    while True:
        await asyncio.sleep(2)
        task = context.store.get(task_id)
        state_path = task_dir / "run" / "paper_provider_state.json"
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {}
        progress = (task.status, state.get("current_stage"), state.get("iteration"))
        if progress != last_progress:
            print(json.dumps({"status": progress[0], "stage": progress[1], "iteration": progress[2],
                              "elapsed_seconds": round(time.perf_counter() - started, 2)}), flush=True)
            last_progress = progress
        if task.status in {"COMPLETED", "FAILED", "TERMINATED"}:
            break
    await context.worker._queue.join()
    summary = {"task_id": task_id, "status": task.status,
               "elapsed_seconds": round(time.perf_counter() - started, 2),
               "report": context.report_service.get({"task_id": task_id}),
               "usage": context.usage_service.get({"task_id": task_id}),
               "results": task.config.get("results")}
    (task_dir / "run_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, default=str), flush=True)
    runner = context.worker._run_task
    if runner is not None and not runner.done():
        runner.cancel()
        try:
            await runner
        except asyncio.CancelledError:
            pass
    return 0 if task.status == "COMPLETED" else 1


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=root / "paper-input")
    parser.add_argument("--pipeline", type=Path, default=root / "pipeline.yaml")
    parser.add_argument("--instruction", type=Path, default=root / "INSTRUCTION.txt")
    parser.add_argument("--tasks-root", type=Path, default=root / "tasks")
    raise SystemExit(asyncio.run(run(parser.parse_args())))
