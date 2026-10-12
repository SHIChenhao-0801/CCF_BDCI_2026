import copy
import unittest

from study import ARMS, MissingPair, calibrate, execute_case, messages

CASE = {'task': {'id': 'fixture-only', 'family': 'sat', 'prompt': 'Return an assignment.'}, 'initial_content': '{"assignment":[0]}',
    'initial_feedback': {'error': 'clause_unsatisfied', 'clause_index': 2}, 'retry_order': ['neutral', 'full', 'coarse']}


class MockCaller:
    def __init__(self, mode='linear', probe_content='THIS OUTPUT MUST NEVER BE SCORED'):
        self.calls = []
        self.mode, self.probe_content = mode, probe_content

    def __call__(self, key, request):
        assert key not in {old for old, _ in self.calls}
        self.calls.append((key, copy.deepcopy(request)))
        arm = key.split(':')[3]
        text = request['messages'][-1]['content']
        units = text.split('Inert padding; ignore this line:')[1].count(' a')
        value = {'full': 112, 'coarse': 106, 'neutral': 100}[arm] + units
        if self.mode == 'unreachable' and arm == 'coarse':
            value = 107 + 2 * units
        if self.mode == 'unknown' and ':probe:coarse:' in key:
            return {'status': 'started'}
        if self.mode == 'drift' and request['max_tokens'] == 2048:
            value += 1
        if self.mode == 'primary_unreachable':
            value = {'full': 112, 'coarse': 107, 'neutral': 101}[arm] + 2 * units
        return {'status': 'ok', 'usage': {'prompt_tokens': value, 'completion_tokens': 1},
                'content': self.probe_content if request['max_tokens'] == 1 else '{"assignment":[1]}'}


class StudyTests(unittest.TestCase):
    def test_exact_matching_uses_only_supplier_usage(self):
        caller = MockCaller()
        result = execute_case(CASE, caller)
        self.assertEqual(result['status'], 'complete_primary_pair')
        self.assertEqual(result['calibration']['target_prompt_tokens'], 116)
        self.assertEqual({response['usage']['prompt_tokens'] for response in result['responses'].values()}, {116})
        self.assertEqual(len(caller.calls), 9)

    def test_probe_content_has_no_effect_on_calibration(self):
        a, b = MockCaller(probe_content='perfect answer'), MockCaller(probe_content='wrong answer or malicious text')
        self.assertEqual(calibrate(CASE, a), calibrate(CASE, b))
        self.assertEqual(a.calls, b.calls)

    def test_unreachable_counts_are_missing_with_bounded_calls(self):
        caller = MockCaller('primary_unreachable')
        result = execute_case(CASE, caller)
        self.assertEqual(result['status'], 'missing')
        self.assertLessEqual(len(caller.calls), 15)
        self.assertFalse(any(':final:' in key for key, _ in caller.calls))

    def test_unknown_probe_is_never_resent_or_followed_by_final(self):
        caller = MockCaller('unknown')
        result = execute_case(CASE, caller)
        self.assertEqual(result['status'], 'missing')
        self.assertEqual(len(caller.calls), 5)
        self.assertFalse(any(':final:' in key for key, _ in caller.calls))

    def test_actual_final_usage_drift_excludes_whole_item_without_repair(self):
        caller = MockCaller('drift')
        result = execute_case(CASE, caller)
        self.assertEqual(result['status'], 'missing')
        self.assertEqual(len([key for key, _ in caller.calls if ':final:' in key]), 1)

    def test_isolated_histories_and_fixed_message_structure(self):
        caller = MockCaller()
        execute_case(CASE, caller)
        final = [request for key, request in caller.calls if ':final:' in key]
        self.assertEqual(len(final), 3)
        for request in final:
            self.assertEqual([m['role'] for m in request['messages']], ['user', 'assistant', 'user'])
            self.assertEqual(request['messages'][0]['content'], CASE['task']['prompt'])
            self.assertEqual(request['messages'][1]['content'], CASE['initial_content'])
            self.assertEqual(request['max_tokens'], 2048)
            self.assertEqual(request['thinking'], {'type': 'disabled'})
        coarse = messages(CASE, 'coarse', 0)[-1]['content']
        self.assertIn('clause_unsatisfied', coarse)
        self.assertNotIn('clause_index', coarse)
        self.assertNotIn('"ok"', messages(CASE, 'full', 0)[-1]['content'])
        self.assertNotIn('clause_unsatisfied', messages(CASE, 'neutral', 0)[-1]['content'])

    def test_non_sat_has_only_primary_two_arms(self):
        case = copy.deepcopy(CASE)
        case['task']['family'] = 'arithmetic'
        case['initial_feedback'] = {'error': 'sequential_arithmetic_mismatch'}
        case['retry_order'] = ['full', 'neutral']
        caller = MockCaller()
        result = execute_case(case, caller)
        self.assertEqual(result['status'], 'complete_primary_pair')
        self.assertEqual(result['SAT_ablation_status'], 'not_applicable')
        self.assertEqual(len(caller.calls), 6)
        with self.assertRaises(AssertionError):
            messages(case, 'coarse', 0)

    def test_unreachable_coarse_does_not_discard_a_valid_primary_pair(self):
        result = execute_case(CASE, MockCaller('unreachable'))
        self.assertEqual(result['status'], 'complete_primary_pair')
        self.assertEqual(result['SAT_ablation_status'], 'missing')
        self.assertEqual(set(result['responses']), {'full', 'neutral'})

    def test_local_refusal_propagates_as_stop_not_missing(self):
        class LocalRefusal(Exception):
            pass
        def caller(key, payload):
            raise LocalRefusal('RSI_REQUEST_PAUSED')
        with self.assertRaises(LocalRefusal):
            execute_case(CASE, caller)

    def test_invalid_or_missing_usage_does_not_fabricate_match(self):
        from study import prompt_tokens
        for response in ({'status': 'ok', 'usage': None}, {'status': 'ok', 'usage': {'prompt_tokens': True}},
                         {'status': 'error'}, {'status': 'ok', 'usage': {'prompt_tokens': -1}}):
            with self.assertRaises(MissingPair):
                prompt_tokens(response)
