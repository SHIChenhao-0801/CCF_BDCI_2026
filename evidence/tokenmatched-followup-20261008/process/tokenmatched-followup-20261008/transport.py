"""Auditable future transport; importing/constructing it never sends a request."""
from datetime import datetime, timezone
import json
import os
import time
from urllib.error import HTTPError
import urllib.request


class LocalStop(Exception):
    pass


LOCAL_CODES = {'RSI_REQUEST_PAUSED', 'RSI_REQUEST_DEADLINE', 'RSI_REQUEST_POLICY_INVALID',
               'RSI_MODEL_BUDGET_EXCEEDED', 'RSI_LEDGER_PERSIST_FAILED'}


def guarded_open(request):
    try:
        return urllib.request.urlopen(request, timeout=180)
    except HTTPError as error:
        try:
            body = json.loads(error.read())
            detail = body.get('detail', {})
            code = detail.get('code') if isinstance(detail, dict) else None
        except (ValueError, OSError):
            code = None
        if error.code in (402, 423) or code in LOCAL_CODES:
            raise LocalStop(code or 'local_HTTP_' + str(error.code)) from error
        raise


class Caller:
    def __init__(self, journal, ledger):
        self.journal, self.ledger = journal, ledger
        self.records = {}
        try:
            if journal.exists():
                for line in journal.read_text(encoding='utf-8').splitlines():
                    record = json.loads(line)
                    prior = self.records.get(record['call_key'])
                    if prior and (prior['request'] != record['request'] or (prior['status'] == 'ok' and prior != record)):
                        raise LocalStop('STUDY_CALL_IDENTITY_CONFLICT')
                    self.records[record['call_key']] = record
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise LocalStop('STUDY_JOURNAL_INVALID_OR_UNREADABLE') from error
        self.reconcile_usage()

    def reconcile_usage(self):
        """Derive only known usage; validate the whole ledger before appending gaps."""
        expected = {}
        try:
            for record in self.records.values():
                if record['status'] != 'ok':
                    continue
                usage, request, key = record['usage'], record['request'], record['call_key']
                identifier = record['response_id']
                cache = usage.get('prompt_cache_hit_tokens', 0)
                assert isinstance(identifier, str) and identifier and identifier not in expected
                assert type(usage['prompt_tokens']) is int and usage['prompt_tokens'] > 0
                assert type(usage['completion_tokens']) is int and 0 <= usage['completion_tokens'] <= request['max_tokens']
                assert type(usage['total_tokens']) is int and usage['total_tokens'] == usage['prompt_tokens'] + usage['completion_tokens']
                assert type(cache) is int and 0 <= cache <= usage['prompt_tokens']
                expected[identifier] = {'call_id': identifier, 'call_key': key, 'task_id': 'tokenmatched-followup-20261008',
                    'provenance': 'calibration_probe' if ':probe:' in key else 'fresh_retry_followup',
                    'model_call': {'model': request['model'], 'status': 'succeeded', 'call_count': 1,
                        'tokens': {'input': usage['prompt_tokens'], 'output': usage['completion_tokens'], 'cache_hit': cache}}}
            seen = set()
            if self.ledger.exists():
                for line in self.ledger.read_text(encoding='utf-8').splitlines():
                    entry = json.loads(line)
                    identifier = entry['call_id']
                    if identifier in seen or entry != expected.get(identifier):
                        raise LocalStop('STUDY_USAGE_LEDGER_CONFLICT')
                    seen.add(identifier)
        except (ValueError, KeyError, TypeError, AssertionError) as error:
            raise LocalStop('STUDY_USAGE_LEDGER_INVALID') from error
        except OSError as error:
            raise LocalStop('STUDY_USAGE_LEDGER_IO') from error
        try:
            for identifier, entry in expected.items():
                if identifier not in seen:
                    self.append(self.ledger, entry)
        except OSError as error:
            raise LocalStop('STUDY_USAGE_LEDGER_IO') from error

    @staticmethod
    def append(path, record):
        with path.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + '\n')
            stream.flush()
            os.fsync(stream.fileno())

    def __call__(self, key, request):
        if key in self.records:
            prior = self.records[key]
            if prior['request'] != request:
                raise LocalStop('STUDY_CALL_IDENTITY_CONFLICT')
            if prior['status'] == 'local_stop':
                raise LocalStop(prior['code'])
            if prior['status'] == 'ok':
                self.reconcile_usage()
            return prior  # Known evidence reused; started/error/unknown never resent.
        base = {'call_key': key, 'request': request, 'started_at_utc': datetime.now(timezone.utc).isoformat()}
        pending = {**base, 'status': 'started'}
        self.append(self.journal, pending)  # Persist before admission/network.
        self.records[key] = pending
        started = time.perf_counter()
        try:
            req = urllib.request.Request('http://127.0.0.1:19081/v1/chat/completions',
                data=json.dumps(request).encode(), headers={'Content-Type': 'application/json', 'Authorization': 'Bearer local-proxy-key'})
            with guarded_open(req) as response:
                body = json.load(response)
            usage = body['usage']
            assert type(usage['prompt_tokens']) is int and usage['prompt_tokens'] > 0
            assert type(usage['completion_tokens']) is int and 0 <= usage['completion_tokens'] <= request['max_tokens']
            assert usage['total_tokens'] == usage['prompt_tokens'] + usage['completion_tokens']
            cache = usage.get('prompt_cache_hit_tokens') or 0
            assert type(cache) is int and 0 <= cache <= usage['prompt_tokens']
            response_id = body['id']
            assert isinstance(response_id, str) and response_id and response_id not in {r.get('response_id') for r in self.records.values()}
            record = {**base, 'status': 'ok', 'usage': usage, 'response_id': response_id,
                      'response_model': body.get('model'), 'content': body['choices'][0]['message'].get('content') or '',
                      'latency_seconds': time.perf_counter() - started}
        except LocalStop as error:
            self.append(self.journal, {**base, 'status': 'local_stop', 'code': str(error)})
            raise
        except (HTTPError, TimeoutError, urllib.error.URLError) as error:
            record = {**base, 'status': 'error', 'error_type': type(error).__name__,
                      'http_status': getattr(error, 'code', None), 'usage_unknown': True,
                      'not_proof_of_billed_request': True, 'latency_seconds': time.perf_counter() - started}
        except Exception as error:
            self.append(self.journal, {**base, 'status': 'local_stop', 'code': 'INVALID_RESPONSE_OR_ACCOUNTING:' + type(error).__name__})
            raise LocalStop('INVALID_RESPONSE_OR_ACCOUNTING') from error
        self.append(self.journal, record)
        self.records[key] = record
        if record['status'] == 'ok':
            self.reconcile_usage()
        return record
