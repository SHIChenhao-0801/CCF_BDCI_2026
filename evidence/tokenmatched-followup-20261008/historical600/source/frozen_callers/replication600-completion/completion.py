"""Disclosed transport completion; default is offline, only --run-eval calls models."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from threading import Event
import time

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[1]
ORIGINAL = PROJECT / "process/replication600"
CONTINUATION = PROJECT / "process/replication600-continuation"
TASK_ID = "reasoning-replication600-completion-20261007"
OLD_MISSING = {"graph-replication600-easy-64", "sat-replication600-easy-30"}
sys.path.insert(0, str(ORIGINAL))
spec = importlib.util.spec_from_file_location("original_registered_replication", ORIGINAL / "run.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
runner.TASK_ID = TASK_ID


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def settled(path):
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    records = {}
    for event in events:
        key = event["call_key"]
        if event["status"] == "started":
            assert key not in records, "A call key was resent"
        else:
            assert event["status"] in ("ok", "error") and records[key]["status"] == "started"
        records[key] = event
    assert all(record["status"] != "started" for record in records.values()), "Unresolved started call"
    return records


def old_state():
    tasks, manifest = load(ORIGINAL / "dataset.json"), load(ORIGINAL / "manifest.json")
    rows, records, missing = [], {}, []
    for phase in (ORIGINAL, CONTINUATION):
        outcome = load(phase / "process-result.json")
        assert outcome["status"] == "FAILED" and outcome["worker_exit_code"] == 1
        new = settled(phase / "calls.jsonl")
        assert records.keys().isdisjoint(new)
        records.update(new)
        rows.extend(load(phase / "eval-results.json"))
        for record in new.values():
            if record["status"] == "error":
                item = record["call_key"].split(":")[1]
                missing.append({"id": item, "call_key": record["call_key"], "phase": phase.name,
                                "http_status": record.get("http_status"), "error_type": record.get("error_type")})
    assert {row["id"] for row in missing} == OLD_MISSING and len(missing) == 2
    complete = {row["id"]: row for row in rows}
    assert len(complete) == len(rows) and complete.keys().isdisjoint(OLD_MISSING)
    by_id = {task["id"]: task for task in tasks}
    assert len(tasks) == len(by_id) == 600
    for row in rows:
        for arm in runner.ARMS:
            record = records[row[arm]["call_key"]]
            assert record["status"] == "ok"
            assert runner.baseline.check(by_id[row["id"]], record["content"])[0] == row[arm]["correct"]
    attempted = {key.split(":")[1] for key in records}
    assert attempted == complete.keys() | OLD_MISSING
    remaining = [task for task in tasks if task["id"] not in attempted]
    return tasks, manifest, rows, records, missing, remaining


def verify_registration():
    ready = load(ROOT / "ready.json")
    assert ready["model_calls"] == 0
    assert all(sha(ROOT / name) == value for name, value in ready["sha256"].items())
    assert all(sha(Path(name)) == value for name, value in ready["old_input_sha256"].items())
    state = old_state()
    assert [task["id"] for task in state[-1]] == load(ROOT / "completion-plan.json")["unattempted_ids"]
    return state


def execute_worker(index, tasks, dataset_hash, stopped):
    directory = ROOT / "workers" / str(index)
    directory.mkdir(parents=True, exist_ok=False)
    ledger, rows, missing = directory / "model_calls.jsonl", [], []
    for task in tasks:
        assert not stopped.is_set(), "Another worker stopped the completion phase"
        try:
            row = runner.execute([task], directory, ledger, dataset_hash)
        except Exception as error:
            if not isinstance(error, RuntimeError):
                stopped.set()
                raise
            current = settled(directory / "calls.jsonl")
            failed = [record for record in current.values() if record["status"] == "error"
                      and record["call_key"].split(":")[1] == task["id"]]
            if len(failed) != 1 or not (failed[0].get("http_status") in (502, 503)
                                      or failed[0].get("error_type") == "TimeoutError"):
                stopped.set()
                raise
            record = failed[0]
            missing.append({"id": task["id"], "call_key": record["call_key"], "phase": ROOT.name,
                            "worker": index, "http_status": record.get("http_status"),
                            "error_type": record.get("error_type"),
                            "recorded_at": datetime.now(timezone.utc).isoformat()})
            (directory / "missing.json").write_text(json.dumps(missing, indent=2) + "\n", "utf-8")
            continue
        rows.extend(row)
        (directory / "completion-rows.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return rows, missing, settled(directory / "calls.jsonl")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-eval", action="store_true")
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "metrics.json")
    parser.add_argument("--usage-ledger", type=Path, default=ROOT / "model_calls.jsonl")
    parser.add_argument("--task-id", choices=[TASK_ID], default=TASK_ID)
    args = parser.parse_args()
    assert not (args.run_eval and args.smoke_test)
    assert args.output.resolve().is_relative_to(ROOT) and args.usage_ledger.resolve().is_relative_to(ROOT)
    policy = load(PROJECT / "process/flight-policy.json")
    assert not ((policy["paused"] or datetime.now().astimezone() >= datetime.fromisoformat(policy["protect_from"]))
                and not policy["door_open_confirmed"]), "Boarding pause"
    tasks, manifest, old_rows, old_records, missing, remaining = verify_registration()
    summary = {"status": "OFFLINE_READY_NO_API", "smoke_test": True, "model_call_count": 0,
               "planned_eval_count": 600, "previous_complete_rows": len(old_rows),
               "remaining_unattempted_rows": len(remaining), "old_missing_items": missing,
               "maximum_new_calls": len(remaining) * 4}
    if args.run_eval:
        assert not (ROOT / "workers").exists(), "Do not resume or resend a started completion phase"
        started, new_rows = time.perf_counter(), []
        (ROOT / "missing.json").write_text(json.dumps(missing, indent=2) + "\n", "utf-8")
        new_records = {}
        stopped = Event()
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = [pool.submit(execute_worker, index, remaining[index::3], manifest["dataset_sha256"], stopped)
                       for index in range(3)]
            for future in futures:
                rows, failed, records = future.result()
                assert new_records.keys().isdisjoint(records)
                new_rows.extend(rows)
                missing.extend(failed)
                new_records.update(records)
        new_rows.sort(key=lambda row: next(index for index, task in enumerate(tasks) if task["id"] == row["id"]))
        (ROOT / "completion-rows.json").write_text(json.dumps(new_rows, ensure_ascii=False, indent=2) + "\n", "utf-8")
        (ROOT / "missing.json").write_text(json.dumps(missing, indent=2) + "\n", "utf-8")
        for name, target in (("calls.jsonl", ROOT / "calls.jsonl"), ("model_calls.jsonl", args.usage_ledger)):
            events = [json.loads(line) for index in range(3)
                      for line in (ROOT / "workers" / str(index) / name).read_text("utf-8").splitlines()]
            events.sort(key=lambda event: (event.get("started_at", event.get("timestamp", "")),
                                            event.get("call_key", event.get("call_id", "")), event.get("status") != "started"))
            target.write_text("".join(json.dumps(event, ensure_ascii=False) + "\n" for event in events), "utf-8")
        assert old_records.keys().isdisjoint(new_records)
        records = {**old_records, **new_records}
        merged = {row["id"]: row for row in old_rows + new_rows}
        missing_ids = {row["id"] for row in missing}
        assert merged.keys().isdisjoint(missing_ids) and len(merged) + len(missing_ids) == 600
        complete = [merged[task["id"]] for task in tasks if task["id"] not in missing_ids]
        summary = runner.metrics(complete, records)
        successes = [record for record in records.values() if record["status"] == "ok"]
        ids = [record["response_id"] for record in successes]
        assert len(ids) == len(set(ids))
        complete_keys = {row[arm]["call_key"] for row in complete for arm in runner.ARMS}
        phase_elapsed = time.perf_counter() - started
        old_elapsed = sum(load(phase / "process-result.json")["elapsed_seconds"] for phase in (ORIGINAL, CONTINUATION))
        summary.update(protocol="replication600-transport-completion-amendment-v2", planned_eval_count=600,
                       observed_complete_cases=len(complete), missing_transport_items=sorted(missing_ids),
                       missing_transport_count=len(missing_ids), original_execution_status="FAILED",
                       previous_continuation_status="FAILED", after_interruption_amendment=True,
                       completion_complete_rows=len(new_rows), completion_elapsed_seconds=phase_elapsed,
                       administrative_worker_count=3, administrative_partition="roundrobin dataset order; sequential within worker",
                       original_stage_elapsed_seconds=old_elapsed, elapsed_seconds=old_elapsed + phase_elapsed,
                       ledger_actual_response_count=len(successes),
                       ledger_partial_successful_response_count=sum(record["call_key"] not in complete_keys for record in successes),
                       ledger_transport_failed_request_count=sum(record["status"] == "error" for record in records.values()),
                       ledger_usage_all_successful={"input_tokens": sum(record["usage"]["prompt_tokens"] for record in successes),
                                                   "output_tokens": sum(record["usage"]["completion_tokens"] for record in successes),
                                                   "cache_hit_tokens": sum(record["usage"].get("prompt_cache_hit_tokens") or 0 for record in successes)},
                       observed_cell_denominators=dict(Counter(row["family"] + ":" + row["difficulty"] for row in complete)),
                       smoke_test=False,
                       claim_scope="Planned600,dynamic complete-case N after disclosed transport amendments; original strict600 and first continuation FAILED; no MCAR claim; no pooling with120")
        (ROOT / "results.json").write_text(json.dumps({"metrics": summary, "rows": complete}, ensure_ascii=False, indent=2) + "\n", "utf-8")
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
