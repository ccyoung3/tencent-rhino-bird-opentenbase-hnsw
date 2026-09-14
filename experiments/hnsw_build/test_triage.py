import copy
import itertools
import subprocess
import sys
import unittest
from pathlib import Path

import triage_overhead as triage


def fixture(blocks=6, orders=6):
    rows = []
    for workers, spill in triage.SCENES:
        for study, count in (("A", blocks), ("B", orders)):
            for block in range(count):
                groups = [["old_off"] * 3, ["new_off"] * 3] if study == "A" else [
                    list(itertools.permutations(triage.CONDITIONS))[block]]
                for group in groups:
                    for position, variant in enumerate(group, 1):
                        rows.append(dict(study=study, workers=workers, spill=spill, block=block,
                            variant=variant, position=position, command_seconds=1., source=str(len(rows))))
    return rows


class TriageTest(unittest.TestCase):
    def test_help(self):
        result = subprocess.run([sys.executable, str(Path(triage.__file__)), "--help"], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode())

    def test_all_six_orders_balance_positions_and_predecessors(self):
        orders = list(itertools.permutations(triage.CONDITIONS))
        for condition in triage.CONDITIONS:
            for position in range(3):
                self.assertEqual(sum(order[position] == condition for order in orders), 2)
            for previous in set(triage.CONDITIONS) - {condition}:
                self.assertEqual(sum(order[p:p+2] == (previous, condition)
                                     for order in orders for p in (0, 1)), 2)

    def test_block_is_statistical_unit_not_each_build(self):
        rows = fixture()
        for row in rows:
            if row["study"] == "A" and row["variant"] == "new_off":
                row["command_seconds"] = 1 + row["block"] * .01 + {1: -.001, 2: 0, 3: .5}[row["position"]]
        result = triage.aggregate(rows, 6, 6)
        for group in result["matched"]:
            self.assertEqual(len(group["blocks"]), 6)
            self.assertAlmostEqual(group["median_change_percent"], 2.5)
            self.assertEqual(group["upper_bound"]["rank"], 6)
            self.assertAlmostEqual(group["upper_bound"]["upper_ratio"], 1.05)
            self.assertAlmostEqual(group["upper_bound"]["coverage"], 63/64)

    def test_reject_missing_duplicate_wrong_order_and_nonfinite(self):
        original = fixture()
        bad_cases = [original[:-1], original + original[:1]]
        for field, value in (("source", "0"), ("variant", "old_off"), ("command_seconds", float("nan")),
                             ("command_seconds", 0), ("command_seconds", -1)):
            rows = copy.deepcopy(original)
            rows[-1][field] = value
            bad_cases.append(rows)
        for rows in bad_cases:
            with self.assertRaises(ValueError):
                triage.aggregate(rows, 6, 6)

    def test_smoke_has_no_finite_bound(self):
        result = triage.aggregate(fixture(1, 1), 1, 1)
        self.assertTrue(all(g["upper_bound"]["upper_ratio"] is None for g in result["matched"]))


if __name__ == "__main__":
    unittest.main()
