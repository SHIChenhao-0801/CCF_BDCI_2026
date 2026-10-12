"""Portable frozen-response reanalysis; no model or network caller exists in this file."""
import argparse
from collections import Counter
from datetime import datetime, timezone, timedelta
import hashlib
import json
import math
import operator
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parent
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
            correct, feedback = score(task, initial["content"])
            assert not correct, "Correct initial must be reused without retries"
            messages += [{"role": "assistant", "content": initial["content"]},
                         {"role": "user", "content": instructions(feedback)[arm]}]
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


def recompute(tasks, calls, missing_ids):
    rows, details, lengths, used, order = [], [], [], set(), []
    for task in tasks:
        if task["id"] in missing_ids:
            continue
        prefix = "7adae0c2cfac:" + task["id"]
        initial = calls.get(prefix + ":initial")
        if initial is None:
            continue
        correct, feedback = score(task, initial["content"])
        needed = ["initial"] + ([] if correct else task["retry_order"])
        if any(prefix + ":" + arm not in calls for arm in needed):
            continue
        retry = instructions(feedback) if not correct else {}
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
            valid, error = score(task, reply["content"])
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
        "accuracies": {a: counts[a] / n for a in ARMS}, "accuracy_wilson_95": {a: wilson(counts[a], n) for a in ARMS},
        "primary_diagnostic_vs_lengthmatched": compare(rows, "lengthmatchedretry"),
        "secondary_diagnostic_vs_generic": compare(rows, "blindretry"),
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
                case = compare(rows + extension, control)
                cases.append({"missing_diagnostic_only": i, "missing_control_only": j, **case})
        observed = compare(rows, control)
        difference = observed["diagnostic_only_correct"] - observed["control_only_correct"]
        result["comparisons"][name] = {"observed_complete_case": observed, "enumerated_possible_missing_outcomes": cases,
            "p_value_range": [min(c["exact_mcnemar_p_two_sided"] for c in cases), max(c["exact_mcnemar_p_two_sided"] for c in cases)],
            "paired_difference_full600_range": [(difference - missing) / 600, (difference + missing) / 600],
            "paired_difference_percentage_point_range": [100 * (difference - missing) / 600, 100 * (difference + missing) / 600]}
    result["marginal_accuracy_full600_ranges"] = {a: [sum(r[a] for r in rows) / 600, (sum(r[a] for r in rows) + missing) / 600] for a in ARMS}
    return result


def usage_totals(records):
    records = tuple(records)
    return {'input_tokens': sum(r['usage']['prompt_tokens'] for r in records),
            'output_tokens': sum(r['usage']['completion_tokens'] for r in records),
            'cache_hit_tokens': sum(r['usage'].get('prompt_cache_hit_tokens') or 0 for r in records)}


def reanalyze():
    manifest = json.loads((ROOT / 'manifest.json').read_text(encoding='utf-8'))
    for name, expected in manifest['file_sha256'].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, 'Frozen reanalysis input changed: ' + name
    bundle = json.loads((ROOT / 'dataset.json').read_text(encoding='utf-8'), object_pairs_hook=unique_object)
    tasks, raw, events = bundle['tasks'], bundle['raw_records'], bundle['resource_events']
    assert len(tasks) == 600 and len({t['id'] for t in tasks}) == 600
    for task in tasks:
        assert fingerprint(task) == task['instance_sha256']
        assert initial_prompt(task) == task['prompt'] and score(task, json.dumps(task['oracle'])) == (True, None)
    calls, groups, per_item = verify_requests(tasks, raw)
    missing = {key.split(':')[1] for key, group in groups.items() if group[-1]['status'] != 'ok'}
    assert len(missing) == 8 and len(per_item) == 600
    ledger = {event['call_id']: event for event in events}
    ids = [record['response_id'] for record in calls.values()]
    assert len(ids) == len(set(ids)) == len(events) == len(ledger) == 1721 and set(ids) == set(ledger)
    for record in calls.values():
        usage = record['usage']
        assert all(type(usage[key]) is int and usage[key] >= 0 for key in ('prompt_tokens', 'completion_tokens'))
        hit = usage.get('prompt_cache_hit_tokens') or 0
        assert type(hit) is int and 0 <= hit <= usage['prompt_tokens']
        assert usage['total_tokens'] == usage['prompt_tokens'] + usage['completion_tokens']
        assert ledger[record['response_id']]['model_call']['tokens'] == {'input': usage['prompt_tokens'], 'output': usage['completion_tokens'], 'cache_hit': hit}
    rows, details, lengths, used, order = recompute(tasks, calls, missing)
    assert len(rows) == 592 and len(used) == 1717 and len(rows) + len(missing) == 600
    stats = statistics(rows, details, lengths, calls)
    sensitivity = missing_sensitivity(rows, len(missing))
    all_usage, scientific_usage = usage_totals(calls.values()), usage_totals(calls[key] for key in used)
    assert stats == bundle['expected_independent_audit']['statistics']
    assert sensitivity == bundle['expected_independent_audit']['missing_pair_worst_case_sensitivity']
    assert all_usage == bundle['expected_independent_audit']['usage_all_successful']
    assert scientific_usage == bundle['expected_independent_audit']['usage_scientific_complete_pairs']
    primary = stats['primary_diagnostic_vs_lengthmatched']
    result = {'method': 'paired_study', 'status': 'completed', 'smoke_test': False,
        'execution_type': 'offline_reanalysis_of_frozen_model_responses', 'new_solver_evaluation': False,
        'planned_items': 600, 'valid_eval_count': 592, 'missing_count': len(missing),
        'primary_verifier_minus_lengthmatched': primary['difference'],
        'exact_primary_mcnemar_p_two_sided': primary['exact_mcnemar_p_two_sided'],
        'baseline_accuracy': stats['accuracies']['initial'], 'generic_accuracy': stats['accuracies']['blindretry'],
        'verifier_accuracy': stats['accuracies']['verifiedretry'], 'lengthmatched_accuracy': stats['accuracies']['lengthmatchedretry'],
        'model_call_count': 0, 'input_tokens': 0, 'output_tokens': 0, 'cache_hit_tokens': 0, 'network_requests': 0,
        'historical_actual_model_call_count': len(calls), 'historical_scientific_model_call_count': len(used),
        'historical_partial_item_successful_call_count': len(calls) - len(used),
        'historical_usage_all_successful': all_usage, 'historical_usage_scientific_complete_pairs': scientific_usage,
        'missing_ids': sorted(missing), 'missing_pair_worst_case_sensitivity': sensitivity,
        'no_missing_at_random_assumption': True, 'unchanged_registered600_completed': False,
        'historical_timing_by_stage': bundle['metadata']['timing_by_stage'],
        'historical_resource_accounting': bundle['metadata']['resource_accounting'],
        'prior120_separate_context': bundle['metadata']['prior120_separate_context'],
        'claim_scope': 'One model synthetic task repair; disclosed missingness; decoded-length NOT token-equivalent; no pooling with120/24; current Execution reuses responses',
        **stats}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--method', choices=['paired_study'], default='paired_study')
    parser.add_argument('--smoke-test', action='store_true')
    parser.add_argument('--run-eval', action='store_true', help='Offline reanalysis only; never requests model replies')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--usage-ledger', type=Path)
    parser.add_argument('--task-id')
    parser.add_argument('--node-ref')
    args = parser.parse_args()
    started = time.perf_counter()
    result = reanalyze()
    result['smoke_test'] = args.smoke_test or not (args.output or args.run_eval)
    result['elapsed_seconds'] = time.perf_counter() - started
    result['usage_ledger_written'] = False
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        if not args.smoke_test:
            (args.output.parent / 'reanalysis_summary.md').write_text(
                '# Frozen-response reanalysis\n\nExecution used zero new solver/model calls. Planned600, complete592, missing8.\n'
                + 'Correct initial/generic/diagnostic/length: ' + '/'.join(str(result['correct_counts'][arm]) for arm in ARMS)
                + '\nPrimary diagnostic versus decoded-length control: ' + json.dumps(result['primary_diagnostic_vs_lengthmatched'])
                + '\nHistorical1721 replies,1717 scientific replies,4 cost-only partial replies.\n'
                + 'Report actual cell denominators,token confound,missing sensitivity,previous120 separately,and hard-case failures.\n', encoding='utf-8')
    print(json.dumps({key: result[key] for key in ('method', 'status', 'smoke_test', 'execution_type', 'valid_eval_count',
          'missing_count', 'model_call_count', 'historical_actual_model_call_count', 'elapsed_seconds')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
