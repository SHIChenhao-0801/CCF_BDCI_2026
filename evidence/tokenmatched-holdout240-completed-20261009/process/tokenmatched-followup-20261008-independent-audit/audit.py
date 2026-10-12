"""Exact audited pure transcript functions; budget and paid workflow entry points excluded."""

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
