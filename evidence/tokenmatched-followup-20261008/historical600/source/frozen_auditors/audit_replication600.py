"""Independent stdlib-only audit; no caller imports, network, credentials or source writes."""
import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import itertools
import json
import math
import operator
from pathlib import Path

ARMS = ("initial", "blindretry", "verifiedretry", "lengthmatchedretry")
RECONSIDER = "Reconsider your previous answer and return only the requested final JSON object."
NEUTRAL = "Check your answer carefully. "


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=unique_object)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def journal(path, final):
    records, truncated = [], 0
    data = path.read_bytes() if path.exists() else b""
    lines = data.splitlines()
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line, object_pairs_hook=unique_object))
        except ValueError:
            if final or index != len(lines) - 1:
                raise
            truncated += 1
    return records, {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data), "records": len(records), "partial_last_line": truncated}


def fingerprint(task):
    spec = dict(task["spec"])
    if task["family"] == "sat":
        spec["clauses"] = sorted({tuple(sorted(clause)) for clause in spec["clauses"]})
    elif task["family"] == "graph":
        spec["edges"] = sorted((min(a, b), max(a, b), w) for a, b, w in spec["edges"])
    return hashlib.sha256(json.dumps([task["family"], spec], sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def distances(spec):
    n = spec["n"]
    table = [[0 if a == b else math.inf for b in range(n)] for a in range(n)]
    for a, b, weight in spec["edges"]:
        assert 0 <= a < b < n and type(weight) is int and weight > 0
        table[a][b] = table[b][a] = min(table[a][b], weight)
    for via in range(n):
        for a in range(n):
            for b in range(n):
                table[a][b] = min(table[a][b], table[a][via] + table[via][b])
    return table


def score(task, content):
    try:
        answer = json.loads(content, object_pairs_hook=unique_object)
        spec, family = task["spec"], task["family"]
        if not isinstance(answer, dict):
            return False, {"error": "json_object_required"}
        if family == "arithmetic":
            if set(answer) != {"answer"} or type(answer["answer"]) is not int:
                return False, {"error": "integer_answer_schema"}
            expected = spec["start"]
            for symbol, operand in spec["ops"]:
                expected = {"+": operator.add, "-": operator.sub, "*": operator.mul}[symbol](expected, operand)
            if answer["answer"] != expected:
                return False, {"error": "sequential_arithmetic_mismatch"}
        elif family == "sat":
            bits = answer.get("assignment")
            if set(answer) != {"assignment"} or not isinstance(bits, list) or len(bits) != spec["n"] or any(type(bit) is not int or bit not in (0, 1) for bit in bits):
                return False, {"error": "binary_assignment_schema"}
            for index, clause in enumerate(spec["clauses"], 1):
                if not any(bool(bits[abs(lit) - 1]) == (lit > 0) for lit in clause):
                    return False, {"error": "clause_unsatisfied", "clause_index": index}
        else:
            path = answer.get("path")
            if set(answer) != {"path", "cost"} or not isinstance(path, list) or len(path) < 2 or type(answer["cost"]) is not int or any(type(v) is not int or v not in range(spec["n"]) for v in path):
                return False, {"error": "path_schema"}
            if path[0] != spec["source"] or path[-1] != spec["target"] or len(set(path)) != len(path):
                return False, {"error": "path_endpoints_or_repetition"}
            edges = {(a, b): weight for a, b, weight in spec["edges"]}
            edges.update({(b, a): weight for a, b, weight in spec["edges"]})
            if any((a, b) not in edges for a, b in zip(path, path[1:])):
                return False, {"error": "nonexistent_edge"}
            cost = sum(edges[a, b] for a, b in zip(path, path[1:]))
            if answer["cost"] != cost:
                return False, {"error": "path_cost_mismatch"}
            if cost != distances(spec)[spec["source"]][spec["target"]]:
                return False, {"error": "path_not_shortest"}
        return True, None
    except (ValueError, TypeError, KeyError):
        return False, {"error": "invalid_json_or_schema"}


def instructions(feedback):
    diagnostic = RECONSIDER + "\nDeterministic checker feedback: " + json.dumps(feedback, separators=(",", ":"))
    repetitions, remainder = divmod(len(diagnostic) - len(RECONSIDER) - 1, len(NEUTRAL))
    return {"blindretry": RECONSIDER, "verifiedretry": diagnostic,
            "lengthmatchedretry": RECONSIDER + "\n" + NEUTRAL * repetitions + "." * remainder}


def initial_prompt(task):
    spec = task["spec"]
    if task["family"] == "arithmetic":
        wording = 'Apply ops sequentially to start, using exact integer arithmetic. Return {"answer": integer}.'
        ordered = {"start": spec["start"], "ops": spec["ops"]}
    elif task["family"] == "sat":
        wording = 'Find any satisfying assignment for this CNF. Each clause is OR, clauses combine by AND, positive literals mean x_i and negative literals mean NOT x_i. Return {"assignment": [0 or 1 for x_1 through x_n]}. All instances are satisfiable.'
        ordered = {"n": spec["n"], "clauses": spec["clauses"]}
    else:
        wording = 'Find a shortest simple path from source to target in this undirected positive-weight graph. Each edge is [a,b,weight]. Return {"path": [integer vertices], "cost": integer total weight}. Any tied optimum is accepted.'
        ordered = {"n": spec["n"], "edges": spec["edges"], "source": spec["source"], "target": spec["target"]}
    return wording + "\nInput: " + json.dumps(ordered, separators=(",", ":")) + "\nOutput only the requested JSON object, without code fences or other keys."


def compare(rows, control):
    better = sum(r["verifiedretry"] and not r[control] for r in rows)
    worse = sum(r[control] and not r["verifiedretry"] for r in rows)
    n = better + worse
    p = min(1.0, 2 * sum(math.comb(n, k) for k in range(min(better, worse) + 1)) / 2 ** n) if n else 1.0
    return {"diagnostic_only_correct": better, "control_only_correct": worse,
            "difference": (better - worse) / len(rows), "exact_mcnemar_p_two_sided": p}


def wilson(count, n):
    z, proportion = 1.959963984540054, count / n
    denominator = 1 + z * z / n
    center = (proportion + z * z / (2 * n)) / denominator
    radius = z * math.sqrt(proportion * (1 - proportion) / n + z * z / (4 * n * n)) / denominator
    return [max(0, center - radius), min(1, center + radius)]


def audit(source, team, final):
    ready, manifest, tasks = (load(source / name) for name in ("ready.json", "manifest.json", "dataset.json"))
    frozen_before = {name: digest(source / name) for name in ready["sha256"]}
    assert frozen_before == ready["sha256"]
    assert len(tasks) == manifest["n"] == 600
    raw_hash = digest(source / "dataset.json")
    lf_hash = hashlib.sha256((source / "dataset.json").read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    assert raw_hash == "0241523b60df12349ad2124b2a3d94a1eb145e29c26e7590609c5a5bd96c56df"
    assert lf_hash == manifest["dataset_sha256"] == "7adae0c2cfac2445ce9ee6c8ccb50585060e3d5d0278158a94e34d6ba442c23f"
    old_source = team / "code/research_project/reviewer_followup_reasoning"
    prior = load(old_source / "legacy-dataset.json") + load(old_source / "dataset.json")
    assert len(prior) == len({fingerprint(t) for t in prior}) == 156
    assert all(digest(Path(entry["path"])) == entry["sha256"] for entry in load(source / "original-inputs-before.json"))
    overlap = {"id": len({t["id"] for t in tasks} & {t["id"] for t in prior}),
               "canonical": len({fingerprint(t) for t in tasks} & {fingerprint(t) for t in prior}),
               "exact_prompt": len({t["prompt"] for t in tasks} & {t["prompt"] for t in prior})}
    assert not any(overlap.values())
    assert len({t["id"] for t in tasks}) == len({fingerprint(t) for t in tasks}) == len({t["prompt"] for t in tasks}) == 600
    cells = Counter((t["family"], t["difficulty"]) for t in tasks)
    assert len(cells) == 6 and set(cells.values()) == {100}
    assert set(Counter(tuple(t["retry_order"]) for t in tasks).values()) == {100}
    for f, d in cells:
        distribution = Counter(tuple(t["retry_order"]) for t in tasks if t["family"] == f and t["difficulty"] == d)
        assert len(distribution) == 6 and set(distribution.values()) == {16, 17}
    for task in tasks:
        assert fingerprint(task) == task["instance_sha256"]
        assert initial_prompt(task) == task["prompt"]
        assert score(task, json.dumps(task["oracle"])) == (True, None)
        if task["family"] == "sat":
            spec = task["spec"]
            assert any(all(any(bool(bits[abs(lit)-1]) == (lit > 0) for lit in clause) for clause in spec["clauses"])
                       for bits in itertools.product((0, 1), repeat=spec["n"]))
    records, call_snapshot = journal(source / "calls.jsonl", final)
    events, ledger_snapshot = journal(source / "model_calls.jsonl", final)
    groups = {}
    for record in records:
        groups.setdefault(record["call_key"], []).append(record)
    calls = {}
    unresolved, errors = [], []
    registration = datetime.fromisoformat(ready["ready_before_first_call_utc"])
    for key, group in groups.items():
        assert group[0]["status"] == "started" and len(group) <= 2
        assert datetime.fromisoformat(group[0]["started_at"]) > registration
        if len(group) == 2:
            assert group[0]["request"] == group[1]["request"]
            if group[1]["status"] == "ok":
                calls[key] = group[1]
            else:
                errors.append(key)
        else:
            unresolved.append(key)
    ids = [c.get("response_id") for c in calls.values()]
    assert all(isinstance(value, str) and value for value in ids) and len(ids) == len(set(ids))
    event_map = {event["call_id"]: event for event in events}
    assert len(events) == len(event_map) and len({e["event_id"] for e in events}) == len(events)
    missing_events, extra_events = set(ids) - set(event_map), set(event_map) - set(ids)
    if final:
        assert not missing_events and not extra_events and not unresolved and not errors
    for c in calls.values():
        usage = c["usage"]
        assert all(type(usage.get(k)) is int and usage[k] >= 0 for k in ("prompt_tokens", "completion_tokens"))
        hit = usage.get("prompt_cache_hit_tokens") or 0
        assert type(hit) is int and 0 <= hit <= usage["prompt_tokens"]
        assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]
        assert usage.get("prompt_cache_miss_tokens", usage["prompt_tokens"] - hit) == usage["prompt_tokens"] - hit
        if c["response_id"] in event_map:
            event = event_map[c["response_id"]]
            assert event["model_call"]["tokens"] == {"input": usage["prompt_tokens"], "output": usage["completion_tokens"], "cache_hit": hit}
            assert event["model_call"]["status"] == "succeeded" and event["model_call"]["call_count"] == 1
    prior_files = list((team / "evidence/raw-runs").glob("*/run/model_calls.jsonl"))
    prior_files += [team / "evidence/reviewer-followup/reasoning/model_calls.jsonl"]
    old_ids, old_journals = set(), []
    for path in prior_files:
        old_events, metadata = journal(path, True)
        old_ids.update(e.get("call_id") for e in old_events if e.get("call_id"))
        old_journals.append({"path": str(path.relative_to(team)), **metadata})
    assert set(ids).isdisjoint(old_ids) and set(event_map).isdisjoint(old_ids)
    rows, details, lengths, used, schema_failures = [], [], [], set(), []
    expected_order = []
    for task in tasks:
        prefix = lf_hash[:12] + ":" + task["id"]
        initial = calls.get(prefix + ":initial")
        if initial is None:
            break
        initial_ok, feedback = score(task, initial["content"])
        needed = ["initial"] + ([] if initial_ok else task["retry_order"])
        if any(prefix + ":" + arm not in calls for arm in needed):
            break
        row = {"id": task["id"], "family": task["family"], "difficulty": task["difficulty"]}
        request_lengths, arms = {}, {}
        retry = instructions(feedback) if not initial_ok else {}
        for arm in ARMS:
            key = prefix + ":" + ("initial" if initial_ok else arm)
            reply = calls[key]
            expected_messages = [{"role": "user", "content": task["prompt"]}]
            if arm != "initial" and not initial_ok:
                expected_messages += [{"role": "assistant", "content": initial["content"]}, {"role": "user", "content": retry[arm]}]
            expected_payload = {"model": "deepseek-flash", "messages": expected_messages, "max_tokens": 2048,
                                "temperature": 0, "stream": False, "thinking": {"type": "disabled"}}
            assert reply["request"] == expected_payload
            correct, error = score(task, reply["content"])
            row[arm] = correct
            used.add(key)
            arms[arm] = {"call_key": key, "correct": correct, "feedback": error}
            if arm != "initial":
                arms[arm]["reused_initial"] = initial_ok
                if initial_ok:
                    del arms[arm]["feedback"]
            if error and error["error"] in ("json_object_required", "integer_answer_schema", "binary_assignment_schema", "path_schema", "invalid_json_or_schema"):
                schema_failures.append({"id": task["id"], "arm": arm, "error": error["error"]})
            if arm != "initial" and not initial_ok:
                request_lengths[arm] = {"content_characters": sum(len(m["content"]) for m in expected_messages),
                                        "content_utf8_bytes": sum(len(m["content"].encode()) for m in expected_messages)}
                arms[arm]["request_lengths"] = request_lengths[arm]
        if not initial_ok:
            assert request_lengths["verifiedretry"] == request_lengths["lengthmatchedretry"]
            lengths.append({"id": task["id"], "decoded_content_lengths": request_lengths["verifiedretry"], "matched_lengths_equal": True,
                            "diagnostic_prompt_tokens": calls[prefix+":verifiedretry"]["usage"]["prompt_tokens"],
                            "matched_prompt_tokens": calls[prefix+":lengthmatchedretry"]["usage"]["prompt_tokens"]})
        expected_order.extend(prefix + ":" + arm for arm in needed)
        rows.append(row)
        details.append({"id": task["id"], "family": task["family"], "difficulty": task["difficulty"], "retry_order": task["retry_order"], **arms})
    starts = [r["call_key"] for r in records if r["status"] == "started"]
    assert starts[:len(expected_order)] == expected_order
    n = len(rows)
    counts = {arm: sum(row[arm] for row in rows) for arm in ARMS}
    assert len(used) == n + 3 * (n - counts["initial"])
    if final:
        assert n == 600 and used == set(calls) and len(records) == 2 * len(calls)
    published_checks = {}
    for name in ("eval-results.json", "results.json"):
        path = source / name
        if path.exists():
            try:
                published = load(path)
            except ValueError:
                if final:
                    raise
                published_checks[name] = "PARTIAL_WRITE"
                continue
            stored = published["rows"] if isinstance(published, dict) else published
            assert len(stored) <= len(tasks)
            for expected, actual in zip(details, stored):
                assert expected == actual
            if final:
                assert len(stored) == n
            published_checks[name] = {"rows_checked": min(len(stored), n), "stored_rows": len(stored)}
    totals = {"input_tokens": sum(c["usage"]["prompt_tokens"] for c in calls.values()),
              "output_tokens": sum(c["usage"]["completion_tokens"] for c in calls.values()),
              "cache_hit_tokens": sum(c["usage"].get("prompt_cache_hit_tokens") or 0 for c in calls.values())}
    control_micro = totals["input_tokens"] * 2 + totals["output_tokens"] * 8
    peak_micro = Decimal(totals["cache_hit_tokens"]) * Decimal("0.04") + (totals["input_tokens"] - totals["cache_hit_tokens"]) * 2 + totals["output_tokens"] * 8
    budget_before = load(source / "budget-before.json")
    assert (budget_before["charged_micro_cny"], budget_before["reserved_calls"], budget_before["settled_calls"], budget_before["unmetered_calls"]) == (158788938, 2526, 2526, 6)
    assert budget_before["policy"]["budget_cny"] == "176.785881" and not budget_before["active_reservations"]
    budget_path = source / "budget-after.json" if final else source.parent / "model-budget.json"
    budget = load(budget_path)
    charge_delta = budget["charged_micro_cny"] - budget_before["charged_micro_cny"]
    active = budget["active_reservations"]
    assert budget["policy"] == budget_before["policy"] and budget["unmetered_calls"] == 6
    if final:
        assert not active and charge_delta == control_micro
        assert budget["reserved_calls"] - 2526 == budget["settled_calls"] - 2526 == len(calls)
    statistics = {"correct_counts": counts, "valid_eval_count": n,
        "cell_counts": {f+":"+d: {arm: sum(r[arm] for r in rows if r["family"] == f and r["difficulty"] == d) for arm in ARMS}
                        for f, d in sorted(cells)},
        "cell_denominators": {f+":"+d: sum(r["family"] == f and r["difficulty"] == d for r in rows) for f, d in sorted(cells)},
        "initial_errors_repaired": {a: sum(not r["initial"] and r[a] for r in rows) for a in ARMS[1:]},
        "actual_retry_orders": dict(Counter(",".join(r["retry_order"]) for r in details if not r["initial"]["correct"])),
        "error_class_counts": {a: dict(Counter(r[a]["feedback"]["error"] for r in details if r[a].get("feedback"))) for a in ARMS},
        "diagnostic_minus_matched_prompt_tokens": [v["diagnostic_prompt_tokens"] - v["matched_prompt_tokens"] for v in lengths],
        "length_match_audit": lengths}
    statistics["arm_usage_excludes_shared_initial"] = {}
    for arm in ARMS:
        actual = [calls[r[arm]["call_key"]] for r in details if arm == "initial" or not r["initial"]["correct"]]
        statistics["arm_usage_excludes_shared_initial"][arm] = {"call_count": len(actual),
            "input_tokens": sum(c["usage"]["prompt_tokens"] for c in actual),
            "output_tokens": sum(c["usage"]["completion_tokens"] for c in actual),
            "client_call_seconds": sum(c["latency_seconds"] for c in actual)}
    if n and final:
        statistics.update(primary_diagnostic_vs_lengthmatched=compare(rows, "lengthmatchedretry"),
                          secondary_diagnostic_vs_generic=compare(rows, "blindretry"),
                          accuracies={a: counts[a] / n for a in ARMS}, accuracy_wilson_95={a: wilson(counts[a], n) for a in ARMS})
    if final:
        outcome = load(source / "process-result.json")
        assert outcome["status"] == "COMPLETED" and outcome["worker_exit_code"] == 0
        metrics = load(source / "metrics.json")
        assert metrics["smoke_test"] is False and metrics["status"] == "completed"
        for key, value in statistics.items():
            if key != "cell_denominators":
                assert metrics[key] == value, key
        assert metrics["model_call_count"] == len(calls)
        for key, value in totals.items():
            assert metrics[key] == value
    frozen_after = {name: digest(source / name) for name in ready["sha256"]}
    assert frozen_before == frozen_after
    return {"status": "PASS" if final else "PARTIAL", "mode": "FINAL" if final else "LIVE_SNAPSHOT",
        "model_api_calls": 0, "network_requests": 0, "expected_final_denominator": 600,
        "completed_item_denominator": n, "partial_results_not_full600": not final,
        "source_raw_dataset_sha256": raw_hash, "source_LF_call_key_sha256": lf_hash,
        "ready_precedes_all_observed_calls": True, "600_oracles_independently_checked": True, "prior156_overlap": overlap,
        "response_ids_disjoint_from_old_main_and120": True, "old_ledger_evidence": old_journals,
        "unique_successful_responses": len(calls), "complete_item_call_arithmetic": len(used),
        "incomplete_item_successful_calls": len(calls) - len(used), "unresolved_calls": len(unresolved), "failed_calls": len(errors),
        "journal_response_1_to_1": not missing_events and not extra_events,
        "missing_usage_events": len(missing_events), "extra_usage_events": len(extra_events),
        "finish_reason_counts": dict(Counter(c.get("finish_reason") for c in calls.values())),
        "schema_failures_scored_in_denominator": schema_failures, "published_rows_checks": published_checks,
        "statistics": statistics, "usage": totals, "call_snapshot": call_snapshot, "ledger_snapshot": ledger_snapshot,
        "cost": {"rates_CNY_per_million": {"cache_hit": "0.04", "uncached_input": "2", "output": "8"},
                 "usage_peak_rate_CNY": str(peak_micro / 1_000_000), "control_usage_CNY": str(Decimal(control_micro) / 1_000_000),
                 "control_charge_delta_CNY": str(Decimal(charge_delta) / 1_000_000), "active_reservations": len(active),
                 "control_charge_not_actual_spend_while_active": bool(active), "historical_unknown_calls_retained": 6,
                 "final_control_delta_exactly_matches_usage": final and charge_delta == control_micro},
        "frozen_inputs_unchanged": True, "frozen_before": frozen_before, "frozen_after": frozen_after,
        "claim_scope": "Registered after observed120, fixed600 independent operator replication; partial descriptive results are not full600 or a new complete Agent workflow"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--team", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--final", action="store_true")
    args = parser.parse_args()
    report = audit(args.source.resolve(), args.team.resolve(), args.final)
    report["checked_at_utc"] = datetime.now(timezone.utc).isoformat()
    report["auditor_sha256"] = digest(Path(__file__))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("status", "completed_item_denominator", "unique_successful_responses", "finish_reason_counts", "usage", "cost", "frozen_inputs_unchanged")}, ensure_ascii=False))
