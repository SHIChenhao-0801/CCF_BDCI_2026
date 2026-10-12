"""Resume only frozen never-attempted items; default execution makes zero API calls."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from threading import Event
import time
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[1]
ORIGINAL = PROJECT / 'process/replication600'
CONTINUATION = PROJECT / 'process/replication600-continuation'
COMPLETION = PROJECT / 'process/replication600-completion'
TASK_ID = 'reasoning-replication600-resume-20261008'
sys.path.insert(0, str(ORIGINAL))
spec = importlib.util.spec_from_file_location('frozen_original_replication', ORIGINAL / 'run.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
runner.TASK_ID = TASK_ID


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def journal(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()] if path.exists() else []


def classify(events):
    records = {}
    for event in events:
        key = event['call_key']
        if event['status'] == 'started':
            assert key not in records, 'Duplicate request identity'
        else:
            assert key in records and records[key]['status'] == 'started'
            assert event['status'] in ('ok', 'error')
        records[key] = event
    return records


def directories():
    return [ORIGINAL, CONTINUATION] + [COMPLETION / 'workers' / str(i) for i in range(3)]


def missing_record(record, directory):
    return {'id': record['call_key'].split(':')[1], 'call_key': record['call_key'],
            'phase': directory.parent.parent.name if directory.parent.name == 'workers' else directory.name,
            'worker': directory.name if directory.parent.name == 'workers' else None,
            'request_state': 'unknown' if record['status'] == 'started' else 'error',
            'http_status': record.get('http_status'), 'error_type': record.get('error_type'),
            'usage_is_unknown': True, 'never_resend': True}


def old_state():
    tasks, manifest = load(ORIGINAL / 'dataset.json'), load(ORIGINAL / 'manifest.json')
    records, rows, missing = {}, [], []
    for directory in directories():
        component = classify(journal(directory / 'calls.jsonl'))
        assert records.keys().isdisjoint(component), 'Historical request was repeated'
        records.update(component)
        rowfile = 'completion-rows.json' if directory.parent.name == 'workers' else 'eval-results.json'
        rows.extend(load(directory / rowfile))
        missing.extend(missing_record(record, directory) for record in component.values() if record['status'] != 'ok')
    by_id = {task['id']: task for task in tasks}
    complete_ids, missing_ids = {row['id'] for row in rows}, {row['id'] for row in missing}
    assert len(tasks) == len(by_id) == 600 and len(rows) == len(complete_ids)
    assert len(missing) == len(missing_ids) and complete_ids.isdisjoint(missing_ids)
    attempted = {key.split(':')[1] for key in records}
    assert attempted == complete_ids | missing_ids
    for row in rows:
        for arm in runner.ARMS:
            record = records[row[arm]['call_key']]
            assert record['status'] == 'ok'
            assert runner.baseline.check(by_id[row['id']], record['content'])[0] == row[arm]['correct']
    remaining = [task for task in tasks if task['id'] not in attempted]
    assert len(rows) + len(missing) + len(remaining) == 600
    return tasks, manifest, rows, records, missing, remaining


def verify_registration():
    ready, plan = load(ROOT / 'ready.json'), load(ROOT / 'resume-plan.json')
    assert ready['model_calls'] == 0
    assert all(sha(ROOT / name) == expected for name, expected in ready['sha256'].items())
    assert all(sha(Path(name)) == expected for name, expected in ready['old_input_sha256'].items())
    state = old_state()
    assert [task['id'] for task in state[-1]] == plan['unattempted_ids']
    assert state[-2] == plan['old_missing_items']
    assert plan['administrative_worker_count'] == 2
    assert all(plan['worker_ids'][str(i)] == plan['unattempted_ids'][i::2] for i in range(2))
    return state


class LocalGuardRefusal(Exception):
    def __init__(self, code):
        self.code = code


def guarded_open(opener, *args, **kwargs):
    try:
        return opener(*args, **kwargs)
    except HTTPError as error:
        if error.code in (402, 423):
            raise LocalGuardRefusal(error.code) from None
        if error.code in (429, 503):
            try:
                detail = json.loads(error.read(8192)).get('detail', '')
            except (ValueError, TypeError):
                detail = ''
            code = detail.get('code') if isinstance(detail, dict) else None
            if code in ('RSI_MODEL_BUDGET_EXCEEDED', 'RSI_REQUEST_POLICY_INVALID',
                        'RSI_REQUEST_PAUSED', 'RSI_REQUEST_DEADLINE'):
                raise LocalGuardRefusal(error.code) from None
        raise


def execute_worker(index, tasks, dataset_hash, stopped, directory=None):
    directory = directory or ROOT / 'workers' / str(index)
    if not directory.exists():
        directory.mkdir(parents=True, exist_ok=False)
    elif directory == ROOT / 'workers' / str(index):
        raise FileExistsError('Never resume or overwrite a started worker')
    assert not (directory / 'calls.jsonl').exists()
    ledger, rows, missing, terminals = directory / 'model_calls.jsonl', [], [], []
    for task in tasks:
        assert not stopped.is_set(), 'Another worker stopped the phase'
        try:
            result = runner.execute([task], directory, ledger, dataset_hash)
        except Exception as error:
            records = classify(journal(directory / 'calls.jsonl'))
            failed = [record for record in records.values()
                      if record['call_key'].split(':')[1] == task['id'] and record['status'] != 'ok']
            if len(failed) != 1 or not isinstance(error, RuntimeError):
                stopped.set()
                raise
            record = failed[0]
            if record.get('http_status') in (402, 423) or record.get('error_type') == 'LocalGuardRefusal':
                stopped.set()
                raise
            if record['status'] != 'started' and record.get('error_type') not in ('HTTPError', 'TimeoutError', 'URLError'):
                stopped.set()
                raise
            missing.append(missing_record(record, directory))
            terminals.append({'id': task['id'], 'state': 'missing', 'call_key': record['call_key']})
        else:
            rows.extend(result)
            terminals.append({'id': task['id'], 'state': 'complete'})
        write(directory / 'completion-rows.json', rows)
        write(directory / 'missing.json', missing)
        write(directory / 'terminal-items.json', terminals)
    return rows, missing, classify(journal(directory / 'calls.jsonl'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-eval', action='store_true')
    parser.add_argument('--smoke-test', action='store_true')
    parser.add_argument('--output', type=Path, default=ROOT / 'smoke.json')
    args = parser.parse_args()
    assert not (args.run_eval and args.smoke_test)
    assert args.output.resolve().is_relative_to(ROOT)
    tasks, manifest, old_rows, old_records, missing, remaining = verify_registration()
    summary = {'status': 'OFFLINE_READY_NO_API', 'model_call_count': 0, 'planned_items': 600,
               'previous_complete_rows': len(old_rows), 'old_missing_items': len(missing),
               'remaining_unattempted_rows': len(remaining), 'maximum_new_calls': len(remaining) * 4,
               'statistics_computed': False}
    if args.run_eval:
        assert not (ROOT / 'workers').exists(), 'No automatic restart of this paid phase'
        preflight = load(ROOT / 'execution-preflight.json')
        assert preflight['root_authorized_paid_start'] and preflight['request_policy_tests'] == 'PASS'
        assert preflight['ledger_reset'] is False
        policy = load(PROJECT / 'process/flight-policy.json')
        authorization = load(PROJECT / 'process/resume-authorization-and-budget-20261008.json')
        assert not policy['paused'] and policy.get('resume_authorization') == authorization['authorization'], 'Explicit human continuation authorization required'
        started, stopped, new_rows, new_records = time.perf_counter(), Event(), [], {}
        opener = runner.baseline.urllib.request.urlopen
        runner.baseline.urllib.request.urlopen = lambda *a, **k: guarded_open(opener, *a, **k)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(execute_worker, i, remaining[i::2], manifest['dataset_sha256'], stopped) for i in range(2)]
            for future in futures:
                rows, failed, records = future.result()
                assert old_records.keys().isdisjoint(records) and new_records.keys().isdisjoint(records)
                new_rows.extend(rows)
                missing.extend(failed)
                new_records.update(records)
        ordered = {task['id']: i for i, task in enumerate(tasks)}
        new_rows.sort(key=lambda row: ordered[row['id']])
        complete = sorted(old_rows + new_rows, key=lambda row: ordered[row['id']])
        assert len(complete) + len(missing) == 600
        assert len(complete) <= 592 and len(missing) >= 8
        assert {row['id'] for row in complete}.isdisjoint(item['id'] for item in missing)
        write(ROOT / 'completion-rows.json', new_rows)
        write(ROOT / 'missing.json', missing)
        for name in ('calls.jsonl', 'model_calls.jsonl'):
            events = [event for i in range(2) for event in journal(ROOT / 'workers' / str(i) / name)]
            (ROOT / name).write_text(''.join(json.dumps(event, ensure_ascii=False) + '\n' for event in events), encoding='utf-8')
        records = {**old_records, **new_records}
        summary = runner.metrics(complete, records)
        summary.update(status='COMPLETED_WITH_DECLARED_MISSING', protocol='replication600-operational-resume-20261008',
                       planned_eval_count=600, observed_complete_cases=len(complete), missing_count=len(missing),
                       missing_ids=sorted(item['id'] for item in missing), administrative_worker_count=2,
                       resume_elapsed_seconds=time.perf_counter() - started, statistics_computed=True,
                       unchanged_registered600_completed=False, ledger_reset=False,
                       claim_scope='Disclosed transport/pause amendments; complete-case N<=592; no MCAR; no pooling with120/24; not a new complete Agent workflow')
        write(ROOT / 'results.json', {'metrics': summary, 'rows': complete})
    write(args.output, summary)
    print(json.dumps({k: summary[k] for k in summary if k in ('status', 'model_call_count', 'planned_items',
        'previous_complete_rows', 'old_missing_items', 'remaining_unattempted_rows', 'maximum_new_calls',
        'observed_complete_cases', 'missing_count', 'statistics_computed')}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
