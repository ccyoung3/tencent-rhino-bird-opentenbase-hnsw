import unittest
import subprocess
import sys
from pathlib import Path

import bounded_recall
import bounded_overhead
import glove


class BoundedRecallTest(unittest.TestCase):
    def test_formal_holdout_not_previously_exposed(self):
        old = glove.query_split(10000)
        new = bounded_recall.splits()
        self.assertEqual(new["tuning"], old["tuning"])
        self.assertEqual(len(new["validation"]), 1000)
        self.assertFalse(set(new["validation"]) & set(old["tuning"] + old["validation"]))
        smoke = bounded_recall.splits(True)
        self.assertFalse(set(new["validation"]) & set(smoke["tuning"] + smoke["validation"]))

    def test_fixed_budget_and_selection(self):
        self.assertEqual(len(bounded_recall.CONFIGS), 3)
        self.assertEqual(max(bounded_recall.EFS), 1000)
        self.assertEqual(glove.select_ef([{"ef_search": 800, "mean_recall": .95},
                                         {"ef_search": 1000, "mean_recall": .97}], .95), 800)


class CostBoundTest(unittest.TestCase):
    def test_new_cli_help(self):
        for name in ("observe.py", "bounded_recall.py", "bounded_overhead.py"):
            result = subprocess.run([sys.executable, str(Path(__file__).with_name(name)), "--help"], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr.decode())

    def test_small_sample_has_no_finite_bound(self):
        self.assertIsNone(bounded_overhead.upper_median_bound([1., 1.])['upper_ratio'])

    def test_exact_conservative_rank(self):
        result = bounded_overhead.upper_median_bound([1+i*.01 for i in range(12)])
        self.assertEqual(result['rank'], 10)
        self.assertAlmostEqual(result['upper_ratio'], 1.09)
        self.assertGreaterEqual(result['coverage'], .95)

    def test_reject_nonfinite_and_incomplete(self):
        for values in ([], [float('nan')], [0], [-1]):
            with self.assertRaises(ValueError):
                bounded_overhead.upper_median_bound(values)
        with self.assertRaises(ValueError):
            bounded_overhead.summarize([], 12)

    def test_paired_reference_not_ratio_of_medians(self):
        rows = []
        for workers in (0, 2):
            for spill in (False, True):
                for block in range(12):
                    for variant, value in [('old_off', 1), ('new_off', 1.01), ('new_on', 1.02), ('new_observed', 1.2)]:
                        rows.append(dict(workers=workers, spill=spill, block=block, variant=variant, command_seconds=value,
                            observer={"observation": {"phases": [{"phase": "loading"}], "samples": 1}}))
        groups = bounded_overhead.summarize(rows, 12)
        self.assertEqual(len(groups), 12)
        self.assertTrue(all(g['verdict'] == 'not_established' for g in groups if g['effect'] == 'observer'))
        rows[3]["observer"] = {}
        self.assertEqual(bounded_overhead.summarize(rows, 12)[2]["verdict"], "insufficient_observation_coverage")
        with self.assertRaises(ValueError):
            bounded_overhead.summarize(rows + rows[:1], 12)


if __name__ == "__main__":
    unittest.main()
