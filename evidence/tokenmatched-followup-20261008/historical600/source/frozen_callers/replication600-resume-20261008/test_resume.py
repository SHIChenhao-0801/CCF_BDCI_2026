import io
import json
from pathlib import Path
import tempfile
from threading import Event
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import resume as r


class ResumeTests(unittest.TestCase):
    def test_historical_partition_excludes_every_started_or_failed_item(self):
        tasks, manifest, rows, records, missing, remaining = r.old_state()
        self.assertEqual((len(tasks), len(rows), len(missing), len(remaining)), (600, 412, 8, 180))
        self.assertEqual(len({key.split(':')[1] for key in records}), 420)
        self.assertEqual(sum(item['request_state'] == 'unknown' for item in missing), 3)
        self.assertEqual(manifest['dataset_sha256'][:12], '7adae0c2cfac')
        self.assertTrue({t['id'] for t in remaining}.isdisjoint({key.split(':')[1] for key in records}))

    def test_duplicate_start_cannot_be_hidden_by_terminal_record(self):
        event = {'call_key': 'prefix:item:initial', 'status': 'started'}
        with self.assertRaises(AssertionError):
            r.classify([event, event, {**event, 'status': 'ok'}])

    def test_started_without_terminal_remains_unknown(self):
        event = {'call_key': 'prefix:item:initial', 'status': 'started'}
        self.assertEqual(r.classify([event])[event['call_key']]['status'], 'started')

    def response(self, task):
        return io.BytesIO(json.dumps({'id': 'response-' + task['id'], 'model': 'deepseek-flash',
            'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15},
            'choices': [{'message': {'content': json.dumps(task['oracle'])}, 'finish_reason': 'stop'}]}).encode())

    def test_timeout_missing_does_not_retry_and_next_unattempted_item_runs(self):
        tasks = r.old_state()[-1][:2]
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            with patch.object(r.runner.baseline.urllib.request, 'urlopen', side_effect=[TimeoutError(), self.response(tasks[1])]) as network:
                rows, missing, records = r.execute_worker(0, tasks, '7adae0c2cfac', Event(), directory)
            self.assertEqual(network.call_count, 2)
            self.assertEqual([row['id'] for row in rows], [tasks[1]['id']])
            self.assertEqual([item['id'] for item in missing], [tasks[0]['id']])
            self.assertEqual(missing[0]['request_state'], 'error')
            self.assertEqual(len(records), 2)
            self.assertEqual(json.loads((directory / 'terminal-items.json').read_text())[0]['state'], 'missing')

    def test_unknown_start_missing_is_never_reissued(self):
        task = r.old_state()[-1][0]
        def interrupted(tasks, directory, ledger, dataset_hash):
            event = {'call_key': dataset_hash + ':' + tasks[0]['id'] + ':initial', 'status': 'started'}
            (directory / 'calls.jsonl').write_text(json.dumps(event) + '\n')
            raise RuntimeError('Interrupted request')
        with tempfile.TemporaryDirectory() as tmp, patch.object(r.runner, 'execute', side_effect=interrupted) as execute:
            rows, missing, records = r.execute_worker(0, [task], '7adae0c2cfac', Event(), Path(tmp))
            self.assertEqual(execute.call_count, 1)
            self.assertFalse(rows)
            self.assertEqual(missing[0]['request_state'], 'unknown')

    def test_budget_or_pause_refusal_stops_without_attempting_next_task(self):
        tasks = r.old_state()[-1][:2]
        for code in (402, 423):
            with self.subTest(code=code), tempfile.TemporaryDirectory() as tmp:
                stopped = Event()
                error = HTTPError('http://127.0.0.1', code, 'Local refusal', {}, None)
                with patch.object(r.runner.baseline.urllib.request, 'urlopen', side_effect=error) as network:
                    with self.assertRaises(RuntimeError):
                        r.execute_worker(0, tasks, '7adae0c2cfac', stopped, Path(tmp))
                self.assertEqual(network.call_count, 1)
                self.assertTrue(stopped.is_set())

    def test_existing_worker_directory_is_not_overwritten_or_resumed(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(r, 'ROOT', Path(tmp)):
            (Path(tmp) / 'workers' / '0').mkdir(parents=True)
            with self.assertRaises(FileExistsError):
                r.execute_worker(0, [], '7adae0c2cfac', Event())

    def test_existing_unknown_key_in_original_caller_has_zero_network_requests(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'calls.jsonl'
            prior = {'call_key': '7adae0c2cfac:item:initial', 'status': 'started'}
            path.write_text(json.dumps(prior) + '\n')
            before = path.read_bytes()
            with patch.object(r.runner.baseline.urllib.request, 'urlopen') as network:
                self.assertEqual(r.runner.baseline.call(path, prior['call_key'], []), prior)
            network.assert_not_called()
            self.assertEqual(path.read_bytes(), before)

    def test_invalid_request_policy_503_stops_instead_of_becoming_transport_missing(self):
        body = io.BytesIO(b'{"detail":{"code":"RSI_REQUEST_POLICY_INVALID"}}')
        error = HTTPError('http://127.0.0.1', 503, 'Guard refusal', {}, body)
        with self.assertRaises(r.LocalGuardRefusal) as result:
            r.guarded_open(lambda: (_ for _ in ()).throw(error))
        self.assertEqual(result.exception.code, 503)

    def test_existing_proxy_429_budget_error_stops_without_next_attempt(self):
        tasks = r.old_state()[-1][:2]
        with tempfile.TemporaryDirectory() as tmp:
            stopped = Event()
            error = HTTPError('http://127.0.0.1', 429, 'Budget exceeded', {},
                              io.BytesIO(b'{"detail":{"code":"RSI_MODEL_BUDGET_EXCEEDED"}}'))
            def upstream(*args, **kwargs):
                raise error
            with patch.object(r.runner.baseline.urllib.request, 'urlopen', side_effect=lambda *a, **k: r.guarded_open(upstream, *a, **k)) as network:
                with self.assertRaises(RuntimeError):
                    r.execute_worker(0, tasks, '7adae0c2cfac', stopped, Path(tmp))
            self.assertEqual(network.call_count, 1)
            self.assertTrue(stopped.is_set())

    def test_real_upstream_503_retains_http_error(self):
        error = HTTPError('http://127.0.0.1', 503, 'Upstream unavailable', {}, io.BytesIO(b'{"detail":"upstream unavailable"}'))
        with self.assertRaises(HTTPError):
            r.guarded_open(lambda: (_ for _ in ()).throw(error))

    def test_shared_initial_isolated_retry_payloads_and_frozen_order_are_preserved(self):
        task = next(t for t in r.old_state()[-1] if t['family'] == 'arithmetic')
        payloads = []
        def upstream(request, **kwargs):
            payloads.append(json.loads(request.data))
            content = '{"answer":0}' if len(payloads) == 1 else json.dumps(task['oracle'])
            return io.BytesIO(json.dumps({'id': 'response-' + str(len(payloads)), 'model': 'deepseek-flash',
                'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15},
                'choices': [{'message': {'content': content}, 'finish_reason': 'stop'}]}).encode())
        with tempfile.TemporaryDirectory() as tmp, patch.object(r.runner.baseline.urllib.request, 'urlopen', side_effect=upstream):
            rows, missing, records = r.execute_worker(0, [task], '7adae0c2cfac', Event(), Path(tmp))
        self.assertEqual(len(payloads), 4)
        self.assertFalse(missing)
        self.assertEqual([key.rsplit(':', 1)[1] for key in records], ['initial'] + task['retry_order'])
        self.assertEqual([len(payload['messages']) for payload in payloads], [1, 3, 3, 3])
        self.assertTrue(all(payload['messages'][:2] == payloads[1]['messages'][:2] for payload in payloads[1:]))
        self.assertEqual(rows[0]['verifiedretry']['request_lengths'], rows[0]['lengthmatchedretry']['request_lengths'])


if __name__ == '__main__':
    unittest.main()
