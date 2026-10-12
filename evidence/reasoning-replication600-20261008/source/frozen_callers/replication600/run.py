"""A frozen 600-item replication registered after the observed120 study. Only --run-eval permits model calls."""
import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
import time
from pathlib import Path

import generator
import legacy_runner as baseline

ROOT = Path(__file__).resolve().parent
TASK_ID = "reasoning-replication600-20261007"
ARMS = ("initial", *generator.RETRIES)
RECONSIDER = "Reconsider your previous answer and return only the requested final JSON object."
NEUTRAL_SENTENCE = "Check your answer carefully. "


def retry_instructions(feedback):
    diagnostic = RECONSIDER + "\nDeterministic checker feedback: " + json.dumps(feedback, separators=(",", ":"))
    tail_length = len(diagnostic) - len(RECONSIDER) - 1
    repetitions, remainder = divmod(tail_length, len(NEUTRAL_SENTENCE))
    neutral = NEUTRAL_SENTENCE * repetitions + "." * remainder
    matched = RECONSIDER + "\n" + neutral
    assert len(matched) == len(diagnostic) and len(matched.encode()) == len(diagnostic.encode())
    return {"blindretry": RECONSIDER, "verifiedretry": diagnostic, "lengthmatchedretry": matched}


def message_lengths(messages):
    return {"content_characters": sum(len(m["content"]) for m in messages),
            "content_utf8_bytes": sum(len(m["content"].encode()) for m in messages)}


def verify_freeze():
    ready = json.loads((ROOT / "ready.json").read_text("utf-8"))
    for name, expected in ready["sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, "Frozen input changed: " + name
    assert datetime.fromisoformat(ready["ready_before_first_call_utc"]).timestamp() <= time.time()
    tasks = json.loads((ROOT / "dataset.json").read_text("utf-8"))
    manifest = json.loads((ROOT / "manifest.json").read_text("utf-8"))
    assert tasks == generator.make_dataset()[0] and len(tasks) == 600
    generator.independent_oracle_check(tasks)
    return tasks, manifest, ready


def execute(tasks, output_root, ledger, dataset_hash):
    rows, log = [], output_root / "calls.jsonl"
    for task in tasks:
        key = dataset_hash[:12] + ":" + task["id"]
        messages = [{"role": "user", "content": task["prompt"]}]
        initial = baseline.call(log, key + ":initial", messages, ledger, TASK_ID, TASK_ID)
        if initial["status"] != "ok":
            raise RuntimeError("Unresolved call retained; no automatic resend: " + initial["call_key"])
        correct, feedback = baseline.check(task, initial["content"])
        row = {"id": task["id"], "family": task["family"], "difficulty": task["difficulty"],
               "retry_order": task["retry_order"],
               "initial": {"call_key": initial["call_key"], "correct": correct, "feedback": feedback}}
        history = messages + [{"role": "assistant", "content": initial["content"]}]
        instructions = retry_instructions(feedback) if not correct else None
        lengths = {}
        for arm in task["retry_order"]:
            if correct:
                row[arm] = {"call_key": initial["call_key"], "correct": True, "reused_initial": True}
                continue
            retry = history + [{"role": "user", "content": instructions[arm]}]
            lengths[arm] = message_lengths(retry)
            result = baseline.call(log, key + ":" + arm, retry, ledger, TASK_ID, TASK_ID)
            if result["status"] != "ok":
                raise RuntimeError("Unresolved call retained; no automatic resend: " + result["call_key"])
            passed, error = baseline.check(task, result["content"])
            row[arm] = {"call_key": result["call_key"], "correct": passed, "feedback": error,
                        "reused_initial": False, "request_lengths": lengths[arm]}
        if not correct:
            assert lengths["verifiedretry"] == lengths["lengthmatchedretry"]
        rows.append(row)
        (output_root / "eval-results.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", "utf-8")
        print(json.dumps({"completed": len(rows), "id": task["id"],
                          "correct": {arm: row[arm]["correct"] for arm in ARMS}}), flush=True)
    return rows


def paired(rows, control):
    better = sum(r["verifiedretry"]["correct"] and not r[control]["correct"] for r in rows)
    worse = sum(r[control]["correct"] and not r["verifiedretry"]["correct"] for r in rows)
    discordant = better + worse
    p = min(1.0, 2 * sum(baseline.math.comb(discordant, k) for k in range(min(better, worse) + 1))
            / 2 ** discordant) if discordant else 1.0
    return {"diagnostic_only_correct": better, "control_only_correct": worse,
            "difference": (better - worse) / len(rows), "exact_mcnemar_p_two_sided": p}


def metrics(rows, records):
    n = len(rows)
    keys = {r[arm]["call_key"] for r in rows for arm in ARMS}
    calls = [records[key] for key in sorted(keys)]
    assert all(c["status"] == "ok" for c in calls)
    assert len(calls) == n + 3 * sum(not r["initial"]["correct"] for r in rows)
    ids = [c["response_id"] for c in calls if c.get("response_id")]
    assert len(ids) == len(set(ids)), "Duplicate response ID across actual requests"
    token_differences = [records[r["verifiedretry"]["call_key"]]["usage"]["prompt_tokens"]
                         - records[r["lengthmatchedretry"]["call_key"]]["usage"]["prompt_tokens"]
                         for r in rows if not r["initial"]["correct"]]
    intervals = {}
    for arm in ARMS:
        proportion, z = sum(r[arm]["correct"] for r in rows) / n, 1.959963984540054
        denominator = 1 + z * z / n
        center = (proportion + z * z / (2 * n)) / denominator
        radius = z * baseline.math.sqrt(proportion * (1 - proportion) / n + z * z / (4 * n * n)) / denominator
        intervals[arm] = [max(0, center - radius), min(1, center + radius)]
    arm_usage = {}
    for arm in ARMS:
        actual = [records[r[arm]["call_key"]] for r in rows if arm == "initial" or not r["initial"]["correct"]]
        arm_usage[arm] = {"call_count": len(actual),
                          "input_tokens": sum(c["usage"]["prompt_tokens"] for c in actual),
                          "output_tokens": sum(c["usage"]["completion_tokens"] for c in actual),
                          "client_call_seconds": sum(c["latency_seconds"] for c in actual)}
    return {"method": "paired_study", "protocol": "reasoning-replication600-v1", "status": "completed",
            "valid_eval_count": n, "correct_counts": {arm: sum(r[arm]["correct"] for r in rows) for arm in ARMS},
            "accuracies": {arm: sum(r[arm]["correct"] for r in rows) / n for arm in ARMS},
            "accuracy_wilson_95": intervals,
            "cell_counts": {family + ":" + difficulty: {arm: sum(r[arm]["correct"] for r in rows
                                if r["family"] == family and r["difficulty"] == difficulty) for arm in ARMS}
                            for family in generator.FAMILIES for difficulty in ("easy", "hard")},
            "primary_diagnostic_vs_lengthmatched": paired(rows, "lengthmatchedretry"),
            "secondary_diagnostic_vs_generic": paired(rows, "blindretry"),
            "initial_errors_repaired": {arm: sum(not r["initial"]["correct"] and r[arm]["correct"] for r in rows)
                                        for arm in generator.RETRIES},
            "error_class_counts": {arm: dict(Counter(r[arm]["feedback"]["error"] for r in rows
                                    if r[arm].get("feedback"))) for arm in ARMS},
            "actual_retry_orders": dict(Counter(",".join(r["retry_order"]) for r in rows if not r["initial"]["correct"])),
            "input_tokens": sum(c["usage"]["prompt_tokens"] for c in calls),
            "output_tokens": sum(c["usage"]["completion_tokens"] for c in calls),
            "cache_hit_tokens": sum(c["usage"].get("prompt_cache_hit_tokens") or 0 for c in calls),
            "model_call_count": len(calls), "client_call_seconds": sum(c["latency_seconds"] for c in calls),
            "arm_usage_excludes_shared_initial": arm_usage,
            "diagnostic_minus_matched_prompt_tokens": token_differences,
            "length_match_audit": [{"id": r["id"], "decoded_content_lengths": r["verifiedretry"]["request_lengths"],
                                    "matched_lengths_equal": r["verifiedretry"]["request_lengths"] == r["lengthmatchedretry"]["request_lengths"],
                                    "diagnostic_prompt_tokens": records[r["verifiedretry"]["call_key"]]["usage"]["prompt_tokens"],
                                    "matched_prompt_tokens": records[r["lengthmatchedretry"]["call_key"]]["usage"]["prompt_tokens"]}
                                   for r in rows if not r["initial"]["correct"]],
            "length_control": "exact decoded content characters and UTF-8 bytes; NOT token-equivalent",
            "claim_scope": "operator-run independent synthetic replication registered after observed120; not a new complete Agent workflow"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-eval", action="store_true")
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--method", choices=["paired_study"], default="paired_study")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--usage-ledger", type=Path, default=ROOT / "model_calls.jsonl")
    parser.add_argument("--task-id", choices=[TASK_ID], default=TASK_ID)
    args = parser.parse_args()
    assert not (args.smoke_test and args.run_eval)
    tasks, manifest, ready = verify_freeze()
    assert args.usage_ledger.resolve().is_relative_to(ROOT), "Use this follow-up's independent ledger only"
    result = {"method": "paired_study", "status": "completed", "smoke_test": True,
              "dataset_verified_count": len(tasks), "model_call_count": 0,
              "dataset_sha256": manifest["dataset_sha256"], "ready_before_first_call_utc": ready["ready_before_first_call_utc"]}
    if args.run_eval:
        started = time.perf_counter()
        rows = execute(tasks, ROOT, args.usage_ledger, manifest["dataset_sha256"])
        records = {r["call_key"]: r for r in map(json.loads, (ROOT / "calls.jsonl").read_text("utf-8").splitlines())}
        result = metrics(rows, records)
        result["elapsed_seconds"] = time.perf_counter() - started
        result["smoke_test"] = False
        (ROOT / "results.json").write_text(json.dumps({"metrics": result, "rows": rows}, ensure_ascii=False, indent=2) + "\n", "utf-8")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
