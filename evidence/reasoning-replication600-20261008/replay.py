"""Independently rebuild the sealed four-stage study using Python 3.12 stdlib."""
import argparse
from collections import Counter
from datetime import datetime
from decimal import Decimal
import hashlib
import itertools
import json
from pathlib import Path
import sys

from audit import base_primitives as base
from audit import continuation_primitives as continuation
from audit import completion_primitives as completion
from audit import budget_primitives as budget

STAGES = ("replication600", "replication600-continuation", "replication600-completion", "replication600-resume-20261008")


def replay(bundle):
    bundle = bundle.resolve()
    manifest = base.load(bundle / "public-manifest.json")
    for relative, expected in manifest["files"].items():
        path = (bundle / relative).resolve()
        assert path.is_relative_to(bundle), "Manifest path leaves bundle"
        assert base.digest(path) == expected, relative
    identity = base.load(bundle / "copy-identity.json")
    assert identity["all_exact_copies_match_source_sha256"]
    assert all(base.digest(bundle / r["path"]) == r["sha256"] == r["source_sha256"] for r in identity["exact_copies"])
    tasks = base.load(bundle / "input/dataset.json")
    dataset_manifest = base.load(bundle / "input/manifest.json")
    registrations = base.load(bundle / "registrations.json")["stages"]
    assert [r["stage"] for r in registrations] == list(STAGES)
    assert all(r["kind"] == "DERIVED_PUBLIC_REGISTRATION_PROJECTION" and not r["is_original_registration"] for r in registrations)
    assert registrations[0]["public_execution_status"] == registrations[1]["public_execution_status"] == "FAILED"
    assert len(tasks) == dataset_manifest["n"] == 600
    assert base.digest(bundle / "input/dataset.json") == registrations[0]["registered_relative_file_sha256"]["dataset.json"]
    lf = hashlib.sha256((bundle / "input/dataset.json").read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    assert lf == dataset_manifest["dataset_sha256"] == "7adae0c2cfac2445ce9ee6c8ccb50585060e3d5d0278158a94e34d6ba442c23f"
    prior = base.load(bundle / "input/prior120-dataset.json") + base.load(bundle / "input/prior36-dataset.json")
    legacy = base.load(bundle / "input/legacy-dataset.json")
    assert len(prior) == len(legacy) == len({r["id"] for r in legacy}) == 156
    assert {r["id"]: r for r in legacy} == {r["id"]: r for r in prior}
    for selector in (lambda task: task["id"], base.fingerprint, lambda task: task["prompt"]):
        assert len({selector(t) for t in tasks}) == 600
        assert {selector(t) for t in tasks}.isdisjoint({selector(t) for t in prior})
    for task in tasks:
        assert base.initial_prompt(task) == task["prompt"] and base.fingerprint(task) == task["instance_sha256"]
        assert base.score(task, json.dumps(task["oracle"])) == (True, None)
        if task["family"] == "sat":
            spec = task["spec"]
            assert any(all(any(bool(bits[abs(v)-1]) == (v > 0) for v in clause) for clause in spec["clauses"])
                       for bits in itertools.product((0, 1), repeat=spec["n"]))
    cells = Counter((t["family"], t["difficulty"]) for t in tasks)
    assert len(cells) == 6 and set(cells.values()) == {100}
    assert set(Counter(tuple(t["retry_order"]) for t in tasks).values()) == {100}
    records, events, saved, stage_records, stage_events, stage_keys = [], [], [], [], [], set()
    for index, (stage, registration) in enumerate(zip(STAGES, registrations)):
        root = bundle / "history" / stage
        directories = [root] if index < 2 else [root / "workers" / str(i) for i in range(3 if index == 2 else 2)]
        raw, ledger = [], []
        for directory in directories:
            component, metadata = base.journal(directory / "calls.jsonl", True)
            resource, ledger_metadata = base.journal(directory / "model_calls.jsonl", True)
            assert len({e["event_id"] for e in resource}) == len(resource)
            assert all(datetime.fromisoformat(r["started_at"]) > datetime.fromisoformat(registration["registered_before_first_call_utc"]) for r in component)
            raw += component
            ledger += resource
            saved += base.load(directory / ("eval-results.json" if index < 2 else "completion-rows.json"))
        keys = {r["call_key"] for r in raw}
        assert stage_keys.isdisjoint(keys), "Previously observed, failed, or unknown request reissued"
        stage_keys.update(keys)
        records += raw
        events += ledger
        stage_records.append(raw)
        stage_events.append(ledger)
    calls, groups, per_item = completion.verify_requests(tasks, records)
    missing_keys = [key for key, group in groups.items() if group[-1]["status"] != "ok"]
    missing_ids = {key.split(":")[1] for key in missing_keys}
    historical = [r for stage in stage_records[:3] for r in stage]
    errors = [r for r in historical if r["status"] == "error"]
    unknown = [key for key, group in groups.items() if len(group) == 1]
    assert len(errors) == 5 and len(unknown) == 3 and len(missing_keys) == len(missing_ids) == 8
    assert all(key in {r["call_key"] for r in historical} for key in unknown)
    old_attempted = {r["call_key"].split(":")[1] for r in historical}
    plan = base.load(bundle / "history" / STAGES[3] / "resume-plan.json")
    expected = [t["id"] for t in tasks if t["id"] not in old_attempted]
    assert len(old_attempted) == 420 and len(expected) == 180
    assert plan["unattempted_ids"] == expected and plan["administrative_worker_count"] == 2
    assert {item["id"] for item in plan["old_missing_items"]} == missing_ids
    for worker in range(2):
        assignment = expected[worker::2]
        assert plan["worker_ids"][str(worker)] == assignment
        root = bundle / "history" / STAGES[3] / "workers" / str(worker)
        raw, _ = base.journal(root / "calls.jsonl", True)
        attempted = list(dict.fromkeys(r["call_key"].split(":")[1] for r in raw if r["status"] == "started"))
        terminal = base.load(root / "terminal-items.json")
        assert attempted == [item["id"] for item in terminal] == assignment
        assert all(item["state"] == "complete" for item in terminal)
    ids = [r["response_id"] for r in calls.values()]
    ledger = {e["call_id"]: e for e in events}
    assert len(ids) == len(set(ids)) == len(events) == len(ledger) and set(ids) == set(ledger)
    prior_ids = set(base.load(bundle / "input/prior-response-id-sha256.json"))
    assert {hashlib.sha256(i.encode()).hexdigest() for i in ids}.isdisjoint(prior_ids)
    for reply in calls.values():
        usage = reply["usage"]
        assert all(type(usage[k]) is int and usage[k] >= 0 for k in ("prompt_tokens", "completion_tokens"))
        hit = usage.get("prompt_cache_hit_tokens") or 0
        assert type(hit) is int and 0 <= hit <= usage["prompt_tokens"]
        assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]
        if usage.get("prompt_cache_miss_tokens") is not None:
            assert usage["prompt_cache_miss_tokens"] == usage["prompt_tokens"] - hit
        event = ledger[reply["response_id"]]
        assert event["model_call"]["tokens"] == {"input": usage["prompt_tokens"], "output": usage["completion_tokens"], "cache_hit": hit}
        assert event["model_call"]["model"] == "deepseek-flash" and event["model_call"]["call_count"] == 1
    rows, details, lengths, used, order = completion.generalized_recompute(tasks, calls, missing_ids)
    assert len(rows) == len(saved) == 592 and len({r["id"] for r in saved}) == 592
    details_by_id = {r["id"]: r for r in details}
    assert all(row == details_by_id[row["id"]] for row in saved)
    final = bundle / "history" / STAGES[3]
    assert base.load(final / "results.json")["rows"] == details
    assert {r["id"] for r in base.load(final / "missing.json")} == missing_ids
    for filename, components in (("calls.jsonl", stage_records[3]), ("model_calls.jsonl", stage_events[3])):
        merged, _ = base.journal(final / filename, True)
        assert sorted(json.dumps(r, sort_keys=True) for r in merged) == sorted(json.dumps(r, sort_keys=True) for r in components)
    outcome = base.load(final / "process-result.json")
    assert outcome["status"] == "COMPLETED_WITH_DECLARED_MISSING" and outcome["worker_exit_code"] == 0
    stats = continuation.statistics(rows, details, lengths, calls)
    metrics = base.load(final / "metrics.json")
    assert all(metrics[key] == value for key, value in stats.items() if key in metrics)
    sensitivity = completion.missing_sensitivity(rows, 8)
    assert all(len(value["enumerated_possible_missing_outcomes"]) == 45 for value in sensitivity["comparisons"].values())
    scientific_calls = len(rows) + 3 * sum(not row["initial"] for row in rows)
    assert scientific_calls == len(used) == 1717 and len(calls) == 1721
    auth = base.load(bundle / "accounting/resume-authorization.public.json")
    before = base.load(bundle / "accounting" / STAGES[3] / "budget-before.json")
    after = base.load(bundle / "accounting" / STAGES[3] / "budget-after.json")
    assert before == auth["ledger_after"] and auth["refund_cny"] == "0" and not auth["new_paid_ledger_created"]
    for key in ("charged_micro_cny", "reserved_calls", "settled_calls", "unmetered_calls", "active_reservations"):
        assert auth["ledger_before"][key] == auth["ledger_after"][key]
    initial_budget = base.load(bundle / "accounting" / STAGES[0] / "budget-before.json")
    assert before["unmetered_calls"] - initial_budget["unmetered_calls"] == 7
    new_calls = [r for r in stage_records[3] if r["status"] == "ok"]
    cost = budget.check_budget(before, after, budget.totals(new_calls), len(new_calls), True)
    all_usage = budget.totals(calls.values())
    science_usage = budget.totals(calls[key] for key in used)
    archived = base.load(bundle / "audit/original-resume-final-audit.json")
    for key, value in (("statistics", stats), ("missing_pair_worst_case_sensitivity", sensitivity), ("cost", cost),
                       ("usage_all_successful", all_usage), ("usage_scientific_complete_pairs", science_usage)):
        assert archived[key] == value, key
    control = all_usage["input_tokens"] * 2 + all_usage["output_tokens"] * 8
    peak = Decimal(all_usage["cache_hit_tokens"]) * Decimal("0.04") + (all_usage["input_tokens"] - all_usage["cache_hit_tokens"]) * 2 + all_usage["output_tokens"] * 8
    return {"status": "PASS", "kind": "DERIVED_PORTABLE_FOUR_STAGE_REPLAY", "planned_items": 600,
        "complete_items": 592, "missing_items": 8, "original_strict600_status": "FAILED",
        "first_continuation_status": "FAILED", "historical_raw_error_requests": 5, "historical_started_unknown_requests": 3,
        "historical_global_unknown_delta": 7, "scientific_complete_pair_calls": scientific_calls,
        "all_successful_calls": len(calls), "partial_missing_cost_only_calls": len(calls) - len(used),
        "statistics": stats, "missing_sensitivity": sensitivity, "missing_ids": sorted(missing_ids),
        "usage_scientific_complete_pairs": science_usage, "usage_all_successful": all_usage,
        "all_known_control_usage_CNY": str(Decimal(control) / 1_000_000), "all_known_peak_usage_CNY": str(peak / 1_000_000),
        "resume_accounting": cost, "all600_oracles_checked": True, "prior156_overlap": 0,
        "response_journal_one_to_one": True, "no_reissued_failed_unknown_or_observed_keys": True,
        "no_missing_at_random_assumption": True, "not_a_new_registration_or_paid_run": True,
        "model_api_calls": 0, "network_requests": 0, "live_ledger_access": False}


if __name__ == "__main__":
    assert sys.version_info >= (3, 12), "Use Python 3.12 or later"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "replay-result.json")
    args = parser.parse_args()
    result = replay(args.bundle)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("status", "planned_items", "complete_items", "missing_items", "scientific_complete_pair_calls", "all_successful_calls", "partial_missing_cost_only_calls", "model_api_calls", "network_requests")}))
