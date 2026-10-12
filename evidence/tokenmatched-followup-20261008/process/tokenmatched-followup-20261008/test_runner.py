"""Test the real runner's operational terminal metadata only, with no network."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys

import runner
from transport import LocalStop


class RunnerFailureTests(unittest.TestCase):
    def run_fixture(self, error=None):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            root = project / 'process/study'
            root.mkdir(parents=True)
            cases = {'source_sha256': {}, 'cells': {'arithmetic:easy': {}},
                     'cases': [{'task': {'id': 'only-offline-fixture', 'family': 'arithmetic', 'difficulty': 'easy'}, 'retry_order': ['full', 'neutral']}]}
            raw = json.dumps(cases).encode()
            (root / 'cases.json').write_bytes(raw)
            (root / 'ready.json').write_text(json.dumps({'sha256': {'cases.json': hashlib.sha256(raw).hexdigest()}}))
            (project / 'process/request-policy.json').write_text('{"paused":false,"stop_at_utc":null}')
            (project / 'process/model-budget.json').write_text('{"active_reservations":{},"charged_micro_cny":0}')
            (root / 'execution-preflight.json').write_text(json.dumps({'root_authorized_paid_start': True,
                'authorized_scope': 'calibration_only', 'request_policy_tests': 'PASS', 'ledger_reset': False,
                'additional_settled_control_cap_micro_CNY': 5000000, 'study_baseline_charged_micro_CNY': 0}))
            with (patch.object(runner, 'ROOT', root), patch.object(runner, 'PROJECT', project),
                 patch.object(sys, 'argv', ['runner.py', '--calibration-only']),
                 patch('urllib.request.urlopen', side_effect=AssertionError('Network forbidden')),
                 patch.object(runner, 'Caller', return_value=lambda *args: None),
                 patch.object(runner, 'calibrate', side_effect=error, return_value={'target_prompt_tokens': 123})):
                if error is not None and not isinstance(error, LocalStop):
                    with self.assertRaises(type(error)):
                        runner.main()
                else:
                    runner.main()
            return json.loads((root / 'calibration_only-result.json').read_text())

    def test_unexpected_local_error_cannot_claim_all_selected_processed(self):
        result = self.run_fixture(OSError('TEST_ONLY_JOURNAL_FAILURE'))
        self.assertEqual(result['status'], 'FAILED_LOCAL_ERROR')
        self.assertEqual(result['processed_cases'], 0)
        self.assertEqual(result['unattempted_or_interrupted_cases'], 1)
        self.assertEqual(result['failure_type'], 'OSError')

    def test_interrupt_cannot_claim_all_selected_processed(self):
        result = self.run_fixture(KeyboardInterrupt())
        self.assertEqual(result['status'], 'FAILED_LOCAL_ERROR')
        self.assertEqual(result['failure_type'], 'KeyboardInterrupt')

    def test_local_stop_remains_stopped_partial(self):
        result = self.run_fixture(LocalStop('RSI_LEDGER_PERSIST_FAILED'))
        self.assertEqual(result['status'], 'STOPPED_PARTIAL')
        self.assertEqual(result['stop_code'], 'RSI_LEDGER_PERSIST_FAILED')

    def test_normal_exhaustion_is_all_selected_processed(self):
        result = self.run_fixture()
        self.assertEqual(result['status'], 'ALL_SELECTED_CASES_PROCESSED')
        self.assertEqual(result['processed_cases'], result['selected_cases'])
        self.assertEqual(result['unattempted_or_interrupted_cases'], 0)


