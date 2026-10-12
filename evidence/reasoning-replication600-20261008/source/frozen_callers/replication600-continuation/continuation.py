"""Disclosed after-interruption continuation; default/smoke is0API, original study staysFAILED."""
import argparse
from datetime import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[1]
ORIGINAL = PROJECT / "process/replication600"
SKIP_ID = "graph-replication600-easy-64"
TASK_ID = "reasoning-replication600-continuation-20261007"
sys.path.insert(0, str(ORIGINAL))
spec = importlib.util.spec_from_file_location("original_registered_replication", ORIGINAL / "run.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
runner.TASK_ID = TASK_ID


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def calls(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def original_state():
    ready, manifest, tasks = (load(ORIGINAL / name) for name in ("ready.json", "manifest.json", "dataset.json"))
    assert all(sha(ORIGINAL / name) == value for name, value in ready["sha256"].items())
    outcome = load(ORIGINAL / "process-result.json")
    assert outcome["status"] == "FAILED" and outcome["worker_exit_code"] == 1
    rows = load(ORIGINAL / "eval-results.json")
    records = calls(ORIGINAL / "calls.jsonl")
    settled = {row["call_key"]: row for row in records if row["status"] in ("ok", "error")}
    assert len(settled) * 2 == len(records)
    failed = [row for row in settled.values() if row["status"] == "error"]
    skipped_key = manifest["dataset_sha256"][:12] + ":" + SKIP_ID + ":initial"
    assert len(failed) == 1 and failed[0]["call_key"] == skipped_key and failed[0]["http_status"] == 502
    completed = {row["id"] for row in rows}
    assert len(rows) == len(completed) == 360 and SKIP_ID not in completed
    assert [task["id"] for task in tasks[:len(rows)]] == [row["id"] for row in rows]
    assert tasks[len(rows)]["id"] == SKIP_ID
    by_id = {task["id"]: task for task in tasks}
    used = set()
    for row in rows:
        for arm in runner.ARMS:
            key = row[arm]["call_key"]
            assert settled[key]["status"] == "ok"
            assert runner.baseline.check(by_id[row["id"]], settled[key]["content"])[0] == row[arm]["correct"]
            used.add(key)
    assert used == {key for key, record in settled.items() if record["status"] == "ok"}
    remaining = [task for task in tasks if task["id"] not in completed and task["id"] != SKIP_ID]
    assert len(tasks) == 600 and len(remaining) == 239
    return tasks, manifest, rows, settled, remaining


def verify_registration():
    ready = load(ROOT / "ready.json")
    assert ready["skip_id"] == SKIP_ID and ready["model_calls"] == 0
    assert all(sha(ROOT / name) == value for name, value in ready["sha256"].items())
    assert all(sha(Path(path)) == value for path, value in ready["original_input_sha256"].items())
    assert datetime.fromisoformat(ready["registered_before_first_continuation_call_utc"]).timestamp() <= time.time()
    return original_state()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-eval", action="store_true")
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "metrics.json")
    parser.add_argument("--usage-ledger", type=Path, default=ROOT / "model_calls.jsonl")
    parser.add_argument("--task-id", choices=[TASK_ID], default=TASK_ID)
    args = parser.parse_args()
    assert not (args.smoke_test and args.run_eval)
    assert args.output.resolve().is_relative_to(ROOT) and args.usage_ledger.resolve().is_relative_to(ROOT)
    policy = load(PROJECT / "process/flight-policy.json")
    assert not ((policy["paused"] or datetime.now().astimezone() >= datetime.fromisoformat(policy["protect_from"]))
                and not policy["door_open_confirmed"]), "Boarding pause"
    tasks, manifest, previous, prior_records, remaining = verify_registration()
    summary = {"status": "OFFLINE_READY_NO_API", "smoke_test": True, "model_call_count": 0,
               "planned_eval_count": 600, "original_complete_rows": len(previous),
               "continuation_planned_rows": len(remaining), "missing_transport_item": SKIP_ID,
               "complete_case_target": 599, "maximum_new_calls": len(remaining) * 4,
               "original_execution_status": "FAILED", "after_interruption_amendment": True}
    if args.run_eval:
        started = time.perf_counter()
        new_rows = runner.execute(remaining, ROOT, args.usage_ledger, manifest["dataset_sha256"])
        assert len(new_rows) == len(remaining)
        new_records = {row["call_key"]: row for row in calls(ROOT / "calls.jsonl") if row["status"] == "ok"}
        assert set(new_records).isdisjoint(prior_records)
        merged = {row["id"]: row for row in previous + new_rows}
        complete = [merged[task["id"]] for task in tasks if task["id"] != SKIP_ID]
        assert len(complete) == 599 and len(merged) == 599
        summary = runner.metrics(complete, {**prior_records, **new_records})
        summary.update(protocol="replication600-after-transport-amendment-v1", planned_eval_count=600,
                       complete_case_target=599, missing_transport_items=[SKIP_ID], missing_transport_count=1,
                       original_execution_status="FAILED", after_interruption_amendment=True,
                       continuation_model_call_count=len(new_records), continuation_complete_rows=len(new_rows),
                       continuation_elapsed_seconds=time.perf_counter() - started,
                       original_stage_elapsed_seconds=load(ORIGINAL / "process-result.json")["elapsed_seconds"],
                       elapsed_seconds=load(ORIGINAL / "process-result.json")["elapsed_seconds"] + time.perf_counter() - started,
                       smoke_test=False,
                       claim_scope="After-interruption amendment: planned600,599 observed complete pairs,1 transport-missing; original strict registered600 FAILED; not full Agent workflow")
        (ROOT / "results.json").write_text(json.dumps({"metrics": summary, "rows": complete}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (ROOT / "continuation-rows.json").write_text(json.dumps(new_rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
