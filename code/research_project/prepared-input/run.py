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


def reanalyze600():
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



PREFIX = "tokenmatched-followup-20261008:"
LOCAL_CODES = {'RSI_MODEL_BUDGET_EXCEEDED', 'RSI_REQUEST_DEADLINE', 'RSI_LEDGER_PERSIST_FAILED', 'RSI_REQUEST_PAUSED', 'FOLLOWUP_SETTLED_CONTROL_CAP_REACHED', 'RSI_REQUEST_POLICY_INVALID', 'INVALID_RESPONSE_OR_ACCOUNTING'}
from math import comb
import itertools

def expected_payload(case, phase, arm, units):
    assert arm in ('full', 'neutral', 'coarse') and type(units) is int and 0 <= units <= 64
    feedback = {} if arm == 'neutral' else dict(case['initial_feedback'])
    if arm == 'coarse':
        assert case['task']['family'] == 'sat' and 'clause_index' in feedback
        del feedback['clause_index']
    content = RECONSIDER + '\nDeterministic checker feedback: ' + json.dumps(feedback, separators=(',', ':'))
    content += '\nInert padding; ignore this line:' + ' a' * units
    return {'model': 'deepseek-flash', 'messages': [{'role': 'user', 'content': case['task']['prompt']},
        {'role': 'assistant', 'content': case['initial_content']}, {'role': 'user', 'content': content}],
        'max_tokens': 1 if phase == 'probe' else 2048, 'temperature': 0, 'stream': False, 'thinking': {'type': 'disabled'}}

def parse_journal(events):
    records, starts = {}, []
    response_ids = set()
    for event in events:
        key, status = event['call_key'], event['status']
        if status == 'started':
            assert not any(row['status']=='local_stop' for row in records.values()), 'Request admitted after retained globalSTOP'
            assert key not in records, 'Duplicate/admitted request identity: ' + key
            starts.append(key)
        else:
            assert key in records and records[key]['status'] == 'started', 'Terminal event without one start'
            assert event['request'] == records[key]['request']
            assert status in ('ok', 'error', 'local_stop')
        if status == 'ok':
            usage = event['usage']
            assert type(usage['prompt_tokens']) is int and usage['prompt_tokens'] > 0
            assert type(usage['completion_tokens']) is int and 0 <= usage['completion_tokens'] <= event['request']['max_tokens']
            assert usage['total_tokens'] == usage['prompt_tokens'] + usage['completion_tokens']
            raw_cache = usage.get('prompt_cache_hit_tokens')
            cache = 0 if raw_cache is None else raw_cache
            assert type(cache) is int and 0 <= cache <= usage['prompt_tokens']
            assert event['response_id'] not in response_ids
            response_ids.add(event['response_id'])
        elif status == 'local_stop':
            code = event['code'].split(':')[0]
            assert code in LOCAL_CODES, 'Unclassified local policy/accounting failure'
        records[key] = event
    return records, starts

class ReplayHalt(Exception):
    def __init__(self, kind, reason):
        self.kind, self.reason = kind, reason
        super().__init__(reason)

def inspect_case(case, records, calibration_only):
    """Independent transcript verifier: no probe contents or runner summaries read."""
    used, target, padding, observations = [], None, {}, {}
    coarse_missing = None
    def take(phase, arm, units):
        key = PREFIX + case['task']['id'] + ':' + phase + ':' + arm
        if phase == 'probe':
            key += ':pad' + str(units)
        if key not in records:
            raise ReplayHalt('unattempted_or_interrupted', 'next_not_attempted:' + key)
        record = records[key]
        assert record['request'] == expected_payload(case, phase, arm, units), 'Request/history/feedback contract changed: ' + key
        used.append(key)
        if record['status'] == 'local_stop':
            raise ReplayHalt('local_stop', record['code'])
        if record['status'] == 'started':
            raise ReplayHalt('pending_unknown', 'started_without_terminal:' + key)
        if record['status'] != 'ok':
            raise ReplayHalt('missing', 'failed_or_unknown:' + key)
        return record['usage']['prompt_tokens'], record

    def search(arm, zero=None):
        pairs = [] if zero is None else [(0, zero)]
        n = 0
        for _ in range(5):
            if zero is None or len(pairs) > 1 or n != 0:
                count, _ = take('probe', arm, n)
                pairs.append((n, count))
            else:
                count = zero
            if count == target:
                observations[arm] = pairs
                return n
            history = [(old_n, old_count) for old_n, old_count in pairs[:-1] if old_count != count]
            if history:
                a, b = history[-1]
                proposal = round(n + (target - count) * (n - a) / (count - b))
            else:
                proposal = n + target - count
            if proposal < 0 or proposal > 64 or proposal in {unit for unit, _ in pairs}:
                observations[arm] = pairs
                raise ReplayHalt('calibration_nonmatch', 'bounded_no_match:' + arm)
            n = proposal
            zero = None
        # One pre-existing zero-padding probe plus at most4new probes.
        observations[arm] = pairs
        raise ReplayHalt('calibration_nonmatch', 'bounded_no_match:' + arm)

    try:
        order = [arm for arm in case['retry_order'] if arm != 'coarse']
        zero = {arm: take('probe', arm, 0)[0] for arm in order}
        target = max(zero.values()) + 4
        for arm in order:
            padding[arm] = search(arm, zero[arm])
        if 'coarse' in case['retry_order']:
            try:
                padding['coarse'] = search('coarse')
            except ReplayHalt as error:
                if error.kind != 'calibration_nonmatch' or calibration_only:
                    raise
                coarse_missing = error.reason
        if calibration_only:
            result = {'status': 'matched_probe_only', 'target_prompt_tokens': target, 'padding_units': padding}
        else:
            finals = {}
            for arm in case['retry_order']:
                if arm not in padding:
                    continue
                count, record = take('final', arm, padding[arm])
                if count != target:
                    if arm == 'coarse':
                        coarse_missing = 'final_token_drift:coarse'
                        continue
                    raise ReplayHalt('missing', 'final_token_drift:' + arm)
                finals[arm] = record
            result = {'status': 'complete_primary_pair', 'target_prompt_tokens': target, 'padding_units': padding,
                'primary_records': {arm: finals[arm] for arm in ('full', 'neutral')},
                'coarse_record': finals.get('coarse'), 'coarse_missing_reason': coarse_missing,
                'SAT_ablation_status': ('missing' if coarse_missing else 'complete') if 'coarse' in case['retry_order'] else 'not_applicable'}
    except ReplayHalt as error:
        result = {'status': error.kind, 'reason': error.reason, 'target_prompt_tokens': target,
            'padding_units': padding, 'coarse_missing_reason': coarse_missing}
    result.update(id=case['task']['id'], checked_keys=used, probe_observations=observations)
    return result

def paired(pairs, planned):
    n = len(pairs)
    better = sum(a and not b for a, b in pairs)
    worse = sum(b and not a for a, b in pairs)
    d = better + worse
    p = min(1., 2 * sum(comb(d, k) for k in range(min(better, worse) + 1)) / 2 ** d) if d else 1.
    return {'planned': planned, 'valid': n, 'full_only_correct': better, 'control_only_correct': worse,
        'difference': (better - worse) / n if n else None, 'exact_two_sided_McNemar': p if n else None,
        'planned_possible_outcome_bounds_not_CI': [(better-worse-(planned-n))/planned, (better-worse+planned-n)/planned]}

def check_usage_ledger(ledger, successful):
    assert len({event['call_id'] for event in ledger}) == len(ledger)
    assert {event['call_id'] for event in ledger} == successful.keys(), 'Successful response missing or duplicated in usage ledger'
    for event in ledger:
        record = successful[event['call_id']]
        usage = record['usage']
        assert event['call_key']==record['call_key']
        assert event['model_call']['model']==record['request']['model']
        assert event['model_call']['status']=='succeeded' and event['model_call']['call_count']==1
        assert event['model_call']['tokens']=={'input':usage['prompt_tokens'], 'output':usage['completion_tokens'], 'cache_hit':usage.get('prompt_cache_hit_tokens') or 0}
        assert event['provenance']==('calibration_probe' if ':probe:' in event['call_key'] else 'fresh_retry_followup')

def replay_followup(bundle):
    followup = bundle.get("tokenmatched_followup")
    if followup is None:
        raise RuntimeError("NOT_READY_NO_API: sealed full-study evidence is absent; calibration-only is not an efficacy result")
    cases = followup["cases"]["cases"]
    _, old_groups, _ = verify_requests(bundle["tasks"], bundle["raw_records"])
    old_missing = {key.split(":")[1] for key, group in old_groups.items() if group[-1]["status"] != "ok"}
    initials = {r["call_key"].split(":")[1]: r for r in bundle["raw_records"] if r["status"] == "ok" and r["call_key"].endswith(":initial")}
    expected = []
    for task in bundle["tasks"]:
        if task["id"] in old_missing:
            continue
        initial = initials[task["id"]]
        correct, feedback = score(task, initial["content"])
        if not correct:
            expected.append({"task": dict(task), "initial_content": initial["content"], "initial_feedback": feedback,
                "historical_initial_call_key": initial["call_key"], "historical_initial_response_id": initial["response_id"],
                "historical_initial_request": initial["request"]})
    expected.sort(key=lambda c: (c["task"]["family"], c["task"]["difficulty"], hashlib.sha256(("tokenmatched-followup-order-v1:" + c["task"]["id"]).encode()).hexdigest()))
    indices = {2: 0, 3: 0}
    for case in expected:
        localized = case["task"]["family"] == "sat" and "clause_index" in case["initial_feedback"]
        choices = list(itertools.permutations(("full", "neutral", "coarse"))) if localized else [("full", "neutral"), ("neutral", "full")]
        size = 3 if localized else 2
        case["retry_order"] = list(choices[indices[size] % len(choices)])
        indices[size] += 1
        case["historical_retry_order"] = case["task"].pop("retry_order")
    assert cases == expected and len(cases) == 375 and indices[3] == 166
    records, starts = parse_journal(followup["raw_records"])
    successful = {r["response_id"]: r for r in records.values() if r["status"] == "ok"}
    assert set(initials[r["task"]["id"]]["response_id"] for r in cases).isdisjoint(successful)
    check_usage_ledger(followup["resource_events"], successful)
    inspected = [inspect_case(case, records, False) for case in cases]
    assert {key for item in inspected for key in item["checked_keys"]} == records.keys()
    for item in inspected:
        assert [key for key in starts if key in set(item["checked_keys"])] == item["checked_keys"]
    primary, ablation = [], []
    for case, item in zip(cases, inspected):
        if item["status"] != "complete_primary_pair":
            continue
        task = case["task"]
        full, neutral = (score(task, item["primary_records"][arm]["content"])[0] for arm in ("full", "neutral"))
        primary.append((full, neutral))
        if item["SAT_ablation_status"] == "complete":
            ablation.append((full, score(task, item["coarse_record"]["content"])[0]))
    usage = {"input": sum(r["usage"]["prompt_tokens"] for r in successful.values()),
        "output": sum(r["usage"]["completion_tokens"] for r in successful.values()),
        "cache_hit": sum(r["usage"].get("prompt_cache_hit_tokens") or 0 for r in successful.values())}
    expected_audit = followup["independent_audit"]
    result = {"primary": paired(primary, 375), "exploratory_SAT_ablation": paired(ablation, 166),
        "phase_state_counts": dict(Counter(item["status"] for item in inspected)), "usage": usage,
        "actual_request_starts": len(starts), "actual_successful_responses": len(successful)}
    assert all(result[key] == expected_audit[key] for key in result)
    result.update(scope="conditional followup on historical initial errors; no new independent cohort; no pooling with600/120",
        final_input_counts_verified_equal=True, zero_new_model_requests_in_current_Execution=True,
        probe_usage_is_counted=True, probe_content_not_scored=True,
        budget=expected_audit["budget"], outcome=expected_audit["outcome"],
        source_sha256=followup["source_sha256"])
    if followup.get("whole_study_resource_facts"):
        resources = followup["whole_study_resource_facts"]
        assert resources["actual_request_starts"]==len(starts) and resources["actual_successful_responses"]==len(successful)
        result["whole_study_resource_facts"] = resources
    if followup.get("posthoc_description"):
        description = followup["posthoc_description"]
        for name,pairs,planned in (("primary_aggregate",primary,375),("SAT_aggregate",ablation,166)):
            actual={"planned":planned,"valid":len(pairs),"missing":planned-len(pairs),
                "full_correct":sum(a for a,b in pairs),"other_correct":sum(b for a,b in pairs),
                "full_only_correct":sum(a and not b for a,b in pairs),"other_only_correct":sum(b and not a for a,b in pairs),
                "both_correct":sum(a and b for a,b in pairs),"both_wrong":sum(not a and not b for a,b in pairs)}
            assert description[name]==actual, "Posthoc descriptive mask/count contradicts raw outcomes"
        result["posthoc_description"] = description
    return result


def reanalyze():
    result = reanalyze600()
    bundle = json.loads((ROOT / "dataset.json").read_text(encoding="utf-8"), object_pairs_hook=unique_object)
    if bundle.get("independent_new_holdout") is None:
        raise RuntimeError("NOT_READY_NO_API: independently audited new240 holdout is absent; no invented primary metrics")
    result["tokenmatched_followup"] = replay_followup(bundle)
    result["independent_new_holdout"] = replay_holdout(bundle)
    result["primary_evidence_group"] = "independent_new_holdout"
    result["existing_host_table_figure_group"] = "original600_complete592_secondary_context"
    result["execution_type"] = "offline_reanalysis_of_three_separate_frozen_studies"
    return result


import heapq
import random
from types import SimpleNamespace
HOLDOUT_BASE_CODE = 'def expected_payload(case, phase, arm, units):\n    assert arm in (\'full\', \'neutral\', \'coarse\') and type(units) is int and 0 <= units <= 64\n    feedback = {} if arm == \'neutral\' else dict(case[\'initial_feedback\'])\n    if arm == \'coarse\':\n        assert case[\'task\'][\'family\'] == \'sat\' and \'clause_index\' in feedback\n        del feedback[\'clause_index\']\n    content = RECONSIDER + \'\\nDeterministic checker feedback: \' + json.dumps(feedback, separators=(\',\', \':\'))\n    content += \'\\nInert padding; ignore this line:\' + \' a\' * units\n    return {\'model\': \'deepseek-flash\', \'messages\': [{\'role\': \'user\', \'content\': case[\'task\'][\'prompt\']},\n        {\'role\': \'assistant\', \'content\': case[\'initial_content\']}, {\'role\': \'user\', \'content\': content}],\n        \'max_tokens\': 1 if phase == \'probe\' else 2048, \'temperature\': 0, \'stream\': False, \'thinking\': {\'type\': \'disabled\'}}\n\ndef parse_journal(events):\n    records, starts = {}, []\n    response_ids = set()\n    for event in events:\n        key, status = event[\'call_key\'], event[\'status\']\n        if status == \'started\':\n            assert not any(row[\'status\']==\'local_stop\' for row in records.values()), \'Request admitted after retained globalSTOP\'\n            assert key not in records, \'Duplicate/admitted request identity: \' + key\n            starts.append(key)\n        else:\n            assert key in records and records[key][\'status\'] == \'started\', \'Terminal event without one start\'\n            assert event[\'request\'] == records[key][\'request\']\n            assert status in (\'ok\', \'error\', \'local_stop\')\n        if status == \'ok\':\n            usage = event[\'usage\']\n            assert type(usage[\'prompt_tokens\']) is int and usage[\'prompt_tokens\'] > 0\n            assert type(usage[\'completion_tokens\']) is int and 0 <= usage[\'completion_tokens\'] <= event[\'request\'][\'max_tokens\']\n            assert usage[\'total_tokens\'] == usage[\'prompt_tokens\'] + usage[\'completion_tokens\']\n            raw_cache = usage.get(\'prompt_cache_hit_tokens\')\n            cache = 0 if raw_cache is None else raw_cache\n            assert type(cache) is int and 0 <= cache <= usage[\'prompt_tokens\']\n            assert event[\'response_id\'] not in response_ids\n            response_ids.add(event[\'response_id\'])\n        elif status == \'local_stop\':\n            code = event[\'code\'].split(\':\')[0]\n            assert code in LOCAL_CODES, \'Unclassified local policy/accounting failure\'\n        records[key] = event\n    return records, starts\n\nclass ReplayHalt(Exception):\n    def __init__(self, kind, reason):\n        self.kind, self.reason = kind, reason\n        super().__init__(reason)\n\ndef inspect_case(case, records, calibration_only):\n    """Independent transcript verifier: no probe contents or runner summaries read."""\n    used, target, padding, observations = [], None, {}, {}\n    coarse_missing = None\n    def take(phase, arm, units):\n        key = PREFIX + case[\'task\'][\'id\'] + \':\' + phase + \':\' + arm\n        if phase == \'probe\':\n            key += \':pad\' + str(units)\n        if key not in records:\n            raise ReplayHalt(\'unattempted_or_interrupted\', \'next_not_attempted:\' + key)\n        record = records[key]\n        assert record[\'request\'] == expected_payload(case, phase, arm, units), \'Request/history/feedback contract changed: \' + key\n        used.append(key)\n        if record[\'status\'] == \'local_stop\':\n            raise ReplayHalt(\'local_stop\', record[\'code\'])\n        if record[\'status\'] == \'started\':\n            raise ReplayHalt(\'pending_unknown\', \'started_without_terminal:\' + key)\n        if record[\'status\'] != \'ok\':\n            raise ReplayHalt(\'missing\', \'failed_or_unknown:\' + key)\n        return record[\'usage\'][\'prompt_tokens\'], record\n\n    def search(arm, zero=None):\n        pairs = [] if zero is None else [(0, zero)]\n        n = 0\n        for _ in range(5):\n            if zero is None or len(pairs) > 1 or n != 0:\n                count, _ = take(\'probe\', arm, n)\n                pairs.append((n, count))\n            else:\n                count = zero\n            if count == target:\n                observations[arm] = pairs\n                return n\n            history = [(old_n, old_count) for old_n, old_count in pairs[:-1] if old_count != count]\n            if history:\n                a, b = history[-1]\n                proposal = round(n + (target - count) * (n - a) / (count - b))\n            else:\n                proposal = n + target - count\n            if proposal < 0 or proposal > 64 or proposal in {unit for unit, _ in pairs}:\n                observations[arm] = pairs\n                raise ReplayHalt(\'calibration_nonmatch\', \'bounded_no_match:\' + arm)\n            n = proposal\n            zero = None\n        # One pre-existing zero-padding probe plus at most4new probes.\n        observations[arm] = pairs\n        raise ReplayHalt(\'calibration_nonmatch\', \'bounded_no_match:\' + arm)\n\n    try:\n        order = [arm for arm in case[\'retry_order\'] if arm != \'coarse\']\n        zero = {arm: take(\'probe\', arm, 0)[0] for arm in order}\n        target = max(zero.values()) + 4\n        for arm in order:\n            padding[arm] = search(arm, zero[arm])\n        if \'coarse\' in case[\'retry_order\']:\n            try:\n                padding[\'coarse\'] = search(\'coarse\')\n            except ReplayHalt as error:\n                if error.kind != \'calibration_nonmatch\' or calibration_only:\n                    raise\n                coarse_missing = error.reason\n        if calibration_only:\n            result = {\'status\': \'matched_probe_only\', \'target_prompt_tokens\': target, \'padding_units\': padding}\n        else:\n            finals = {}\n            for arm in case[\'retry_order\']:\n                if arm not in padding:\n                    continue\n                count, record = take(\'final\', arm, padding[arm])\n                if count != target:\n                    if arm == \'coarse\':\n                        coarse_missing = \'final_token_drift:coarse\'\n                        continue\n                    raise ReplayHalt(\'missing\', \'final_token_drift:\' + arm)\n                finals[arm] = record\n            result = {\'status\': \'complete_primary_pair\', \'target_prompt_tokens\': target, \'padding_units\': padding,\n                \'primary_records\': {arm: finals[arm] for arm in (\'full\', \'neutral\')},\n                \'coarse_record\': finals.get(\'coarse\'), \'coarse_missing_reason\': coarse_missing,\n                \'SAT_ablation_status\': (\'missing\' if coarse_missing else \'complete\') if \'coarse\' in case[\'retry_order\'] else \'not_applicable\'}\n    except ReplayHalt as error:\n        result = {\'status\': error.kind, \'reason\': error.reason, \'target_prompt_tokens\': target,\n            \'padding_units\': padding, \'coarse_missing_reason\': coarse_missing}\n    result.update(id=case[\'task\'][\'id\'], checked_keys=used, probe_observations=observations)\n    return result\n\ndef paired(pairs, planned):\n    n = len(pairs)\n    better = sum(a and not b for a, b in pairs)\n    worse = sum(b and not a for a, b in pairs)\n    d = better + worse\n    p = min(1., 2 * sum(comb(d, k) for k in range(min(better, worse) + 1)) / 2 ** d) if d else 1.\n    return {\'planned\': planned, \'valid\': n, \'full_only_correct\': better, \'control_only_correct\': worse,\n        \'difference\': (better - worse) / n if n else None, \'exact_two_sided_McNemar\': p if n else None,\n        \'planned_possible_outcome_bounds_not_CI\': [(better-worse-(planned-n))/planned, (better-worse+planned-n)/planned]}\n\ndef check_usage_ledger(ledger, successful):\n    assert len({event[\'call_id\'] for event in ledger}) == len(ledger)\n    assert {event[\'call_id\'] for event in ledger} == successful.keys(), \'Successful response missing or duplicated in usage ledger\'\n    for event in ledger:\n        record = successful[event[\'call_id\']]\n        usage = record[\'usage\']\n        assert event[\'call_key\']==record[\'call_key\']\n        assert event[\'model_call\'][\'model\']==record[\'request\'][\'model\']\n        assert event[\'model_call\'][\'status\']==\'succeeded\' and event[\'model_call\'][\'call_count\']==1\n        assert event[\'model_call\'][\'tokens\']=={\'input\':usage[\'prompt_tokens\'], \'output\':usage[\'completion_tokens\'], \'cache_hit\':usage.get(\'prompt_cache_hit_tokens\') or 0}\n        assert event[\'provenance\']==(\'calibration_probe\' if \':probe:\' in event[\'call_key\'] else \'fresh_retry_followup\')'
HOLDOUT_ITEM_CODE = 'def initial_payload(task):\n    return {"model":"deepseek-flash","messages":[{"role":"user","content":task["prompt"]}],"max_tokens":2048,\n        "temperature":0,"stream":False,"thinking":{"type":"disabled"}}\n\ndef inspect_item(task,records):\n    key = PREFIX + task["id"] + ":initial"\n    if key not in records:\n        return {"id":task["id"],"status":"unattempted","checked_keys":[],"initial_observed":False}\n    record = records[key]\n    assert record["request"]==initial_payload(task), "Initial request contract changed"\n    if record["status"]!="ok":\n        return {"id":task["id"],"status":record["status"],"checked_keys":[key],"initial_observed":False}\n    correct,feedback = ORACLE.score(task,record["content"])\n    if correct:\n        return {"id":task["id"],"status":"initial_correct","checked_keys":[key],"initial_observed":True,\n            "initial_correct":True,"SAT_eligible":False,"primary_pair":(True,True)}\n    eligible = task["family"]=="sat" and "clause_index" in feedback\n    case = {"task":task,"initial_content":record["content"],"initial_feedback":feedback,\n        "retry_order":[arm for arm in task["retry_order"] if arm!="coarse" or eligible]}\n    result = BASE.inspect_case(case,records,False)\n    result.update(initial_observed=True,initial_correct=False,initial_feedback=feedback,SAT_eligible=eligible)\n    result["checked_keys"]=[key]+result["checked_keys"]\n    if result["status"]=="complete_primary_pair":\n        result["primary_pair"] = tuple(ORACLE.score(task,result["primary_records"][arm]["content"])[0] for arm in ("full","neutral"))\n        if result["SAT_ablation_status"]=="complete":\n            result["ablation_pair"]=(result["primary_pair"][0],ORACLE.score(task,result["coarse_record"]["content"])[0])\n    return result\n\ndef paired(pairs,planned):\n    if not planned:\n        assert not pairs\n        return {"planned":0,"valid":0,"not_complete":0,"difference":None,"exact_two_sided_McNemar":None,\n            "planned_possible_outcome_bounds_not_CI":None,"full_only_correct":0,"control_only_correct":0}\n    result = BASE.paired(pairs,planned)\n    result["not_complete"]=planned-len(pairs)\n    return result\n\ndef estimands(tasks,items):\n    overall = [item["primary_pair"] for item in items if "primary_pair" in item]\n    errors = [item for item in items if item.get("initial_observed") and item.get("initial_correct") is False]\n    eligible = [item for item in errors if item["SAT_eligible"]]\n    unresolved = sum(task["family"]=="sat" and not item["initial_observed"] for task,item in zip(tasks,items))\n    observed = sum(item["initial_observed"] for item in items)\n    correct = sum(item.get("initial_correct") is True for item in items)\n    return {"primary_overall240":paired(overall,240),\n        "conditional_repair":paired([item["primary_pair"] for item in errors if "primary_pair" in item],len(errors)),\n        "exploratory_SAT_ablation":paired([item["ablation_pair"] for item in eligible if "ablation_pair" in item],len(eligible)),\n        "SAT_eligibility_unresolved_initials":unresolved,"SAT_possible_eligibility_denominator_range":[len(eligible),len(eligible)+unresolved],\n        "conditional_initial_error_eligibility_unresolved":240-observed,\n        "initial":{"planned":240,"observed":observed,"correct":correct,"not_observed":240-observed,\n            "possible_full240_accuracy_bounds_not_CI":[correct/240,(correct+240-observed)/240]},\n        "scope":"independent holdout240; reused375/old600/old120 never pooled; missing bounds are not CIs and assume no MCAR"}\n\ndef validate_producer_science(science, independent):\n    # A retained initial is observable even when a later localSTOP interrupts its row.\n    assert science["initial"] == independent["initial"], "Producer omitted or misstated raw initial observations"\n    for source,target in (("primary_overall240","primary_overall240"),("conditional_repair","conditional_repair"),("exploratory_SAT_full_vs_coarse","exploratory_SAT_ablation")):\n        actual,expected=science[source],independent[target]\n        for key in ("planned","valid","not_complete","full_only_correct","control_only_correct","difference"):\n            assert actual[key]==expected[key], "Producer estimand mismatch: "+source+":"+key\n        assert actual["exact_McNemar_two_sided"]==expected["exact_two_sided_McNemar"]\n        assert actual["planned_possible_outcome_difference_bounds_not_CI"]==expected["planned_possible_outcome_bounds_not_CI"]\n    assert science["SAT_eligibility_unresolved_initials"]==independent["SAT_eligibility_unresolved_initials"]\n    assert science["SAT_possible_eligibility_denominator_range"]==independent["SAT_possible_eligibility_denominator_range"]'
LEGACY_PURE_GENERATOR = 'def shortest(spec):\n    queue, visited = [(0, [spec[\'source\']])], set()\n    while queue:\n        cost, path = heapq.heappop(queue)\n        node = path[-1]\n        if node in visited:\n            continue\n        visited.add(node)\n        if node == spec[\'target\']:\n            return {\'path\': path, \'cost\': cost}\n        for a, b, weight in spec[\'edges\']:\n            neighbor = b if a == node else a if b == node else None\n            if neighbor is not None and neighbor not in visited:\n                heapq.heappush(queue, (cost + weight, path + [neighbor]))\n    raise ValueError(\'Disconnected generated graph\')\n\ndef make_dataset():\n    rng, tasks = random.Random(SEED), []\n    for family in [\'arithmetic\', \'sat\', \'graph\']:\n        for i in range(12):\n            hard = i % 2 == 1\n            split = \'development\' if i < 2 else \'pilot\' if i < 4 else \'eval\'\n            if family == \'arithmetic\':\n                start = rng.randint(20, 150)\n                ops = [[rng.choice([\'+\', \'-\', \'*\']), rng.randint(2, 9)] for _ in range(8 if hard else 4)]\n                spec, answer = {\'start\': start, \'ops\': ops}, start\n                for op, value in ops:\n                    answer = answer + value if op == \'+\' else answer - value if op == \'-\' else answer * value\n                oracle = {\'answer\': answer}\n                instruction = \'Apply ops sequentially to start, using exact integer arithmetic. Return {"answer": integer}.\'\n            elif family == \'sat\':\n                n = 10 if hard else 6\n                bits = [rng.randrange(2) for _ in range(n)]\n                clauses = []\n                while len(clauses) < (28 if hard else 12):\n                    clause = [v if rng.randrange(2) else -v for v in rng.sample(range(1, n+1), 3)]\n                    if any(bits[abs(v)-1] == (v > 0) for v in clause) and clause not in clauses:\n                        clauses.append(clause)\n                spec, oracle = {\'n\': n, \'clauses\': clauses}, {\'assignment\': bits}\n                instruction = \'Find any satisfying assignment for this CNF. Each clause is OR, clauses combine by AND, positive literals mean x_i and negative literals mean NOT x_i. Return {"assignment": [0 or 1 for x_1 through x_n]}. All instances are satisfiable.\'\n            else:\n                n = 10 if hard else 6\n                edges = [[v, v+1, rng.randint(1, 15)] for v in range(n-1)]\n                while len(edges) < (17 if hard else 9):\n                    a, b = sorted(rng.sample(range(n), 2))\n                    if not any(x == a and y == b for x, y, _ in edges):\n                        edges.append([a, b, rng.randint(1, 15)])\n                spec = {\'n\': n, \'edges\': sorted(edges), \'source\': 0, \'target\': n-1}\n                oracle = shortest(spec)\n                instruction = \'Find a shortest simple path from source to target in this undirected positive-weight graph. Each edge is [a,b,weight]. Return {"path": [integer vertices], "cost": integer total weight}. Any tied optimum is accepted.\'\n            prompt = instruction + \'\\nInput: \' + json.dumps(spec, separators=(\',\', \':\')) + \'\\nOutput only the requested JSON object, without code fences or other keys.\'\n            tasks.append({\'id\': family+\'-\'+str(i+1).zfill(2), \'family\': family, \'difficulty\': \'hard\' if hard else \'easy\', \'split\': split, \'spec\': spec, \'oracle\': oracle, \'prompt\': prompt})\n    return tasks'
HOLDOUT_REGENERATOR_CODE = 'def regenerated(excluded):\n    # Only extract the historical generator\'s two pure functions, not its caller.\n    environment = {"random": random, "heapq": heapq, "json": json}\n    exec(LEGACY_PURE_GENERATOR, environment)\n    fingerprints = {ORACLE.fingerprint(task) for task in excluded}\n    prompts = {task["prompt"] for task in excluded}\n    counts = Counter();tasks=[];seeds=[]\n    families = ("arithmetic","sat","graph")\n    for batch in range(64):\n        seed = 20261024 + batch;seeds.append(seed);environment["SEED"] = seed\n        for task in environment["make_dataset"]():\n            cell = task["family"],task["difficulty"]\n            signature = ORACLE.fingerprint(task)\n            if counts[cell] == 40 or signature in fingerprints or task["prompt"] in prompts:\n                continue\n            number = counts[cell]\n            offset = families.index(cell[0])*2 + (cell[1]=="hard")\n            choices = list(itertools.permutations(("full","neutral","coarse"))) if cell[0]=="sat" else [("full","neutral"),("neutral","full")]\n            task.update(id=f"{cell[0]}-holdout240-{cell[1]}-{number+1:02}",split="independent_holdout",\n                retry_order=list(choices[(number+offset)%len(choices)]),instance_sha256=signature)\n            tasks.append(task);counts[cell]+=1;fingerprints.add(signature);prompts.add(task["prompt"])\n        if len(tasks)==240:\n            break\n    assert len(tasks)==240, "Bounded generator cannot fill fixed240"\n    random.Random(20261024+99).shuffle(tasks)\n    return tasks,seeds'

PRIMARY_BOOTSTRAP_CODE = 'import math\nfrom random import Random\nREPLICATES=10000\nSEED=20261008\nCONFIDENCE_LEVEL=.95\n\ndef linear_quantile(values, probability):\n    if not values or not 0 <= probability <= 1:\n        raise ValueError("A nonempty sample and probability in [0,1] are required.")\n    ordered = sorted(values)\n    h = (len(ordered) - 1) * probability\n    left, right = math.floor(h), math.ceil(h)\n    return ordered[left] + (ordered[right] - ordered[left]) * (h - left)\n\ndef paired_percentile_interval(b, w, n, planned_n):\n    if any(type(value) is not int for value in (b, w, n, planned_n)):\n        raise ValueError("Pair counts and denominators must be integers, excluding bool.")\n    if b < 0 or w < 0 or n <= 0 or b + w > n or planned_n < n:\n        raise ValueError("Require nonnegative discordances, b+w<=n>0 and planned_n>=n.")\n    differences = [1] * b + [-1] * w + [0] * (n - b - w)\n    rng = Random(SEED)\n    means = [sum(differences[rng.randrange(n)] for _ in range(n)) / n\n             for _ in range(REPLICATES)]\n    missing = planned_n - n\n    return {"diagnostic_only": b, "comparator_only": w, "complete_pairs": n,\n        "planned_items": planned_n, "missing_items": missing,\n        "paired_difference": (b - w) / n,\n        "ci95": [linear_quantile(means, .025), linear_quantile(means, .975)],\n        "method": "supplementary paired percentile bootstrap with linear quantiles",\n        "replicates": REPLICATES, "seed": SEED, "confidence_level": CONFIDENCE_LEVEL,\n        "complete_case_conditional": missing > 0,\n        "uncertainty_scope": "empirical complete-task distribution; no resampling of model generations",\n        "full_planned_missing_difference_bounds": [(b - w - missing) / planned_n,\n                                                     (b - w + missing) / planned_n],\n        "missing_bounds_are_confidence_intervals": False,\n        "missing_mechanism_assumption": "none; not MCAR or MAR",\n        "primary_exact_mcnemar_replaced": False}'

def replay_holdout(bundle):
    holdout = bundle.get("independent_new_holdout")
    if holdout is None:
        raise RuntimeError("NOT_READY_NO_API: independently audited new240 holdout is absent")
    env = {"json": json, "Counter": Counter, "comb": comb, "datetime": datetime,
        "PREFIX": "tokenmatched-holdout240-20261008:", "LOCAL_CODES": LOCAL_CODES, "RECONSIDER": RECONSIDER,
        "ORACLE": SimpleNamespace(score=score, fingerprint=fingerprint, initial_prompt=initial_prompt),
        "random":random,"heapq":heapq,"itertools":itertools,"hashlib":hashlib,
        "LEGACY_PURE_GENERATOR":LEGACY_PURE_GENERATOR}
    exec(HOLDOUT_BASE_CODE, env)
    env["BASE"] = SimpleNamespace(**{name:env[name] for name in ("expected_payload","inspect_case","paired","parse_journal","check_usage_ledger")})
    exec(HOLDOUT_ITEM_CODE, env)
    exec(HOLDOUT_REGENERATOR_CODE, env)
    tasks = holdout["tasks"]
    regenerated,seeds = env["regenerated"](holdout["excluded756"])
    assert len(holdout["excluded756"]) == 756 and tasks == regenerated
    assert seeds == holdout["manifest"]["seeds"]
    assert set(fingerprint(task) for task in bundle["tasks"]).isdisjoint(fingerprint(task) for task in tasks)
    records,starts,response_ids = {},[],set()
    for segment in holdout["segment_raw_records"]:
        local,local_starts = env["parse_journal"](segment)
        assert records.keys().isdisjoint(local), "Request retransmitted across administrative segments"
        ids = {row["response_id"] for row in local.values() if row["status"] == "ok"}
        assert response_ids.isdisjoint(ids), "Duplicate response across administrative segments"
        records.update(local); starts.extend(local_starts); response_ids.update(ids)
    assert all(key.startswith(env["PREFIX"]) for key in records)
    items = [env["inspect_item"](task,records) for task in tasks]
    assert {key for item in items for key in item["checked_keys"]} == records.keys()
    assert starts == [key for item in items for key in item["checked_keys"]]
    successful = {row["response_id"]:row for row in records.values() if row["status"] == "ok"}
    env["check_usage_ledger"](holdout["resource_events"],successful)
    old_ids = {event["call_id"] for event in bundle["resource_events"]}
    if bundle.get("tokenmatched_followup"):
        old_ids.update(event["call_id"] for event in bundle["tokenmatched_followup"]["resource_events"])
    assert old_ids.isdisjoint(successful)
    result = env["estimands"](tasks,items)
    expected = holdout["independent_audit"]
    assert all(result[key] == expected[key] for key in result)
    usage = {"input":sum(row["usage"]["prompt_tokens"] for row in successful.values()),
        "output":sum(row["usage"]["completion_tokens"] for row in successful.values()),
        "cache_hit":sum(row["usage"].get("prompt_cache_hit_tokens") or 0 for row in successful.values())}
    assert usage == expected["usage"] and len(starts) == expected["actual_request_starts"]
    env["validate_producer_science"](holdout["terminal_result"]["science"],result)
    result.update(usage=usage,usage_by_request_phase=expected["usage_by_request_phase"],
        actual_request_starts=len(starts),actual_successful_responses=len(successful),
        phase_state_counts=expected["phase_state_counts"],budget=expected["budget"],outcome=expected["outcome"],
        zero_new_model_requests_in_current_Execution=True,initial_correct_shared_response_counted_once=True,
        calibration_probe_content_not_scored=True,source_sha256=holdout["source_sha256"])
    if expected.get("derived_from_independent_continuation_union_audit"):
        bootstrap = {}
        exec(PRIMARY_BOOTSTRAP_CODE,bootstrap)
        primary = result["primary_overall240"]
        interval = bootstrap["paired_percentile_interval"](primary["full_only_correct"],primary["control_only_correct"],primary["valid"],240) if primary["valid"] else None
        assert interval == expected["supplementary_primary_paired_bootstrap"]
        result.update(supplementary_primary_paired_bootstrap=interval,bootstrap_source_sha256=expected["bootstrap_source_sha256"],bootstrap_scope=expected["bootstrap_scope"],administrative_amendment_after_first_result=True,original240_denominator_never_expanded=True,derived_from_independent_continuation_union_audit=True,derived_three_segment_view=True,primary_correct_counts=expected["primary_correct_counts"])
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
