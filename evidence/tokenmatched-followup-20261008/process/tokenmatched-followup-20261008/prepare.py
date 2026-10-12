"""Freeze the375 historical initial errors using the independently frozen scorer; zero API."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[1]
source = PROJECT / 'process/run14-input/run.py'
spec = importlib.util.spec_from_file_location('frozen_scorer', source)
scorer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scorer)
bundle_path = PROJECT / 'process/run14-input/dataset.json'
audit_path = PROJECT / 'process/replication600-independent-audit/resume-final-audit.json'
bundle = json.loads(bundle_path.read_text(encoding='utf-8'))
audit = json.loads(audit_path.read_text(encoding='utf-8'))
assert audit['status'] == 'PASS' and audit['observed_complete_pairs'] == 592
missing = set(audit['missing_ids'])
initial = {row['call_key'].split(':')[1]: row for row in bundle['raw_records']
           if row['status'] == 'ok' and row['call_key'].endswith(':initial')}
cases = []
for task in bundle['tasks']:
    if task['id'] in missing:
        continue
    record = initial[task['id']]
    correct, feedback = scorer.score(task, record['content'])
    if not correct:
        cases.append({'task': task, 'initial_content': record['content'], 'initial_feedback': feedback,
                      'historical_initial_call_key': record['call_key'], 'historical_initial_response_id': record['response_id'],
                      'historical_initial_request': record['request']})
assert len(cases) == 375
# Outcome-independent ID hashing within fixed family/difficulty strata. Cyclic assignments
# balance all6 permutations globally and within every frozen stratum to within one item.
rank = lambda case: (case['task']['family'], case['task']['difficulty'],
    hashlib.sha256(('tokenmatched-followup-order-v1:' + case['task']['id']).encode()).hexdigest())
cases.sort(key=rank)
permutations = list(itertools.permutations(('full', 'neutral', 'coarse')))
counts = {2: 0, 3: 0}
for case in cases:
    localized = case['task']['family'] == 'sat' and 'clause_index' in case['initial_feedback']
    choices = permutations if localized else [('full', 'neutral'), ('neutral', 'full')]
    count = counts[len(choices[0])]
    case['retry_order'] = list(choices[count % len(choices)])
    counts[len(choices[0])] += 1
    case['historical_retry_order'] = case['task'].pop('retry_order')
order_counts = Counter(','.join(case['retry_order']) for case in cases)
for size in (2, 3):
    group = [value for order, value in order_counts.items() if len(order.split(',')) == size]
    assert max(group) - min(group) <= 1
strata = sorted({(case['task']['family'], case['task']['difficulty']) for case in cases})
cells = {}
for family, difficulty in strata:
    subgroup = [case for case in cases if (case['task']['family'], case['task']['difficulty']) == (family, difficulty)]
    orders = Counter(','.join(case['retry_order']) for case in subgroup)
    assert max(orders.values()) - min(orders.values()) <= 1
    cells[family + ':' + difficulty] = {'N': len(subgroup), 'retry_order_counts': dict(orders)}
data = {'study_id': 'tokenmatched-followup-20261008-v1', 'planned_cases': 375,
    'source_population': '375known initial errors among592complete original600 cases; reused samples, not independent',
    'selected_using': ['historical_complete_case_membership', 'historical_initial_answer_correctness_only'],
    'selected_using_retry_outcomes': False, 'pool_with_prior600_or120': False,
    'order_seed': 'tokenmatched-followup-order-v1', 'retry_order_counts': dict(order_counts), 'cells': cells,
    'SAT_localization_ablation_planned_cases': counts[3],
    'source_sha256': {str(path.relative_to(PROJECT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (source, bundle_path, audit_path)}, 'cases': cases}
assert not (ROOT / 'cases.json').exists(), 'No post-outcome change to frozen375 selection'
(ROOT / 'cases.json').write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
(ROOT / 'case-ids.json').write_text(json.dumps([case['task']['id'] for case in cases], indent=2) + '\n', encoding='utf-8')
report = {'status': 'OFFLINE_SELECTION_VERIFIED', 'prepared_at_utc': datetime.now(timezone.utc).isoformat(),
    'planned_cases': 375, 'model_calls': 0, 'network_requests': 0, 'strata': cells, 'retry_order_counts': dict(order_counts),
    'historical_retry_usage_planning_reference': audit['statistics']['arm_usage_excludes_shared_initial']}
(ROOT / 'selection-check.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({key: report[key] for key in ('status', 'planned_cases', 'model_calls', 'network_requests', 'retry_order_counts')}))
