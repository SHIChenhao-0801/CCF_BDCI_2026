"""Register the operational v2 fix without replacing the retained v1 evidence."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
archive = ROOT / 'prior-v1-prelive'
v1 = json.loads((archive / 'ready.json').read_text(encoding='utf-8-sig'))
assert (ROOT / 'ready.json').read_bytes() == (archive / 'ready.json').read_bytes(), 'Only replace the original v1 freeze once'
assert not any((ROOT / name).exists() for name in ('calls.jsonl', 'model_calls.jsonl', 'calibration_only-started.json', 'full_followup-started.json')), 'No live follow-up before registration'
for name, digest in v1['sha256'].items():
    assert sha(archive / name) == digest, 'Archived v1 changed: ' + name
    if name not in ('runner.py', 'transport.py'):
        assert sha(ROOT / name) == digest, 'Unrelated/scientific v1 artifact changed: ' + name
log = (ROOT / 'operational-v2-green.log').read_text(encoding='utf-8-sig')
assert 'Ran 28 tests' in log and '\nOK' in log
project = ROOT.parents[1]
ledger_path = project / 'process/model-budget.json'
policy_path = project / 'process/request-policy.json'
ledger_raw = ledger_path.read_bytes()
policy_raw = policy_path.read_bytes()
ledger = json.loads(ledger_raw)
policy = json.loads(policy_raw)
assert policy['paused'] is True and not ledger['active_reservations']
registration = {
    'version': 2, 'status': 'BEFORE_FIRST_CALL_ZEROAPI_OPERATIONAL_AMENDMENT',
    'registered_at_utc': datetime.now(timezone.utc).isoformat(),
    'prior_v1_ready_sha256': sha(archive / 'ready.json'),
    'scope': 'failure reporting and exact known-usage recovery only',
    'scientific_v1_files_unchanged': True, 'supplier_requests': 0, 'model_calls': 0,
    'shared_ledger_sha256': hashlib.sha256(ledger_raw).hexdigest(),
    'request_policy_sha256': hashlib.sha256(policy_raw).hexdigest(),
    'paused': True, 'active_reservations': {},
    'charged_micro_cny': ledger['charged_micro_cny'],
    'unmetered_calls': ledger['unmetered_calls'],
    'existing_amendment_preserved': 'registration-amendment.json',
}
(ROOT / 'registration-amendment-v2.json').write_text(json.dumps(registration, indent=2) + '\n', encoding='utf-8')
files = sorted(path for path in ROOT.iterdir() if path.is_file() and path.name != 'ready.json')
report = dict(v1)
report.update(version=2, tests='28PASS', frozen_before_first_followup_call_utc=registration['registered_at_utc'],
              prior_v1_ready_sha256=registration['prior_v1_ready_sha256'],
              operational_amendment='OPERATIONAL_AMENDMENT_V2.md',
              scientific_v1_files_unchanged=True, sha256={path.name: sha(path) for path in files})
assert ledger_path.read_bytes() == ledger_raw and policy_path.read_bytes() == policy_raw
pending = ROOT / 'ready.json.v2.tmp'
pending.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
os.replace(pending, ROOT / 'ready.json')
print(json.dumps({'version': 2, 'tests': report['tests'], 'frozen_files': len(files),
                  'ready_sha256': sha(ROOT / 'ready.json'), 'scientific_v1_files_unchanged': True,
                  'paused': True, 'supplier_requests': 0, 'model_calls': 0}))
