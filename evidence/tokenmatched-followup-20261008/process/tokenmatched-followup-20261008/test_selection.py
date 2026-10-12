import json
from pathlib import Path
import unittest

from study import messages


class SelectionTests(unittest.TestCase):
    def test375_unique_error_cases_and_SAT_only166_ablation(self):
        dataset = json.loads((Path(__file__).parent / 'cases.json').read_text(encoding='utf-8'))
        cases = dataset['cases']
        self.assertEqual(len(cases), 375)
        self.assertEqual(len({case['task']['id'] for case in cases}), 375)
        self.assertEqual(sum('coarse' in case['retry_order'] for case in cases), 166)
        for case in cases:
            feedback = case['initial_feedback']
            full = messages(case, 'full', 0)[-1]['content'].split('Deterministic checker feedback: ')[1].split('\n')[0]
            self.assertEqual(json.loads(full), feedback)
            self.assertNotIn('ok', json.loads(full))
            if 'coarse' in case['retry_order']:
                coarse = messages(case, 'coarse', 0)[-1]['content'].split('Deterministic checker feedback: ')[1].split('\n')[0]
                self.assertEqual(json.loads(coarse), {'error': feedback['error']})
                self.assertEqual(case['task']['family'], 'sat')
            else:
                self.assertEqual(set(case['retry_order']), {'full', 'neutral'})
