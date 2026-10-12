"""Audit the disclosed dynamic completion amendment; two prior FAILED stages stay FAILED."""
import argparse
import ast
from collections import Counter
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import hashlib
import itertools
import json
from pathlib import Path

import audit_replication600 as base
import audit_continuation as amended

ARMS = base.ARMS


def generalized_recompute(tasks, calls, missing_ids):
    # The retained exact scientific function has one transport-only change: skip the registered missing-ID set.
    source = Path(amended.__file__).read_text(encoding="utf-8")
    node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == "recompute")
    function = ast.get_source_segment(source, node)
    function = function.replace("def recompute(tasks, calls):", "def recompute(tasks, calls, missing_ids):", 1)
    function = function.replace('if task["id"] == FAILED_ITEM:', 'if task["id"] in missing_ids:', 1)
    function = function.replace("            break", "            continue")
    namespace = {"base": base, "ARMS": ARMS}
    exec(compile(function, "<exact-amended-recompute-with-missing-set>", "exec"), namespace)
    return namespace["recompute"](tasks, calls, missing_ids)


def missing_sensitivity(rows, missing):
    assert len(rows) + missing == 600
    result = {"planned_denominator": 600, "missing_items": missing, "not_an_imputed_dataset": True,
              "no_missing_at_random_assumption": True, "not_a_confidence_interval": True, "comparisons": {}}
    for name, control in (("primary", "lengthmatchedretry"), ("secondary_exploratory", "blindretry")):
        cases = []
        for i in range(missing + 1):
            for j in range(missing - i + 1):
                extension = ([{"verifiedretry": True, control: False}] * i
                    + [{"verifiedretry": False, control: True}] * j
                    + [{"verifiedretry": False, control: False}] * (missing - i - j))
                case = base.compare(rows + extension, control)
                cases.append({"missing_diagnostic_only": i, "missing_control_only": j, **case})
        observed = base.compare(rows, control)
        difference = observed["diagnostic_only_correct"] - observed["control_only_correct"]
        result["comparisons"][name] = {"observed_complete_case": observed, "enumerated_possible_missing_outcomes": cases,
            "p_value_range": [min(c["exact_mcnemar_p_two_sided"] for c in cases), max(c["exact_mcnemar_p_two_sided"] for c in cases)],
            "paired_difference_full600_range": [(difference - missing) / 600, (difference + missing) / 600],
            "paired_difference_percentage_point_range": [100 * (difference - missing) / 600, 100 * (difference + missing) / 600]}
    result["marginal_accuracy_full600_ranges"] = {a: [sum(r[a] for r in rows) / 600, (sum(r[a] for r in rows) + missing) / 600] for a in ARMS}
    return result


def verify_requests(tasks, records):
    """Check every attempted payload, including cost-only partial items and failed requests."""
    by_id = {t["id"]: t for t in tasks}
    groups = {}
    for record in records:
        groups.setdefault(record["call_key"], []).append(record)
    calls = {key: group[-1] for key, group in groups.items() if group[-1]["status"] == "ok"}
    per_item = {}
    for key, group in groups.items():
        prefix, item, arm = key.split(":")
        assert prefix == "7adae0c2cfac" and item in by_id and arm in ARMS
        assert len(group) in (1, 2) and group[0]["status"] == "started"
        if len(group) == 2:
            assert group[1]["status"] in ("ok", "error")
            assert group[0]["request"] == group[1]["request"] and group[0]["started_at"] == group[1]["started_at"]
        task = by_id[item]
        messages = [{"role": "user", "content": task["prompt"]}]
        if arm != "initial":
            initial = calls[prefix + ":" + item + ":initial"]
            correct, feedback = base.score(task, initial["content"])
            assert not correct, "Correct initial must be reused without retries"
            messages += [{"role": "assistant", "content": initial["content"]},
                         {"role": "user", "content": base.instructions(feedback)[arm]}]
        assert group[0]["request"] == {"model": "deepseek-flash", "messages": messages, "max_tokens": 2048,
            "temperature": 0, "stream": False, "thinking": {"type": "disabled"}}
        per_item.setdefault(item, []).append(group[0])
    for item, starts in per_item.items():
        starts.sort(key=lambda r: r["started_at"])
        arms = [r["call_key"].rsplit(":", 1)[1] for r in starts]
        assert arms == (["initial"] + by_id[item]["retry_order"])[:len(arms)], "Within-task order changed"
        for previous, current in zip(starts, starts[1:]):
            terminal = groups[previous["call_key"]][-1]
            assert terminal["status"] == "ok", "A task continued after failure"
            finished = datetime.fromisoformat(terminal["started_at"]) + timedelta(seconds=terminal["latency_seconds"])
            assert finished <= datetime.fromisoformat(current["started_at"]) + timedelta(milliseconds=2)
    return calls, groups, per_item


def audit(original, continuation, completion, team, final):
    stages = [original, continuation, completion]
    ready, manifest, tasks = (base.load(original / n) for n in ("ready.json", "manifest.json", "dataset.json"))
    frozen = {n: base.digest(original / n) for n in ready["sha256"]}
    assert frozen == ready["sha256"] and len(tasks) == manifest["n"] == 600
    assert base.digest(original / "dataset.json") == "0241523b60df12349ad2124b2a3d94a1eb145e29c26e7590609c5a5bd96c56df"
    assert hashlib.sha256((original / "dataset.json").read_bytes().replace(b"\r\n", b"\n")).hexdigest() == manifest["dataset_sha256"]
    prior_source = team / "code/research_project/reviewer_followup_reasoning"
    prior = base.load(prior_source / "dataset.json") + base.load(prior_source / "legacy-dataset.json")
    for select in (lambda t: t["id"], base.fingerprint, lambda t: t["prompt"]):
        assert len({select(t) for t in tasks}) == 600 and {select(t) for t in tasks}.isdisjoint({select(t) for t in prior})
    for task in tasks:
        assert base.initial_prompt(task) == task["prompt"] and base.score(task, json.dumps(task["oracle"])) == (True, None)
        if task["family"] == "sat":
            spec = task["spec"]
            assert any(all(any(bool(bits[abs(v)-1]) == (v > 0) for v in clause) for clause in spec["clauses"])
                       for bits in itertools.product((0, 1), repeat=spec["n"]))
    assert all(base.load(s / "process-result.json")["status"] == "FAILED" for s in stages[:2])
    registrations = [ready, base.load(continuation / "ready.json"), base.load(completion / "ready.json")]
    registered_hashes = []
    records, events, raw_snapshots, ledger_snapshots, all_keys = [], [], [], [], set()
    for index, stage in enumerate(stages):
        registration = registrations[index]
        actual = {name: base.digest(stage / name) for name in registration["sha256"]}
        assert actual == registration["sha256"]
        prior_hashes = registration.get("original_input_sha256", registration.get("old_input_sha256", {}))
        for path, expected in prior_hashes.items():
            assert base.digest(Path(path)) == expected
        registered_hashes.append(actual)
        directories = [stage] if index < 2 else sorted((stage / "workers").glob("[0-2]"))
        if final:
            assert index < 2 or [p.name for p in directories] == ["0", "1", "2"]
        raw, ledger = [], []
        for directory in directories:
            if not (directory / "calls.jsonl").exists():
                assert not final
                continue
            component, rm = base.journal(directory / "calls.jsonl", final or index < 2)
            component_ledger, lm = base.journal(directory / "model_calls.jsonl", final or index < 2) if (directory / "model_calls.jsonl").exists() else ([], {})
            assert len({e["event_id"] for e in component_ledger}) == len(component_ledger)
            raw += component
            ledger += component_ledger
            raw_snapshots.append({"stage": index, "worker": directory.name if index == 2 else None, **rm})
            ledger_snapshots.append({"stage": index, "worker": directory.name if index == 2 else None, **lm})
        if final and index == 2:
            for name, components in (("calls.jsonl", raw), ("model_calls.jsonl", ledger)):
                merged, _ = base.journal(stage / name, True)
                assert sorted(json.dumps(r, sort_keys=True) for r in merged) == sorted(json.dumps(r, sort_keys=True) for r in components)
        keys = {r["call_key"] for r in raw}
        assert all_keys.isdisjoint(keys), "A previously observed, started or failed request was reissued"
        all_keys.update(keys)
        time_key = "ready_before_first_call_utc" if index == 0 else "registered_before_first_continuation_call_utc"
        if index == 2:
            time_key = next(k for k in registration if k.endswith("_utc") and ("first" in k or "registered" in k))
        assert all(datetime.fromisoformat(r["started_at"]) > datetime.fromisoformat(registration[time_key]) for r in raw)
        records += raw
        events += ledger
    errors = [r for r in records if r["status"] == "error"]
    missing_ids = {r["call_key"].rsplit(":", 1)[0].split(":", 1)[1] for r in errors}
    assert len(missing_ids) == len(errors), "More than one unresolved request for a missing item"
    assert "graph-replication600-easy-64" in missing_ids and "sat-replication600-easy-30" in missing_ids
    assert all(r["http_status"] == 502 for r in errors if r["call_key"].endswith("graph-replication600-easy-64:initial"))
    assert all(r.get("error_type") == "TimeoutError" and r.get("http_status") is None for r in errors if r["call_key"].endswith("sat-replication600-easy-30:verifiedretry"))
    for error in errors:
        assert not error.get("response_id") and not error.get("usage")
        assert error.get("http_status") in (502, 503) or error.get("error_type") == "TimeoutError"
    calls, groups, per_item = verify_requests(tasks, records)
    plan = base.load(completion / "completion-plan.json")
    old_attempted = {r["call_key"].split(":")[1] for r in records if r["started_at"] < registrations[2]["registered_before_first_completion_call_utc"]}
    remaining = [t["id"] for t in tasks if t["id"] not in old_attempted]
    assert plan["unattempted_ids"] == remaining and plan["administrative_worker_count"] == 3
    for worker in range(3):
        expected = remaining[worker::3]
        assert plan["worker_ids"][str(worker)] == expected
        directory = completion / "workers" / str(worker)
        if (directory / "calls.jsonl").exists():
            worker_records, _ = base.journal(directory / "calls.jsonl", final)
            attempted = list(dict.fromkeys(r["call_key"].split(":")[1] for r in worker_records if r["status"] == "started"))
            assert attempted == expected[:len(attempted)]
            if final:
                assert attempted == expected
    pending = []
    for key, group in groups.items():
        assert group[0]["status"] == "started" and len(group) <= 2
        if len(group) == 1:
            pending.append(key)
        else:
            assert group[0]["request"] == group[1]["request"] and group[0]["started_at"] == group[1]["started_at"]
    ids = [r["response_id"] for r in calls.values()]
    ledger = {r["call_id"]: r for r in events}
    assert len(ids) == len(set(ids)) and len(events) == len(ledger)
    if final:
        assert not pending and set(ids) == set(ledger) and len(records) == 2 * (len(calls) + len(errors))
    for reply in calls.values():
        usage = reply["usage"]
        assert all(type(usage[k]) is int and usage[k] >= 0 for k in ("prompt_tokens", "completion_tokens"))
        hit = usage.get("prompt_cache_hit_tokens") or 0
        assert type(hit) is int and 0 <= hit <= usage["prompt_tokens"] and usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]
        if usage.get("prompt_cache_miss_tokens") is not None:
            assert usage["prompt_cache_miss_tokens"] + hit == usage["prompt_tokens"]
        if reply["response_id"] in ledger:
            assert ledger[reply["response_id"]]["model_call"]["tokens"] == {"input": usage["prompt_tokens"], "output": usage["completion_tokens"], "cache_hit": hit}
    old_ids = set()
    old_paths = list((team / "evidence/raw-runs").glob("*/run/model_calls.jsonl")) + [team / "evidence/reviewer-followup/reasoning/model_calls.jsonl"]
    for path in old_paths:
        previous, _ = base.journal(path, True)
        old_ids.update(r["call_id"] for r in previous if r.get("call_id"))
    assert set(ids).isdisjoint(old_ids)
    rows, details, lengths, used, order = generalized_recompute(tasks, calls, missing_ids)
    used_count = len(rows) + 3 * sum(not r["initial"] for r in rows)
    assert used_count == len(used)
    totals = {"input_tokens": sum(r["usage"]["prompt_tokens"] for r in calls.values()),
              "output_tokens": sum(r["usage"]["completion_tokens"] for r in calls.values()),
              "cache_hit_tokens": sum(r["usage"].get("prompt_cache_hit_tokens") or 0 for r in calls.values())}
    before = base.load(original / "budget-before.json")
    policy = before["policy"]
    reserve = int(Decimal(policy["input_cny_per_million"]) * policy["max_input_tokens"] + Decimal(policy["output_cny_per_million"]) * policy["max_output_tokens"])
    assert reserve == 2359296 and before["unmetered_calls"] == 6
    money = base.load(completion / "budget-after.json" if final else original.parent / "model-budget.json")
    assert money["policy"] == policy
    control = totals["input_tokens"] * 2 + totals["output_tokens"] * 8
    peak = Decimal(totals["cache_hit_tokens"]) * Decimal("0.04") + (totals["input_tokens"] - totals["cache_hit_tokens"]) * 2 + totals["output_tokens"] * 8
    stats = None
    if final:
        terminal = base.load(completion / "process-result.json")
        assert terminal["worker_exit_code"] == 0 and "COMPLETED" in terminal["status"]
        assert len(rows) + len(missing_ids) == 600 and not money["active_reservations"]
        assert money["unmetered_calls"] == 6 + len(errors)
        assert money["charged_micro_cny"] - before["charged_micro_cny"] == control + len(errors) * reserve
        assert money["reserved_calls"] - before["reserved_calls"] == money["settled_calls"] - before["settled_calls"] == len(calls) + len(errors)
        stats = amended.statistics(rows, details, lengths, calls)
        saved = base.load(completion / "results.json")["rows"]
        assert saved == details
        metrics = base.load(completion / "metrics.json")
        for key, value in stats.items():
            if key in metrics:
                assert metrics[key] == value, key
    for stage, registration, hashes in zip(stages, registrations, registered_hashes):
        assert hashes == {name: base.digest(stage / name) for name in registration["sha256"]}
        assert all(base.digest(Path(p)) == expected for p, expected in registration.get("original_input_sha256", registration.get("old_input_sha256", {})).items())
    schema_errors = [{"id": r["id"], "arm": a, "error": r[a]["feedback"]["error"]} for r in details for a in ARMS
        if r[a].get("feedback") and r[a]["feedback"]["error"] in ("json_object_required", "integer_answer_schema", "binary_assignment_schema", "path_schema", "invalid_json_or_schema")]
    return {"status": "PASS" if final else "PARTIAL", "mode": "FINAL" if final else "LIVE_SNAPSHOT",
        "audit_scope": "DYNAMIC_COMPLETE_CASES_AFTER_TRANSPORT_AMENDMENTS", "protocol_amended_after_transport_failure": True,
        "administrative_worker_count": 3, "original_sequential_registration_execution_preserved": False,
        "original_strict600_status": "FAILED", "first_continuation_status": "FAILED", "unchanged_registered600_completed": False,
        "planned_items": 600, "completed_item_denominator": len(rows), "observed_complete_pairs": len(rows),
        "transport_missing_items": len(missing_ids), "missing_ids": sorted(missing_ids), "missing_response_types": [{k: r.get(k) for k in ("call_key", "error_type", "http_status")} for r in errors],
        "statistics": stats, "missing_pair_worst_case_sensitivity": missing_sensitivity(rows, len(missing_ids)) if final else None,
        "schema_failures_scored_in_denominator": schema_errors, "unique_successful_responses": len(calls),
        "scientific_complete_pair_call_count": used_count, "actual_successful_call_count": len(calls),
        "partial_missing_item_successful_calls_in_cost_only": len(calls) - len(used), "failed_requests": len(errors),
        "finish_reason_counts": dict(Counter(r.get("finish_reason") for r in calls.values())), "usage": totals,
        "scientific_complete_pair_usage": {"input_tokens": sum(calls[k]["usage"]["prompt_tokens"] for k in used),
            "output_tokens": sum(calls[k]["usage"]["completion_tokens"] for k in used),
            "cache_hit_tokens": sum(calls[k]["usage"].get("prompt_cache_hit_tokens") or 0 for k in used)},
        "cost": {"usage_peak_rate_CNY": str(peak / 1_000_000), "control_usage_CNY": str(Decimal(control) / 1_000_000),
            "extra_unknown_upper_cny": str(Decimal(reserve * len(errors)) / 1_000_000), "failed_reserve_each_cny": "2.359296",
            "prior_safe_actual_upper_CNY": "14.578766", "cumulative_safe_actual_upper_CNY": str(Decimal("14.578766") + (peak + reserve * len(errors)) / 1_000_000),
            "control_charge_delta_CNY": str(Decimal(money["charged_micro_cny"] - before["charged_micro_cny"]) / 1_000_000),
            "expected_control_total_CNY": str(Decimal(control + reserve * len(errors)) / 1_000_000),
            "active_reservations": len(money["active_reservations"]), "historical_unknown_calls_retained": money["unmetered_calls"],
            "failed_amount_is_unknown_upper_not_actual_invoice": True, "final_control_delta_exact": final},
        "all600_oracles_checked": True, "prior156_overlap": 0, "old_response_id_overlap": 0,
        "raw_snapshots": raw_snapshots, "ledger_snapshots": ledger_snapshots, "all_registered_sources_and_prior_raw_unchanged": True,
        "model_api_calls": 0, "network_requests": 0, "not_a_new_complete_agent_workflow": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("original", "continuation", "completion", "team", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--final", action="store_true")
    args = parser.parse_args()
    report = audit(args.original.resolve(), args.continuation.resolve(), args.completion.resolve(), args.team.resolve(), args.final)
    report["checked_at_utc"] = datetime.now(timezone.utc).isoformat()
    report["auditor_sha256"] = base.digest(Path(__file__))
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("status", "observed_complete_pairs", "transport_missing_items", "actual_successful_call_count", "scientific_complete_pair_call_count", "cost")}, ensure_ascii=False))
