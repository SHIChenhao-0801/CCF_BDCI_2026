"""Zero-network preparation/controller; transport is injected only by mocks here."""
import json

ARMS = ('full', 'neutral')
MODEL = 'deepseek-flash'
RECONSIDER = 'Reconsider your previous answer and return only the requested final JSON object.'
MAX_PROBES_PER_ARM = 5
MAX_PADDING_UNITS = 64
TARGET_MARGIN = 4


class MissingPair(Exception):
    pass


def proposed_units(observations, units, count, target):
    previous = [(n, value) for n, value in observations.items() if n != units and value != count]
    if previous:
        old_units, old_count = previous[-1]
        return round(units + (target - count) * (units - old_units) / (count - old_count))
    return units + target - count


def messages(case, arm, padding_units):
    assert arm in (*ARMS, 'coarse') and type(padding_units) is int and 0 <= padding_units <= MAX_PADDING_UNITS
    feedback = {} if arm == 'neutral' else dict(case['initial_feedback'])
    if arm == 'coarse':
        assert case['task']['family'] == 'sat' and 'clause_index' in feedback
        del feedback['clause_index']
    content = RECONSIDER + '\nDeterministic checker feedback: ' + json.dumps(feedback, separators=(',', ':'))
    content += '\nInert padding; ignore this line:' + ' a' * padding_units
    return [{'role': 'user', 'content': case['task']['prompt']},
            {'role': 'assistant', 'content': case['initial_content']},
            {'role': 'user', 'content': content}]


def payload(case, arm, padding_units, max_tokens):
    assert max_tokens in (1, 2048)
    return {'model': MODEL, 'messages': messages(case, arm, padding_units), 'max_tokens': max_tokens,
            'temperature': 0, 'stream': False, 'thinking': {'type': 'disabled'}}


def prompt_tokens(response):
    if response.get('status') != 'ok':
        raise MissingPair('failed_or_unknown_request_never_resent')
    usage = response.get('usage')
    if not isinstance(usage, dict) or type(usage.get('prompt_tokens')) is not int or usage['prompt_tokens'] <= 0:
        raise MissingPair('usage_unavailable')
    return usage['prompt_tokens']


def calibrate(case, caller):
    """Use only returned usage; do not parse, score or pass on any probe output."""
    prefix = 'tokenmatched-followup-20261008:' + case['task']['id']
    observations = {arm: {} for arm in ARMS}

    def probe(arm, units):
        assert units not in observations[arm], 'An identical probe is never resent'
        key = prefix + ':probe:' + arm + ':pad' + str(units)
        result = caller(key, payload(case, arm, units, 1))
        value = prompt_tokens(result)
        observations[arm][units] = value
        return value

    primary_order = [arm for arm in case['retry_order'] if arm in ARMS]
    for arm in primary_order:
        probe(arm, 0)
    target = max(observations[arm][0] for arm in ARMS) + TARGET_MARGIN
    chosen = {}
    for arm in primary_order:
        units, count = 0, observations[arm][0]
        while count != target and len(observations[arm]) < MAX_PROBES_PER_ARM:
            proposal = proposed_units(observations[arm], units, count, target)
            if not 0 <= proposal <= MAX_PADDING_UNITS or proposal in observations[arm]:
                break
            units, count = proposal, probe(arm, proposal)
        if count != target:
            raise MissingPair('bounded_calibration_no_exact_match:' + arm)
        chosen[arm] = units
    return {'target_prompt_tokens': target, 'padding_units': chosen, 'probe_observations': observations}


def calibrate_coarse(case, target, caller):
    """SAT location ablation uses the fixed primary target without changing primary."""
    observations, units = {}, 0
    while len(observations) < MAX_PROBES_PER_ARM:
        key = 'tokenmatched-followup-20261008:' + case['task']['id'] + ':probe:coarse:pad' + str(units)
        count = prompt_tokens(caller(key, payload(case, 'coarse', units, 1)))
        observations[units] = count
        if count == target:
            return {'padding_units': units, 'probe_observations': observations}
        proposal = proposed_units(observations, units, count, target)
        if not 0 <= proposal <= MAX_PADDING_UNITS or proposal in observations:
            break
        units = proposal
    raise MissingPair('bounded_calibration_no_exact_match:coarse')


def execute_case(case, caller):
    """Primary pairs and SAT localization ablation have explicitly separate validity."""
    try:
        calibration = calibrate(case, caller)
        coarse, coarse_missing = None, None
        if 'coarse' in case['retry_order']:
            try:
                coarse = calibrate_coarse(case, calibration['target_prompt_tokens'], caller)
            except MissingPair as error:
                if not str(error).startswith('bounded_calibration_no_exact_match:'):
                    raise
                coarse_missing = str(error)
        results = {}
        for arm in case['retry_order']:
            if arm == 'coarse' and coarse is None:
                continue
            key = 'tokenmatched-followup-20261008:' + case['task']['id'] + ':final:' + arm
            units = coarse['padding_units'] if arm == 'coarse' else calibration['padding_units'][arm]
            response = caller(key, payload(case, arm, units, 2048))
            if prompt_tokens(response) != calibration['target_prompt_tokens']:
                if arm == 'coarse':
                    coarse_missing = 'final_returned_usage_mismatch:coarse'
                    continue
                raise MissingPair('final_returned_usage_mismatch:' + arm)
            results[arm] = response
        return {'status': 'complete_primary_pair', 'id': case['task']['id'], 'calibration': calibration, 'responses': results,
                'SAT_ablation_status': ('missing' if coarse_missing else 'complete') if 'coarse' in case['retry_order'] else 'not_applicable',
                'SAT_ablation_missing_reason': coarse_missing, 'coarse_calibration': coarse}
    except MissingPair as error:
        return {'status': 'missing', 'id': case['task']['id'], 'reason': str(error),
                'whole_item_excluded': True, 'no_automatic_resend': True}
