from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from transport import Caller, LocalStop, guarded_open


class TransportTests(unittest.TestCase):
    def test_all_local_refusals_stop_including_persist_failed503(self):
        for status, code in ((503, 'RSI_LEDGER_PERSIST_FAILED'), (503, 'RSI_REQUEST_POLICY_INVALID'),
                             (429, 'RSI_MODEL_BUDGET_EXCEEDED'), (423, 'RSI_REQUEST_PAUSED')):
            error = HTTPError('local', status, 'test', {}, BytesIO(json.dumps({'detail': {'code': code}}).encode()))
            with patch('urllib.request.urlopen', side_effect=error):
                with self.assertRaisesRegex(LocalStop, code):
                    guarded_open(None)

    def test_started_and_error_keys_never_call_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            journal, ledger = directory / 'calls.jsonl', directory / 'usage.jsonl'
            request = {'test': 'same payload'}
            journal.write_text(json.dumps({'call_key': 'pending', 'request': request, 'status': 'started'}) + '\n' +
                json.dumps({'call_key': 'failed', 'request': request, 'status': 'error'}) + '\n', encoding='utf-8')
            caller = Caller(journal, ledger)
            with patch('urllib.request.urlopen', side_effect=AssertionError('Network forbidden')):
                self.assertEqual(caller('pending', request)['status'], 'started')
                self.assertEqual(caller('failed', request)['status'], 'error')
            self.assertFalse(ledger.exists())

    def test_retained_local_refusal_still_stops_without_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'calls.jsonl'
            path.write_text(json.dumps({'call_key': 'stop', 'request': {}, 'status': 'local_stop',
                'code': 'RSI_LEDGER_PERSIST_FAILED'}) + '\n', encoding='utf-8')
            caller = Caller(path, Path(tmp) / 'usage.jsonl')
            with patch('urllib.request.urlopen', side_effect=AssertionError('Network forbidden')):
                with self.assertRaisesRegex(LocalStop, 'RSI_LEDGER_PERSIST_FAILED'):
                    caller('stop', {})

    def test_upstream503_without_local_code_remains_transport_error(self):
        error = HTTPError('upstream', 503, 'test', {}, BytesIO(b'{"detail":"unavailable"}'))
        with patch('urllib.request.urlopen', side_effect=error):
            with self.assertRaises(HTTPError):
                guarded_open(None)
