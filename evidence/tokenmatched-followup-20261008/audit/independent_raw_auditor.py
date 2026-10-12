"""Independent raw-request replay; never imports the followup runner/controller."""
import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import importlib.util
import itertools
import json
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[1]
STUDY = PROJECT / 'process/tokenmatched-followup-20261008'
PREFIX = 'tokenmatched-followup-20261008:'
RECONSIDER = 'Reconsider your previous answer and return only the requested final JSON object.'
LOCAL_CODES = {'RSI_REQUEST_PAUSED', 'RSI_REQUEST_DEADLINE', 'RSI_REQUEST_POLICY_INVALID',
               'RSI_MODEL_BUDGET_EXCEEDED', 'RSI_LEDGER_PERSIST_FAILED',
               'FOLLOWUP_SETTLED_CONTROL_CAP_REACHED', 'INVALID_RESPONSE_OR_ACCOUNTING'}


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scorer_module():
    path = PROJECT / 'process/run14-input/run.py'
    spec = importlib.util.spec_from_file_location('independent_frozen_oracle', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_selection(directory=STUDY):
    ready, data = load(directory / 'ready.json'), load(directory / 'cases.json')
    assert all(digest(directory / name) == sha for name, sha in ready['sha256'].items())
    assert all(digest(PROJECT / name) == sha for name, sha in data['source_sha256'].items())
    bundle = load(PROJECT / 'process/run14-input/dataset.json')
    old_audit = load(PROJECT / 'process/replication600-independent-audit/resume-final-audit.json')
    missing = set(old_audit['missing_ids'])
    oracle = scorer_module()
    initial = {record['call_key'].split(':')[1]: record for record in bundle['raw_records']
        if record['status'] == 'ok' and record['call_key'].endswith(':initial')}
    expected = []
    for task in bundle['tasks']:
        if task['id'] in missing:
            continue
        record = initial[task['id']]
        correct, feedback = oracle.score(task, record['content'])
        if not correct:
            expected.append({'task': dict(task), 'initial_content': record['content'], 'initial_feedback': feedback,
                'historical_initial_call_key': record['call_key'], 'historical_initial_response_id': record['response_id'],
                'historical_initial_request': record['request']})
    expected.sort(key=lambda case: (case['task']['family'], case['task']['difficulty'],
        hashlib.sha256(('tokenmatched-followup-order-v1:' + case['task']['id']).encode()).hexdigest()))
    permutations = list(itertools.permutations(('full', 'neutral', 'coarse')))
    indices = {2: 0, 3: 0}
    for case in expected:
        localized = case['task']['family'] == 'sat' and 'clause_index' in case['initial_feedback']
        choices = permutations if localized else [('full', 'neutral'), ('neutral', 'full')]
        size = 3 if localized else 2
        case['retry_order'] = list(choices[indices[size] % len(choices)])
        indices[size] += 1
        case['historical_retry_order'] = case['task'].pop('retry_order')
    assert len(expected) == 375 and indices[3] == 166 and data['cases'] == expected
    assert load(directory / 'case-ids.json') == [case['task']['id'] for case in expected]
    pilot = [next(case for case in expected if case['task']['family'] + ':' + case['task']['difficulty'] == cell)
        for cell in sorted({case['task']['family'] + ':' + case['task']['difficulty'] for case in expected})]
    historical_ids = {event['call_id'] for event in bundle['resource_events']}
    return expected, pilot, historical_ids, oracle


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


def check_phase_budget(directory, scope, records, budget_after=None):
    before_path = directory / (scope + '-budget-before.json')
    original_after_path = directory / (scope + '-budget-after.json')
    after_path = Path(budget_after) if budget_after is not None else original_after_path
    if not before_path.exists() or not after_path.exists():
        return {'status': 'NO_TERMINAL_BUDGET_PAIR_YET'}
    before, after = load(before_path), load(after_path)
    original_after = load(original_after_path) if original_after_path.exists() else None
    if original_after is not None:
        assert datetime.fromisoformat(after['updated_at']) >= datetime.fromisoformat(original_after['updated_at']), 'Selected settled seal predates client-exit snapshot'
    assert before['policy'] == after['policy'] and not before['active_reservations'] and not after['active_reservations']
    start = datetime.fromisoformat(load(directory / (scope + '-started.json'))['started_at_utc'])
    end = datetime.fromisoformat(after['updated_at'])
    # after.updated_at is last ledger mutation, not execution end; no model-call
    # correctness content is used, and cached calls outside this interval are excluded.
    calls = [record for record in records.values() if record['status'] == 'ok'
        and start <= datetime.fromisoformat(record['started_at_utc']) <= end]
    tokens = {field: sum(record['usage'][field] for record in calls) for field in ('prompt_tokens', 'completion_tokens')}
    known = 2*tokens['prompt_tokens'] + 8*tokens['completion_tokens']
    delta = after['charged_micro_cny'] - before['charged_micro_cny']
    reserved = after['reserved_calls'] - before['reserved_calls']
    settled = after['settled_calls'] - before['settled_calls']
    unknown = after['unmetered_calls'] - before['unmetered_calls']
    assert reserved == settled and reserved >= len(calls) and 0 <= unknown <= reserved-len(calls)
    residual = delta-known
    assert unknown*2_359_296 <= residual <= (reserved-len(calls))*2_359_296
    return {'status': 'EXACT_KNOWN_AND_GLOBAL_UNKNOWN_RECONCILIATION' if reserved-len(calls)==unknown else 'RESIDUAL_CALLS_REQUIRE_GLOBAL_INTERVAL_ATTRIBUTION',
        'control_delta_CNY': str(Decimal(delta)/1_000_000), 'attributable_known_successful_control_CNY': str(Decimal(known)/1_000_000),
        'residual_control_CNY': str(Decimal(residual)/1_000_000), 'known_successful_calls_in_interval': len(calls),
        'reserved_delta': reserved, 'settled_delta': settled, 'global_unknown_delta': unknown,
        'global_unknown_before': before['unmetered_calls'], 'global_unknown_after': after['unmetered_calls'],
        'raw_missing_requests_not_assumed_equal_global_unknown': True, 'no_refund_or_reset': True,
        'globally_known_calls_without_raw_in_interval': reserved-len(calls)-unknown,
        'late_global_usage_promoted_to_scientific_success': False,
        'selected_after_path': str(after_path), 'selected_after_sha256': digest(after_path),
        'original_after_path': str(original_after_path),
        'original_after_sha256': digest(original_after_path) if original_after is not None else None,
        'original_after_had_active_reservations': bool(original_after and original_after['active_reservations'])}



def check_phase_outcome(directory, scope, selected, inspections):
    result_path = directory / (scope + '-result.json')
    rows_path = directory / (scope + '-rows.json')
    exit_path = directory / (scope + '-process-result.json')
    rows = load(rows_path) if rows_path.exists() else []
    assert [row['id'] for row in rows] == [case['task']['id'] for case in selected[:len(rows)]], 'Processed rows are not a frozen selection prefix'
    for row, independent in zip(rows, inspections):
        if row['status'] in ('matched_probe_only','complete_primary_pair'):
            assert row['status']==independent['status'], 'Claimed complete row lacks raw matching evidence'
        else:
            assert row['status']=='missing' and independent['status'] in ('missing','calibration_nonmatch','pending_unknown')
    outcome = {'selected':len(selected), 'durably_recorded_processed':len(rows), 'unattempted_or_interrupted':len(selected)-len(rows)}
    if result_path.exists():
        declared=load(result_path)
        assert declared['selected_cases']==len(selected)
        assert declared['processed_cases']==len(rows)
        assert declared['unattempted_or_interrupted_cases']==len(selected)-len(rows)
        if declared['status']=='ALL_SELECTED_CASES_PROCESSED':
            assert len(rows)==len(selected), 'False completed phase with missing processed cases'
        else:
            assert declared['status'] in ('STOPPED_PARTIAL','FAILED_LOCAL','FAILED_LOCAL_PARTIAL','FAILED')
        outcome['declared_status']=declared['status']
        outcome['declared_elapsed_seconds']=declared.get('elapsed_seconds')
    else:
        outcome['declared_status']='NO_TERMINAL_RESULT'
    if exit_path.exists():
        process=load(exit_path)
        code=process.get('exit_code',process.get('worker_exit_code'))
        assert type(code) is int
        if outcome['declared_status']=='ALL_SELECTED_CASES_PROCESSED':
            assert code==0
        if outcome['declared_status'].startswith('FAILED'):
            assert code!=0, 'Local failure incorrectly reported with successful exit'
        outcome['exit_code']=code
        outcome['outer_elapsed_seconds']=process.get('elapsed_seconds')
        outcome['outer_elapsed_includes_import_and_teardown']=True
    else:
        outcome['exit_code']=None
        outcome['exit_proof_gap']='Root must save actual process exit in '+exit_path.name
    return outcome

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


def audit(directory=STUDY, budget_after=None):
    cases, pilot, historical_ids, oracle = verify_selection(directory)
    journal = directory / 'calls.jsonl'
    events = [json.loads(line) for line in journal.read_text(encoding='utf-8').splitlines()] if journal.exists() else []
    records, starts = parse_journal(events)
    assert historical_ids.isdisjoint({record['response_id'] for record in records.values() if record['status']=='ok'})
    full_started = (directory / 'full_followup-started.json').exists()
    pilot_started = (directory / 'calibration_only-started.json').exists()
    scope = 'full_followup' if full_started else 'calibration_only' if pilot_started else 'preparation'
    selected = cases if full_started else pilot if pilot_started else cases
    inspections = [inspect_case(case, records, not full_started) for case in selected]
    used = {key for item in inspections for key in item['checked_keys']}
    assert used == records.keys(), 'Unexpected requests or an extra retry after failure'
    # With no full run, the exact6pilot order is independently reconstructed.
    if not full_started:
        expected_order = [key for item in inspections for key in item['checked_keys']]
        assert starts == expected_order
        assert all(':probe:' in key for key in records), 'Final generation illegally entered calibration-only phase'
    else:
        for item in inspections:
            actual = [key for key in starts if key in set(item['checked_keys'])]
            assert actual == item['checked_keys'], 'Within-case request sequence mismatch'
    ledger_path = directory / 'model_calls.jsonl'
    ledger = [json.loads(line) for line in ledger_path.read_text(encoding='utf-8').splitlines()] if ledger_path.exists() else []
    successful = {record['response_id']: record for record in records.values() if record['status']=='ok'}
    check_usage_ledger(ledger,successful)
    counts = dict(Counter(item['status'] for item in inspections))
    totals = {'input': sum(record['usage']['prompt_tokens'] for record in successful.values()),
              'output': sum(record['usage']['completion_tokens'] for record in successful.values()),
              'cache_hit': sum(record['usage'].get('prompt_cache_hit_tokens') or 0 for record in successful.values())}
    result = {'status':'OFFLINE_PREPARED_NOT_RUN' if scope=='preparation' else 'RAW_TRANSCRIPT_AUDIT_PASS', 'scope':scope,
        'planned_primary_cases':375, 'planned_SAT_ablation_cases':166, 'selected_phase_cases':len(selected),
        'phase_state_counts':counts, 'all_request_starts_have_terminal_event':all(row['status']!='started' for row in records.values()),
        'actual_request_starts':len(starts), 'actual_successful_responses':len(successful),
        'raw_terminal_request_states':dict(Counter(record['status'] for record in records.values())),
        'usage':totals,
        'usage_by_request_phase':{phase:{'calls':sum(':'+phase+':' in row['call_key'] for row in successful.values()),
            'input':sum(row['usage']['prompt_tokens'] for row in successful.values() if ':'+phase+':' in row['call_key']),
            'output':sum(row['usage']['completion_tokens'] for row in successful.values() if ':'+phase+':' in row['call_key']),
            'cache_hit':sum(row['usage'].get('prompt_cache_hit_tokens') or 0 for row in successful.values() if ':'+phase+':' in row['call_key'])}
            for phase in ('probe','final')}, 'source_and_selection_exact':True, 'actual_payloads_histories_feedback_padding_and_counts_checked':True,
        'no_duplicate_request_or_response_ids':True, 'old_initials_not_rebilled':True,
        'calibration_probe_content_or_correctness_inspected':False, 'model_calls_for_audit':0, 'supplier_requests_for_audit':0,
        'budget': check_phase_budget(directory,scope,records,budget_after) if scope!='preparation' else {'status':'NOT_RUN'},
        'outcome':check_phase_outcome(directory,scope,selected,inspections) if scope!='preparation' else {'status':'NOT_RUN'},
        'per_case_feasibility':[{k:v for k,v in item.items() if k not in ('primary_records','coarse_record')} for item in inspections]}
    if full_started:
        primary, ablation = [], []
        task_by_id = {case['task']['id']:case['task'] for case in cases}
        for item in inspections:
            if item['status']=='complete_primary_pair':
                task = task_by_id[item['id']]
                full = oracle.score(task,item['primary_records']['full']['content'])[0]
                neutral = oracle.score(task,item['primary_records']['neutral']['content'])[0]
                primary.append((full,neutral))
                if item['SAT_ablation_status']=='complete':
                    ablation.append((full,oracle.score(task,item['coarse_record']['content'])[0]))
        result['primary'] = paired(primary,375)
        result['exploratory_SAT_ablation'] = paired(ablation,166)
    if scope!='preparation' and result['budget']['status']=='NO_TERMINAL_BUDGET_PAIR_YET':
        result['status']='RAW_PARTIAL_SNAPSHOT_PHASE_NOT_SEALED'
    if scope!='preparation' and result['budget']['status']=='RESIDUAL_CALLS_REQUIRE_GLOBAL_INTERVAL_ATTRIBUTION':
        result['status']='RAW_SCIENCE_PASS_GLOBAL_SETTLEMENT_RESIDUAL'
    result['checked_at_utc'] = datetime.now(timezone.utc).isoformat()
    return result


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'audit.json')
    parser.add_argument('--budget-after',type=Path,help='Explicit settled supplement; preserves the original client-exit after snapshot')
    args = parser.parse_args()
    result = audit(budget_after=args.budget_after)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:result[key] for key in ('status','scope','selected_phase_cases','phase_state_counts','actual_request_starts','usage')},ensure_ascii=False))
