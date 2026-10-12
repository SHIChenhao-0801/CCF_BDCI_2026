import unittest

from analysis import comparison


class AnalysisTests(unittest.TestCase):
    def test_paired_exact_and_missing_bounds_have_distinct_denominators(self):
        result = comparison([(True, False)] * 3 + [(False, True)], 6)
        self.assertEqual(result['valid'], 4)
        self.assertEqual(result['exact_McNemar_two_sided'], 0.625)
        self.assertEqual(result['difference'], 0.5)
        self.assertEqual(result['planned_possible_outcome_difference_bounds_not_CI'], [0, 4/6])

    def test_no_valid_pairs_does_not_emit_a_fabricated_p_value(self):
        self.assertIsNone(comparison([], 375)['exact_McNemar_two_sided'])
