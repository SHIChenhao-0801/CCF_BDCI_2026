"""Offline replay of four research stages; final statistics require all600 dispositions."""
import argparse
from collections import Counter
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import hashlib
import itertools
import json
from pathlib import Path

import audit_replication600 as base
import audit_continuation as continuation_audit
import audit_completion as completion_audit

ARMS = base.ARMS


def totals(calls):
    calls = tuple(calls)
    return {'input_tokens': sum(c['usage']['prompt_tokens'] for c in calls),
            'output_tokens': sum(c['usage']['completion_tokens'] for c in calls),
            'cache_hit_tokens': sum(c['usage'].get('prompt_cache_hit_tokens') or 0 for c in calls)}


def check_budget(before, after, usage, successes, final):
    assert before['policy'] == after['policy']
    assert before['unmetered_calls'] == 13
    for name in ('charged_micro_cny', 'reserved_calls', 'settled_calls', 'unmetered_calls'):
        assert after[name] >= before[name], 'Historical accounting was refunded or reset'
    assert not before['active_reservations']
    policy = before['policy']
    reserve = int(Decimal(policy['input_cny_per_million']) * policy['max_input_tokens']
                  + Decimal(policy['output_cny_per_million']) * policy['max_output_tokens'])
    assert reserve == 2359296
    unknown = after['unmetered_calls'] - before['unmetered_calls']
    control = usage['input_tokens'] * 2 + usage['output_tokens'] * 8
    peak = Decimal(usage['cache_hit_tokens']) * Decimal('0.04') + (usage['input_tokens'] - usage['cache_hit_tokens']) * 2 + usage['output_tokens'] * 8
    delta = after['charged_micro_cny'] - before['charged_micro_cny']
    active = sum(after['active_reservations'].values())
    if final:
        assert not active
        assert delta == control + unknown * reserve, 'Global charge delta disagrees with raw usage/unknown accounting'
        assert after['reserved_calls'] - before['reserved_calls'] == successes + unknown
        assert after['settled_calls'] - before['settled_calls'] == successes + unknown
    cap = int(Decimal(policy['budget_cny']) * 1_000_000)
    assert after['charged_micro_cny'] <= cap
    safe = Decimal('31.676218') + (peak + unknown * reserve + active) / 1_000_000
    safe_control = Decimal('31.676218') + Decimal(control + unknown * reserve + active) / 1_000_000
    assert safe_control <= Decimal(40)
    return {'historical_unknown_calls_retained': before['unmetered_calls'], 'new_global_unknown_calls': unknown,
        'global_unknown_calls_final_or_snapshot': after['unmetered_calls'], 'new_unknown_reserve_CNY': str(Decimal(unknown * reserve) / 1_000_000),
        'new_known_conservative_peak_usage_CNY': str(peak / 1_000_000), 'new_control_usage_CNY': str(Decimal(control) / 1_000_000),
        'new_active_reserve_CNY': str(Decimal(active) / 1_000_000), 'control_charge_delta_CNY': str(Decimal(delta) / 1_000_000),
        'expected_final_control_delta_CNY': str(Decimal(control + unknown * reserve) / 1_000_000),
        'cumulative_safe_upper_CNY': str(safe), 'cumulative_safe_control_upper_CNY': str(safe_control),
        'prior_safe_upper_CNY': '31.676218', 'authorized_actual_total_CNY': '40',
        'active_reservations': len(after['active_reservations']), 'global_charge_delta_exact': final,
        'unknown_charges_are_not_invoices': True, 'historical_unknown_refund_CNY': '0', 'second_paid_ledger': False}


def audit(project, final):
    process = project / 'process'
    original, continuation, completion, resumed = [process / name for name in
        ('replication600', 'replication600-continuation', 'replication600-completion', 'replication600-resume-20261008')]
    stages = [original, continuation, completion, resumed]
    tasks, manifest = base.load(original / 'dataset.json'), base.load(original / 'manifest.json')
    assert len(tasks) == manifest['n'] == 600
    assert base.digest(original / 'dataset.json') == '0241523b60df12349ad2124b2a3d94a1eb145e29c26e7590609c5a5bd96c56df'
    assert hashlib.sha256((original / 'dataset.json').read_bytes().replace(b'\r\n', b'\n')).hexdigest() == manifest['dataset_sha256']
    prior_root = project / '每天都在等周五/code/research_project/reviewer_followup_reasoning'
    prior = base.load(prior_root / 'dataset.json') + base.load(prior_root / 'legacy-dataset.json')
    for selector in (lambda t: t['id'], base.fingerprint, lambda t: t['prompt']):
        assert len({selector(t) for t in tasks}) == 600
        assert {selector(t) for t in tasks}.isdisjoint({selector(t) for t in prior})
    for task in tasks:
        assert base.initial_prompt(task) == task['prompt']
        assert base.score(task, json.dumps(task['oracle'])) == (True, None)
        if task['family'] == 'sat':
            spec = task['spec']
            assert any(all(any(bool(bits[abs(v)-1]) == (v > 0) for v in clause) for clause in spec['clauses'])
                       for bits in itertools.product((0, 1), repeat=spec['n']))
    registrations = [base.load(stage / 'ready.json') for stage in stages]
    for stage, registration in zip(stages, registrations):
        assert {name: base.digest(stage / name) for name in registration['sha256']} == registration['sha256']
        for name, expected in registration.get('old_input_sha256', registration.get('original_input_sha256', {})).items():
            assert base.digest(Path(name)) == expected, 'Historical frozen bytes changed'
    assert all(base.load(stage / 'process-result.json')['status'] == 'FAILED' for stage in stages[:2])
    records, events, all_keys, raw_snapshots, ledger_snapshots, saved = [], [], set(), [], [], []
    stage_records, stage_events, worker_raw = [], [], {}
    for stage_index, stage in enumerate(stages):
        directories = [stage] if stage_index < 2 else [stage / 'workers' / str(i) for i in range(3 if stage_index == 2 else 2)]
        raw, ledger = [], []
        registration_time_key = ('ready_before_first_call_utc', 'registered_before_first_continuation_call_utc',
            'registered_before_first_completion_call_utc', 'registered_before_first_resume_call_utc')[stage_index]
        for directory in directories:
            if not (directory / 'calls.jsonl').exists():
                assert stage_index == 3 and not final
                continue
            component, raw_metadata = base.journal(directory / 'calls.jsonl', stage_index < 3 or final)
            resource, ledger_metadata = base.journal(directory / 'model_calls.jsonl', stage_index < 3 or final) if (directory / 'model_calls.jsonl').exists() else ([], {})
            assert len({e['event_id'] for e in resource}) == len(resource)
            keys = {r['call_key'] for r in component}
            assert all_keys.isdisjoint(keys), 'An attempted/failed/unknown request was reissued'
            all_keys.update(keys)
            assert all(datetime.fromisoformat(r['started_at']) > datetime.fromisoformat(registrations[stage_index][registration_time_key]) for r in component)
            raw += component
            ledger += resource
            worker_raw[(stage_index, directory.name)] = component
            raw_snapshots.append({'stage': stage.name, 'worker': directory.name if stage_index >= 2 else None, **raw_metadata})
            ledger_snapshots.append({'stage': stage.name, 'worker': directory.name if stage_index >= 2 else None, **ledger_metadata})
            rowpath = directory / ('eval-results.json' if stage_index < 2 else 'completion-rows.json')
            if rowpath.exists():
                saved += base.load(rowpath)
        records += raw
        events += ledger
        stage_records.append(raw)
        stage_events.append(ledger)
    calls, groups, per_item = completion_audit.verify_requests(tasks, records)
    missing_keys = [key for key, group in groups.items() if group[-1]['status'] != 'ok']
    missing_ids = {key.split(':')[1] for key in missing_keys}
    assert len(missing_keys) == len(missing_ids)
    historical_missing = {r['call_key'].split(':')[1] for raw in stage_records[:3] for r in raw
                          if r['status'] == 'error' or (r['status'] == 'started' and len(groups[r['call_key']]) == 1)}
    historical_errors = [r for raw in stage_records[:3] for r in raw if r['status'] == 'error']
    historical_pending = [key for key, group in groups.items() if len(group) == 1
                          and key in {r['call_key'] for raw in stage_records[:3] for r in raw}]
    assert len(historical_missing) == 8 and len(historical_errors) == 5 and len(historical_pending) == 3
    old_attempted = {r['call_key'].split(':')[1] for raw in stage_records[:3] for r in raw}
    plan = base.load(resumed / 'resume-plan.json')
    expected = [task['id'] for task in tasks if task['id'] not in old_attempted]
    assert len(old_attempted) == 420 and len(expected) == 180
    assert plan['unattempted_ids'] == expected and plan['administrative_worker_count'] == 2
    assert {item['id'] for item in plan['old_missing_items']} == historical_missing
    for i in range(2):
        assignment = expected[i::2]
        assert plan['worker_ids'][str(i)] == assignment
        raw = worker_raw.get((3, str(i)), [])
        attempted = list(dict.fromkeys(r['call_key'].split(':')[1] for r in raw if r['status'] == 'started'))
        assert attempted == assignment[:len(attempted)]
        if final:
            assert attempted == assignment
            terminal = base.load(resumed / 'workers' / str(i) / 'terminal-items.json')
            assert [item['id'] for item in terminal] == assignment
            assert all(item['state'] == ('missing' if item['id'] in missing_ids else 'complete') for item in terminal)
    declared_missing = set(historical_missing)
    for i in range(2):
        path = resumed / 'workers' / str(i) / 'terminal-items.json'
        if path.exists():
            terminal = base.load(path)
            declared_missing.update(item['id'] for item in terminal if item['state'] == 'missing')
    ids = [reply['response_id'] for reply in calls.values()]
    ledger = {event['call_id']: event for event in events}
    assert len(ids) == len(set(ids)) and all(isinstance(i, str) and i for i in ids)
    assert len(ledger) == len(events)
    assert set(ledger).issubset(set(ids))
    if final:
        assert set(ledger) == set(ids)
    for reply in calls.values():
        usage = reply['usage']
        assert all(type(usage[k]) is int and usage[k] >= 0 for k in ('prompt_tokens', 'completion_tokens'))
        hit = usage.get('prompt_cache_hit_tokens') or 0
        assert type(hit) is int and 0 <= hit <= usage['prompt_tokens']
        assert usage['total_tokens'] == usage['prompt_tokens'] + usage['completion_tokens']
        if usage.get('prompt_cache_miss_tokens') is not None:
            assert hit + usage['prompt_cache_miss_tokens'] == usage['prompt_tokens']
        if reply['response_id'] in ledger:
            event = ledger[reply['response_id']]
            assert event['model_call']['tokens'] == {'input': usage['prompt_tokens'], 'output': usage['completion_tokens'], 'cache_hit': hit}
            assert event['model_call']['model'] == 'deepseek-flash' and event['model_call']['call_count'] == 1
    previous_response_ids = set()
    team = project / '每天都在等周五'
    for path in list((team / 'evidence/raw-runs').glob('*/run/model_calls.jsonl')) + [team / 'evidence/reviewer-followup/reasoning/model_calls.jsonl']:
        previous, _ = base.journal(path, True)
        previous_response_ids.update(event['call_id'] for event in previous if event.get('call_id'))
    assert set(ids).isdisjoint(previous_response_ids)
    rows, details, lengths, used, order = completion_audit.generalized_recompute(tasks, calls, missing_ids)
    detail_by_id = {row['id']: row for row in details}
    assert len({row['id'] for row in saved}) == len(saved)
    for row in saved:
        assert row == detail_by_id[row['id']], 'Stored scientific row disagrees with independent raw replay'
    scientific_calls = len(rows) + 3 * sum(not row['initial'] for row in rows)
    assert scientific_calls == len(used)
    proof = base.load(process / 'resume-authorization-and-budget-20261008.json')
    before = base.load(resumed / 'budget-before.json')
    assert before == proof['ledger_after']
    for name in ('charged_micro_cny', 'reserved_calls', 'settled_calls', 'unmetered_calls', 'active_reservations'):
        assert proof['ledger_before'][name] == proof['ledger_after'][name]
    historical_unknown_delta = before['unmetered_calls'] - base.load(original / 'budget-before.json')['unmetered_calls']
    assert historical_unknown_delta == 7 and proof['refund_cny'] == '0' and not proof['new_paid_ledger_created']
    after = base.load(resumed / 'budget-after.json') if final else base.load(process / 'model-budget.json')
    new_calls = [record for record in stage_records[3] if record['status'] == 'ok']
    cost = check_budget(before, after, totals(new_calls), len(new_calls), final)
    stats, sensitivity = None, None
    if final:
        outcome = base.load(resumed / 'process-result.json')
        assert outcome['worker_exit_code'] == 0 and outcome['status'] == 'COMPLETED_WITH_DECLARED_MISSING'
        assert len(rows) + len(missing_ids) == 600 and len(rows) <= 592 and len(missing_ids) >= 8
        assert declared_missing == missing_ids
        assert len(saved) == len(rows) and set(detail_by_id) == {row['id'] for row in saved}
        assert base.load(resumed / 'results.json')['rows'] == details
        assert {item['id'] for item in base.load(resumed / 'missing.json')} == missing_ids
        for filename, expected_events in (('calls.jsonl', stage_records[3]), ('model_calls.jsonl', stage_events[3])):
            merged, _ = base.journal(resumed / filename, True)
            assert sorted(json.dumps(r, sort_keys=True) for r in merged) == sorted(json.dumps(r, sort_keys=True) for r in expected_events)
        stats = continuation_audit.statistics(rows, details, lengths, calls)
        metrics = base.load(resumed / 'metrics.json')
        for key, value in stats.items():
            if key in metrics:
                assert metrics[key] == value, key
        sensitivity = completion_audit.missing_sensitivity(rows, len(missing_ids))
    for stage, registration in zip(stages, registrations):
        assert {name: base.digest(stage / name) for name in registration['sha256']} == registration['sha256']
        assert all(base.digest(Path(name)) == expected for name, expected in registration.get('old_input_sha256', registration.get('original_input_sha256', {})).items())
    times = []
    for stage, raw in zip(stages, stage_records):
        starts = [datetime.fromisoformat(record['started_at']) for record in raw if record['status'] == 'started']
        known_ends = [datetime.fromisoformat(record['started_at']) + timedelta(seconds=record['latency_seconds'])
                      for record in raw if record['status'] != 'started' and 'latency_seconds' in record]
        outcome = base.load(stage / 'process-result.json') if (stage / 'process-result.json').exists() else {}
        times.append({'stage': stage.name, 'first_request_started_at_utc': min(starts).isoformat() if starts else None,
            'last_request_started_at_utc': max(starts).isoformat() if starts else None,
            'request_start_span_seconds': (max(starts) - min(starts)).total_seconds() if starts else 0,
            'last_known_client_terminal_estimate_utc': max(known_ends).isoformat() if known_ends else None,
            'successful_client_latency_sum_seconds': sum(record['latency_seconds'] for record in raw if record['status'] == 'ok'),
            'recorded_phase_elapsed_seconds': outcome.get('elapsed_seconds'),
            'phase_elapsed_not_available': 'elapsed_seconds' not in outcome,
            'execution_status': outcome.get('status', 'RUNNING_OR_NOT_STARTED')})
    all_starts = [datetime.fromisoformat(record['started_at']) for record in records if record['status'] == 'started']
    return {'status': 'PASS' if final else 'PARTIAL', 'mode': 'FINAL' if final else 'LIVE_SNAPSHOT',
        'planned_items': 600, 'observed_complete_pairs': len(rows), 'scientific_missing_items': len(declared_missing),
        'unattempted_items': 600 - len(per_item), 'historical_scientific_missing_items': len(historical_missing),
        'attempted_nonterminal_items': len(per_item) - len(rows) - len(declared_missing),
        'raw_unresolved_candidate_items': len(missing_ids),
        'historical_raw_transport_error_requests': len(historical_errors), 'historical_started_unknown_requests': len(historical_pending),
        'historical_research_global_unknown_delta': historical_unknown_delta,
        'missing_ids': sorted(declared_missing), 'missing_request_states': [{'call_key': key, 'state': 'unknown' if groups[key][-1]['status'] == 'started' else 'error',
            'http_status': groups[key][-1].get('http_status'), 'error_type': groups[key][-1].get('error_type')} for key in missing_keys],
        'new_raw_error_requests': sum(record['status'] == 'error' for record in stage_records[3]),
        'actual_successful_responses': len(calls), 'scientific_complete_pair_call_count': scientific_calls,
        'partial_missing_item_successful_calls_cost_only': len(calls) - len(used), 'usage_all_successful': totals(calls.values()),
        'usage_scientific_complete_pairs': totals(calls[key] for key in used), 'new_successful_responses': len(new_calls),
        'statistics': stats, 'missing_pair_worst_case_sensitivity': sensitivity, 'cost': cost,
        'administrative_workers_by_stage': [1, 1, 3, 2], 'original_strict600_status': 'FAILED',
        'first_continuation_status': 'FAILED', 'unchanged_registered600_completed': False,
        'scientific_missing_is_not_global_unknown_call_count': True, 'all_prior_bytes_preserved': True,
        'no_duplicate_request_identities': True, 'no_duplicate_response_ids': True, 'prior156_overlap': 0,
        'raw_snapshots': raw_snapshots, 'ledger_snapshots': ledger_snapshots,
        'timing_by_stage': times, 'all_stage_request_start_span_seconds_including_pause': (max(all_starts) - min(all_starts)).total_seconds(),
        'timing_scope': 'Raw start span includes overnight pause; sum of per-call latencies is workload, not wall time; absent completion elapsed stays null; known terminal timestamps are estimates from start+client latency',
        'all600_oracles_checked': True, 'model_api_calls': 0, 'network_requests': 0,
        'not_a_new_complete_agent_workflow': True, 'no_missing_at_random_assumption': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--final', action='store_true')
    args = parser.parse_args()
    report = audit(args.project.resolve(), args.final)
    report.update(checked_at_utc=datetime.now(timezone.utc).isoformat(), auditor_sha256=base.digest(Path(__file__)))
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: report[key] for key in ('status', 'observed_complete_pairs', 'scientific_missing_items',
        'unattempted_items', 'new_successful_responses', 'cost')}, ensure_ascii=False))
