"""Operational failure recovery must preserve known usage without model retries."""
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from transport import Caller, LocalStop

KEY = 'tokenmatched-followup-20261008:fixture:probe:full:pad0'
REQUEST = {'model': 'deepseek-flash', 'max_tokens': 1}
RAW = {'call_key': KEY, 'request': REQUEST, 'status': 'ok', 'response_id': 'fixture-response',
       'usage': {'prompt_tokens': 11, 'completion_tokens': 1, 'total_tokens': 12}, 'content': 'UNSCORED'}
EXPECTED = {'call_id': 'fixture-response', 'call_key': KEY, 'task_id': 'tokenmatched-followup-20261008',
            'provenance': 'calibration_probe', 'model_call': {'model': 'deepseek-flash', 'status': 'succeeded',
            'call_count': 1, 'tokens': {'input': 11, 'output': 1, 'cache_hit': 0}}}


class RecoveryTests(unittest.TestCase):
    def test_known_raw_ok_repairs_missing_usage_once_without_network(self):
        with tempfile.TemporaryDirectory() as temp:
            journal, ledger = Path(temp) / 'calls.jsonl', Path(temp) / 'usage.jsonl'
            journal.write_text(json.dumps(RAW) + '\n', encoding='utf-8')
            with patch('urllib.request.urlopen', side_effect=AssertionError('Network forbidden')):
                caller = Caller(journal, ledger)
                self.assertEqual(caller(KEY, REQUEST), RAW)
                self.assertEqual(Caller(journal, ledger)(KEY, REQUEST), RAW)
            self.assertTrue(ledger.exists(), 'Known raw OK requires a matching usage record')
            self.assertEqual([json.loads(line) for line in ledger.read_text(encoding='utf-8').splitlines()], [EXPECTED])

    def test_exact_existing_usage_is_not_appended_again(self):
        with tempfile.TemporaryDirectory() as temp:
            journal, ledger = Path(temp) / 'calls.jsonl', Path(temp) / 'usage.jsonl'
            journal.write_text(json.dumps(RAW) + '\n', encoding='utf-8')
            ledger.write_text(json.dumps(EXPECTED) + '\n', encoding='utf-8')
            before = ledger.read_bytes()
            with patch('urllib.request.urlopen', side_effect=AssertionError('Network forbidden')):
                Caller(journal, ledger)(KEY, REQUEST)
            self.assertEqual(ledger.read_bytes(), before)

    def test_conflicting_duplicate_or_orphan_usage_stops_without_rewrite(self):
        bad = {**EXPECTED, 'model_call': {**EXPECTED['model_call'], 'tokens': {'input': 99, 'output': 1, 'cache_hit': 0}}}
        orphan = {**EXPECTED, 'call_id': 'orphan', 'call_key': 'orphan'}
        for records in ([bad], [EXPECTED, EXPECTED], [orphan]):
            with self.subTest(records=records), tempfile.TemporaryDirectory() as temp:
                journal, ledger = Path(temp) / 'calls.jsonl', Path(temp) / 'usage.jsonl'
                journal.write_text(json.dumps(RAW) + '\n', encoding='utf-8')
                ledger.write_text(''.join(json.dumps(r) + '\n' for r in records), encoding='utf-8')
                before = ledger.read_bytes()
                with patch('urllib.request.urlopen', side_effect=AssertionError('Network forbidden')):
                    with self.assertRaises(LocalStop):
                        Caller(journal, ledger)
                self.assertEqual(ledger.read_bytes(), before)

    def test_conflicting_raw_identity_and_response_id_stop(self):
        for second in ({**RAW, 'request': {**REQUEST, 'max_tokens': 2048}},
                       {**RAW, 'call_key': KEY + ':different'}):
            with self.subTest(second=second), tempfile.TemporaryDirectory() as temp:
                journal, ledger = Path(temp) / 'calls.jsonl', Path(temp) / 'usage.jsonl'
                journal.write_text(json.dumps(RAW) + '\n' + json.dumps(second) + '\n', encoding='utf-8')
                with self.assertRaises(LocalStop):
                    Caller(journal, ledger)
                self.assertFalse(ledger.exists())

    def test_incomplete_usage_ledger_is_preserved_and_stops(self):
        with tempfile.TemporaryDirectory() as temp:
            journal, ledger = Path(temp) / 'calls.jsonl', Path(temp) / 'usage.jsonl'
            journal.write_text(json.dumps(RAW) + '\n', encoding='utf-8')
            ledger.write_text('{"partial":', encoding='utf-8')
            before = ledger.read_bytes()
            with self.assertRaises(LocalStop):
                Caller(journal, ledger)
            self.assertEqual(ledger.read_bytes(), before)

    def test_usage_append_failure_after_raw_ok_stops_and_recovers_without_resend(self):
        for wrote_complete_record in (False, True):
            with self.subTest(wrote_complete_record=wrote_complete_record), tempfile.TemporaryDirectory() as temp:
                journal, ledger = Path(temp) / 'calls.jsonl', Path(temp) / 'usage.jsonl'
                original = Caller.append
                def refuse(path, record):
                    if path == ledger:
                        if wrote_complete_record:
                            original(path, record)
                        raise OSError('TEST_ONLY_USAGE_APPEND_FAILURE')
                    original(path, record)
                response = {'id': RAW['response_id'], 'model': REQUEST['model'], 'usage': RAW['usage'],
                            'choices': [{'message': {'content': RAW['content']}}]}
                caller = Caller(journal, ledger)
                with patch.object(Caller, 'append', staticmethod(refuse)), patch('urllib.request.urlopen', return_value=BytesIO(json.dumps(response).encode())):
                    with self.assertRaises(LocalStop):
                        caller(KEY, REQUEST)
                with patch('urllib.request.urlopen', side_effect=AssertionError('Network forbidden')):
                    retained = Caller(journal, ledger)(KEY, REQUEST)
                self.assertEqual(retained['status'], 'ok')
                self.assertEqual([json.loads(line) for line in ledger.read_text(encoding='utf-8').splitlines()], [EXPECTED])

    def test_started_or_failed_records_never_get_invented_usage(self):
        with tempfile.TemporaryDirectory() as temp:
            journal, ledger = Path(temp) / 'calls.jsonl', Path(temp) / 'usage.jsonl'
            journal.write_text(json.dumps({'call_key': KEY, 'request': REQUEST, 'status': 'started'}) + '\n', encoding='utf-8')
            with patch('urllib.request.urlopen', side_effect=AssertionError('Network forbidden')):
                self.assertEqual(Caller(journal, ledger)(KEY, REQUEST)['status'], 'started')
            self.assertFalse(ledger.exists())
