"""First official freeze after scope correction; zero supplier/model requests."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
assert not (ROOT / 'ready.json').exists() and not (ROOT / 'calls.jsonl').exists()
files = sorted(path for path in ROOT.iterdir() if path.is_file())
selection = json.loads((ROOT / 'cases.json').read_text(encoding='utf-8'))
assert len(selection['cases']) == 375 and selection['SAT_localization_ablation_planned_cases'] == 166
report = {'status': 'OFFLINE_FROZEN_LIVE_FEASIBILITY_UNPROVEN',
    'frozen_before_first_followup_call_utc': datetime.now(timezone.utc).isoformat(),
    'model_calls': 0, 'supplier_requests': 0, 'tests': '17PASS',
    'planned_primary_cases': 375, 'planned_SAT_ablation_cases': 166,
    'no_invented_ok_fields': True, 'retained_initial_feedback_unchanged': True,
    'prior_unfrozen_candidate_superseded_before_calls': True,
    'sha256': {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in files}}
(ROOT / 'ready.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({key: report[key] for key in ('status', 'model_calls', 'supplier_requests', 'tests',
    'planned_primary_cases', 'planned_SAT_ablation_cases')}))
