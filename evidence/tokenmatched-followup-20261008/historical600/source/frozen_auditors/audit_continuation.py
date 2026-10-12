"""Independent AMENDED599 audit after one unretried HTTP502; original strict600 stays FAILED."""
import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import itertools
import json
from pathlib import Path

import audit_replication600 as base

FAILED_ITEM = "graph-replication600-easy-64"
ARMS = base.ARMS


def recompute(tasks, calls):
    rows, details, lengths, used, order = [], [], [], set(), []
    for task in tasks:
        if task["id"] == FAILED_ITEM:
            continue
        prefix = "7adae0c2cfac:" + task["id"]
        initial = calls.get(prefix + ":initial")
        if initial is None:
            break
        correct, feedback = base.score(task, initial["content"])
        needed = ["initial"] + ([] if correct else task["retry_order"])
        if any(prefix + ":" + arm not in calls for arm in needed):
            break
        retry = base.instructions(feedback) if not correct else {}
        row = {"id": task["id"], "family": task["family"], "difficulty": task["difficulty"]}
        item = {**row, "retry_order": task["retry_order"]}
        sizes = {}
        for arm in ARMS:
            key = prefix + ":" + ("initial" if correct else arm)
            reply = calls[key]
            messages = [{"role": "user", "content": task["prompt"]}]
            if arm != "initial" and not correct:
                messages += [{"role": "assistant", "content": initial["content"]}, {"role": "user", "content": retry[arm]}]
            assert reply["request"] == {"model": "deepseek-flash", "messages": messages, "max_tokens": 2048,
                                         "temperature": 0, "stream": False, "thinking": {"type": "disabled"}}
            valid, error = base.score(task, reply["content"])
            row[arm] = valid
            item[arm] = {"call_key": key, "correct": valid}
            if arm == "initial" or not correct:
                item[arm]["feedback"] = error
            if arm != "initial":
                item[arm]["reused_initial"] = correct
            if arm != "initial" and not correct:
                sizes[arm] = {"content_characters": sum(len(m["content"]) for m in messages),
                              "content_utf8_bytes": sum(len(m["content"].encode()) for m in messages)}
                item[arm]["request_lengths"] = sizes[arm]
            used.add(key)
        if not correct:
            assert sizes["verifiedretry"] == sizes["lengthmatchedretry"]
            lengths.append({"id": task["id"], "decoded_content_lengths": sizes["verifiedretry"], "matched_lengths_equal": True,
                "diagnostic_prompt_tokens": calls[prefix+":verifiedretry"]["usage"]["prompt_tokens"],
                "matched_prompt_tokens": calls[prefix+":lengthmatchedretry"]["usage"]["prompt_tokens"]})
        order.extend(prefix+":"+arm for arm in needed)
        rows.append(row)
        details.append(item)
    return rows, details, lengths, used, order


def statistics(rows, details, lengths, calls):
    n = len(rows)
    counts = {arm: sum(r[arm] for r in rows) for arm in ARMS}
    result = {"valid_eval_count": n, "correct_counts": counts,
        "accuracies": {a: counts[a] / n for a in ARMS}, "accuracy_wilson_95": {a: base.wilson(counts[a], n) for a in ARMS},
        "primary_diagnostic_vs_lengthmatched": base.compare(rows, "lengthmatchedretry"),
        "secondary_diagnostic_vs_generic": base.compare(rows, "blindretry"),
        "cell_counts": {f+":"+d: {a: sum(r[a] for r in rows if r["family"] == f and r["difficulty"] == d) for a in ARMS}
                        for f in ("arithmetic", "graph", "sat") for d in ("easy", "hard")},
        "cell_denominators": {f+":"+d: sum(r["family"] == f and r["difficulty"] == d for r in rows)
                        for f in ("arithmetic", "graph", "sat") for d in ("easy", "hard")},
        "initial_errors_repaired": {a: sum(not r["initial"] and r[a] for r in rows) for a in ARMS[1:]},
        "error_class_counts": {a: dict(Counter(r[a]["feedback"]["error"] for r in details if r[a].get("feedback"))) for a in ARMS},
        "actual_retry_orders": dict(Counter(",".join(r["retry_order"]) for r in details if not r["initial"]["correct"])),
        "diagnostic_minus_matched_prompt_tokens": [r["diagnostic_prompt_tokens"] - r["matched_prompt_tokens"] for r in lengths],
        "length_match_audit": lengths, "arm_usage_excludes_shared_initial": {}}
    for arm in ARMS:
        actual = [calls[r[arm]["call_key"]] for r in details if arm == "initial" or not r["initial"]["correct"]]
        result["arm_usage_excludes_shared_initial"][arm] = {"call_count": len(actual),
            "input_tokens": sum(r["usage"]["prompt_tokens"] for r in actual),
            "output_tokens": sum(r["usage"]["completion_tokens"] for r in actual),
            "client_call_seconds": sum(r["latency_seconds"] for r in actual)}
    return result


def sensitivity(rows):
    assert len(rows) == 599
    result = {"planned_denominator": 600, "missing_items": 1,
        "not_an_imputed_dataset": True, "no_missing_at_random_assumption": True, "comparisons": {}}
    for name, control in (("primary", "lengthmatchedretry"), ("secondary_exploratory", "blindretry")):
        cases = {}
        for label, diagnostic, comparator in (("both_incorrect", False, False), ("both_correct", True, True), ("diagnostic_only", True, False), ("control_only", False, True)):
            cases[label] = base.compare(rows + [{"verifiedretry": diagnostic, control: comparator}], control)
        result["comparisons"][name] = {"possible_missing_paired_outcomes": cases,
            "p_value_range": [min(v["exact_mcnemar_p_two_sided"] for v in cases.values()), max(v["exact_mcnemar_p_two_sided"] for v in cases.values())],
            "paired_difference_full600_range": [min(v["difference"] for v in cases.values()), max(v["difference"] for v in cases.values())]}
    result["marginal_accuracy_full600_ranges"] = {a: [sum(r[a] for r in rows) / 600, (sum(r[a] for r in rows) + 1) / 600] for a in ARMS}
    return result


def audit(original, continuation, team, final):
    ready, manifest, tasks = (base.load(original / n) for n in ("ready.json", "manifest.json", "dataset.json"))
    hashes = {name: base.digest(original / name) for name in ready["sha256"]}
    assert hashes == ready["sha256"]
    assert manifest["n"] == len(tasks) == 600 and manifest["dataset_sha256"].startswith("7adae0c2cfac")
    assert base.digest(original / "dataset.json") == "0241523b60df12349ad2124b2a3d94a1eb145e29c26e7590609c5a5bd96c56df"
    assert hashlib.sha256((original / "dataset.json").read_bytes().replace(b"\r\n", b"\n")).hexdigest() == manifest["dataset_sha256"]
    prior_source = team / "code/research_project/reviewer_followup_reasoning"
    prior = base.load(prior_source / "dataset.json") + base.load(prior_source / "legacy-dataset.json")
    assert len(prior) == 156 and len({base.fingerprint(t) for t in tasks}) == 600
    for selector in (lambda t: t["id"], base.fingerprint, lambda t: t["prompt"]):
        assert {selector(t) for t in tasks}.isdisjoint({selector(t) for t in prior})
    for task in tasks:
        assert base.initial_prompt(task) == task["prompt"] and base.score(task, json.dumps(task["oracle"])) == (True, None)
        if task["family"] == "sat":
            spec = task["spec"]
            assert any(all(any(bool(bits[abs(lit)-1]) == (lit > 0) for lit in clause) for clause in spec["clauses"])
                       for bits in itertools.product((0, 1), repeat=spec["n"]))
    old_result = base.load(original / "process-result.json")
    assert old_result["status"] == "FAILED" and old_result["worker_exit_code"] == 1
    amendment = base.load(continuation / "ready.json")
    assert amendment["skip_id"] == FAILED_ITEM and amendment["model_calls"] == 0
    amendment_hashes = {name: base.digest(continuation / name) for name in amendment["sha256"]}
    assert amendment_hashes == amendment["sha256"]
    assert all(base.digest(Path(path)) == expected for path, expected in amendment["original_input_sha256"].items())
    plan = base.load(continuation / "continuation-plan.json")
    assert plan["remaining_ids"] == [t["id"] for t in tasks[361:]] and plan["continuation_planned_rows"] == 239
    assert tasks[360]["id"] == FAILED_ITEM and plan["after_interruption_amendment"] is True
    old_raw, old_meta = base.journal(original / "calls.jsonl", True)
    new_raw, new_meta = base.journal(continuation / "calls.jsonl", final)
    old_events, old_ledger_meta = base.journal(original / "model_calls.jsonl", True)
    new_events, new_ledger_meta = base.journal(continuation / "model_calls.jsonl", final)
    old_keys = {r["call_key"] for r in old_raw}
    new_keys = {r["call_key"] for r in new_raw}
    assert old_keys.isdisjoint(new_keys), "Observed or failed requests were resubmitted"
    amendment_time = datetime.fromisoformat(amendment["registered_before_first_continuation_call_utc"])
    assert all(datetime.fromisoformat(r["started_at"]) > amendment_time for r in new_raw)
    errors = [r for r in old_raw + new_raw if r["status"] == "error"]
    failed_key = manifest["dataset_sha256"][:12] + ":" + FAILED_ITEM + ":initial"
    assert len(errors) == 1 and errors[0]["call_key"] == failed_key and errors[0]["http_status"] == 502
    assert not errors[0].get("response_id") and not errors[0].get("usage")
    assert failed_key not in new_keys and not any(FAILED_ITEM in key for key in new_keys)
    records = old_raw + new_raw
    calls = {r["call_key"]: r for r in records if r["status"] == "ok"}
    groups = {}
    for r in records:
        groups.setdefault(r["call_key"], []).append(r)
    pending = []
    registration = datetime.fromisoformat(ready["ready_before_first_call_utc"])
    for key, group in groups.items():
        assert group[0]["status"] == "started" and len(group) <= 2
        assert datetime.fromisoformat(group[0]["started_at"]) > registration
        if len(group) == 1:
            pending.append(key)
        else:
            assert group[0]["request"] == group[1]["request"] and group[0]["started_at"] == group[1]["started_at"]
    ids = [r["response_id"] for r in calls.values()]
    assert len(ids) == len(set(ids)) and all(isinstance(i, str) and i for i in ids)
    events = old_events + new_events
    ledger = {e["call_id"]: e for e in events}
    assert len(events) == len(ledger)
    assert all(len({e["event_id"] for e in group}) == len(group) for group in (old_events, new_events))
    missing, extra = set(ids) - set(ledger), set(ledger) - set(ids)
    if final:
        assert not pending and not missing and not extra and len(records) == 2 * (len(calls) + 1)
    for reply in calls.values():
        usage = reply["usage"]
        assert all(type(usage[k]) is int and usage[k] >= 0 for k in ("prompt_tokens", "completion_tokens"))
        hit = usage.get("prompt_cache_hit_tokens") or 0
        assert type(hit) is int and 0 <= hit <= usage["prompt_tokens"]
        assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]
        if reply["response_id"] in ledger:
            assert ledger[reply["response_id"]]["model_call"]["tokens"] == {"input": usage["prompt_tokens"], "output": usage["completion_tokens"], "cache_hit": hit}
    old_ids = set()
    old_paths = list((team / "evidence/raw-runs").glob("*/run/model_calls.jsonl")) + [team / "evidence/reviewer-followup/reasoning/model_calls.jsonl"]
    for path in old_paths:
        previous, _ = base.journal(path, True)
        old_ids.update(e["call_id"] for e in previous if e.get("call_id"))
    assert set(ids).isdisjoint(old_ids)
    rows, details, lengths, used, order = recompute(tasks, calls)
    initial_errors = sum(not r["initial"] for r in rows)
    assert len(used) == len(rows) + 3 * initial_errors
    starts = [r["call_key"] for r in records if r["status"] == "started" and r["call_key"] != failed_key]
    assert starts[:len(order)] == order
    for path in (original / "eval-results.json", continuation / "eval-results.json", continuation / "results.json"):
        if path.exists():
            value = base.load(path)
            saved = value["rows"] if isinstance(value, dict) else value
            checked = {r["id"]: r for r in details}
            if final:
                assert all(r["id"] in checked for r in saved)
                if path == continuation / "results.json":
                    assert len(saved) == len({r["id"] for r in saved}) == 599
                if path == continuation / "eval-results.json":
                    assert len(saved) == len({r["id"] for r in saved}) == 239
            for actual in saved:
                if actual["id"] in checked:
                    assert actual == checked[actual["id"]]
    before = base.load(original / "budget-before.json")
    original_after = base.load(original / "budget-after.json")
    assert before["charged_micro_cny"] == 158788938 and before["unmetered_calls"] == 6
    assert original_after["unmetered_calls"] == 7 and original_after["charged_micro_cny"] == 161713686
    assert not original_after["active_reservations"]
    policy = before["policy"]
    failed_reserve_micro = int(Decimal(policy["input_cny_per_million"]) * policy["max_input_tokens"] + Decimal(policy["output_cny_per_million"]) * policy["max_output_tokens"])
    assert failed_reserve_micro == 2359296
    old_success = [r for r in old_raw if r["status"] == "ok"]
    old_control = sum(r["usage"]["prompt_tokens"] * 2 + r["usage"]["completion_tokens"] * 8 for r in old_success)
    assert len(old_success) == 1071 and original_after["charged_micro_cny"] - before["charged_micro_cny"] == old_control + failed_reserve_micro
    assert old_control == 565452
    totals = {"input_tokens": sum(r["usage"]["prompt_tokens"] for r in calls.values()),
              "output_tokens": sum(r["usage"]["completion_tokens"] for r in calls.values()),
              "cache_hit_tokens": sum(r["usage"].get("prompt_cache_hit_tokens") or 0 for r in calls.values())}
    control_micro = totals["input_tokens"] * 2 + totals["output_tokens"] * 8
    peak_micro = Decimal(totals["cache_hit_tokens"]) * Decimal("0.04") + (totals["input_tokens"] - totals["cache_hit_tokens"]) * 2 + totals["output_tokens"] * 8
    current = base.load(continuation / "budget-after.json" if final else original.parent / "model-budget.json")
    assert current["policy"] == policy and current["unmetered_calls"] == 7
    amended = None
    if final:
        outcome = base.load(continuation / "process-result.json")
        assert outcome["worker_exit_code"] == 0 and outcome["status"] in ("COMPLETED", "AMENDED_COMPLETE_CASES_COMPLETED", "COMPLETED_AMENDED599")
        assert len(rows) == 599 and used == set(calls) and not current["active_reservations"]
        assert current["charged_micro_cny"] - before["charged_micro_cny"] == control_micro + failed_reserve_micro
        assert current["reserved_calls"] - before["reserved_calls"] == current["settled_calls"] - before["settled_calls"] == len(calls) + 1
        amended = statistics(rows, details, lengths, calls)
        assert amended["cell_denominators"]["graph:easy"] == 99 and set(v for k, v in amended["cell_denominators"].items() if k != "graph:easy") == {100}
        metric_path = continuation / "metrics.json"
        if metric_path.exists():
            metric = base.load(metric_path)
            for key, value in amended.items():
                if key in metric:
                    assert metric[key] == value, key
            for key, value in totals.items():
                if key in metric:
                    assert metric[key] == value, key
    assert hashes == {name: base.digest(original / name) for name in ready["sha256"]}
    assert amendment_hashes == {name: base.digest(continuation / name) for name in amendment["sha256"]}
    assert all(base.digest(Path(path)) == expected for path, expected in amendment["original_input_sha256"].items())
    schema_failures = [{"id": item["id"], "arm": arm, "error": item[arm]["feedback"]["error"]}
        for item in details for arm in ARMS if item[arm].get("feedback") and item[arm]["feedback"]["error"] in
        ("json_object_required", "integer_answer_schema", "binary_assignment_schema", "path_schema", "invalid_json_or_schema")]
    bounds = sensitivity(rows) if final else None
    return {"status": "PASS" if final else "PARTIAL", "mode": "FINAL" if final else "LIVE_SNAPSHOT",
        "audit_scope": "AMENDED599_AFTER_TRANSPORT_FAILURE", "protocol_amended_after_transport_failure": True,
        "original_strict600_status": "FAILED", "unchanged_registered600_completed": False,
        "planned_items": 600, "transport_missing_items": 1, "missing_item": FAILED_ITEM, "missing_http_status": 502,
        "missing_initial_never_resent": True, "observed_complete_pairs": len(rows), "amended_expected_complete_pairs": 599,
        "completed_item_denominator": len(rows), "expected_final_denominator": 599,
        "original_complete_rows": len(base.load(original / "eval-results.json")), "unique_successful_responses": len(calls), "unique_failed_requests": 1,
        "all600_oracles_independently_checked": True, "prior156_overlap": 0, "response_ids_prior_overlap": 0,
        "journal_response_1_to_1": not missing and not extra, "pending_calls": len(pending),
        "finish_reason_counts": dict(Counter(r.get("finish_reason") for r in calls.values())), "statistics": amended, "statistics_amended599": amended,
        "schema_failures_scored_in_denominator": schema_failures,
        "missing_pair_worst_case_sensitivity": bounds, "usage": totals,
        "cost": {"successful_usage_peak_rate_CNY": str(peak_micro / 1_000_000), "failed_maximum_retained_charge_CNY": str(Decimal(failed_reserve_micro) / 1_000_000),
            "usage_peak_rate_CNY": str(peak_micro / 1_000_000), "extra_unknown_upper_cny": str(Decimal(failed_reserve_micro) / 1_000_000),
            "control_usage_CNY": str(Decimal(control_micro) / 1_000_000),
            "prior_safe_actual_upper_CNY": "14.578766", "cumulative_safe_actual_upper_CNY": str(Decimal("14.578766") + (peak_micro + failed_reserve_micro) / 1_000_000),
            "safe_success_peak_plus_unknown_upper_CNY": str((peak_micro + failed_reserve_micro) / 1_000_000),
            "successful_control_usage_CNY": str(Decimal(control_micro) / 1_000_000),
            "total_control_expected_CNY": str(Decimal(control_micro + failed_reserve_micro) / 1_000_000),
            "actual_control_delta_CNY": str(Decimal(current["charged_micro_cny"] - before["charged_micro_cny"]) / 1_000_000),
            "control_charge_delta_CNY": str(Decimal(current["charged_micro_cny"] - before["charged_micro_cny"]) / 1_000_000),
            "active_reservations": len(current["active_reservations"]), "historical_unknown_calls_retained": 7,
            "failed_charge_is_conservative_unknown_not_known_actual_fee": True, "final_control_delta_exact": final},
        "original_raw_snapshot": old_meta, "original_journal_snapshot": old_ledger_meta,
        "continuation_raw_snapshot": new_meta, "continuation_journal_snapshot": new_ledger_meta,
        "original_frozen_inputs_unchanged": True, "original_frozen_sha256": hashes,
        "continuation_registered_before_all_new_calls": True, "amendment_frozen_sha256": amendment_hashes,
        "amendment_registration_sha256": base.digest(continuation / "ready.json"),
        "model_calls": 0, "model_api_calls": 0, "network_requests": 0, "not_a_new_complete_agent_workflow": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", required=True, type=Path)
    parser.add_argument("--continuation", required=True, type=Path)
    parser.add_argument("--team", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--final", action="store_true")
    args = parser.parse_args()
    report = audit(args.original.resolve(), args.continuation.resolve(), args.team.resolve(), args.final)
    report["checked_at_utc"] = datetime.now(timezone.utc).isoformat()
    report["auditor_sha256"] = base.digest(Path(__file__))
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("status", "original_strict600_status", "observed_complete_pairs", "unique_successful_responses", "transport_missing_items", "cost")}, ensure_ascii=False))
