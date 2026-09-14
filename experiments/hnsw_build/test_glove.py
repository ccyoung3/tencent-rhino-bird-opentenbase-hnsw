"""Pure logic plus optional HDF5 validation; no database started by unit tests."""
import json
import signal
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import glove
import glove_cases
import glove_run
import glove_report
import run

try:
    import h5py
    import numpy as np
except ImportError:
    h5py = None


class GloveLogicTest(unittest.TestCase):
    def test_controller_interrupt_signals_python_only(self):
        child = Mock(pid=12345)
        child.wait.side_effect = [KeyboardInterrupt(), 0]
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(run, "RESULTS_ROOT", Path(directory)), \
                 patch("sys.argv", ["glove_cases.py", "--low-memory", "64MB", "--high-memory", "256MB"]), \
                 patch.object(glove_cases.subprocess, "Popen", return_value=child), \
                 patch.object(glove_cases.os, "kill") as kill, \
                 patch.object(glove_cases.os, "killpg") as killpg, \
                 patch("builtins.print"):
                self.assertEqual(glove_cases.main(), 1)
            kill.assert_called_once_with(12345, signal.SIGINT)
            killpg.assert_not_called()
            self.assertEqual(child.wait.call_count, 2)
            protocol = json.loads(next(Path(directory).glob("*/protocol.json")).read_text())
            self.assertEqual(protocol["status"], "failed")
            self.assertIn("KeyboardInterrupt", protocol["error"])

    def test_split_is_deterministic_disjoint_and_complete(self):
        result = glove.query_split(1200)
        self.assertEqual(result, glove.query_split(1200))
        self.assertEqual(len(result["tuning"]), 200)
        self.assertEqual(len(result["validation"]), 1000)
        self.assertFalse(set(result["tuning"]) & set(result["validation"]))

    def test_split_rejects_over_budget(self):
        with self.assertRaises(ValueError):
            glove.query_split(100)

    def test_selection_and_no_selection(self):
        rows = [{"ef_search": 40, "mean_recall": .90}, {"ef_search": 100, "mean_recall": .97}]
        self.assertEqual(glove.select_ef(rows, .95), 100)
        self.assertIsNone(glove.select_ef(rows, .99))

    def test_percentile_and_unique_queries(self):
        rows = [{"query_id": 1, "ef_search": 10, "execution_ms": x, "recall_at_k": .8} for x in (1, 2, 3)]
        result = glove.aggregate(rows, .95)[0]
        self.assertEqual(result["unique_queries"], 1)
        self.assertEqual(result["measurements"], 3)
        self.assertAlmostEqual(result["p95_execution_ms"], 2.9)
        self.assertTrue(result["below_target"])

    def test_exact_identity_and_boundary_ties(self):
        self.assertTrue(glove.check_exact([1, 2], [.1, .2], [(1, .1), (2, .2)])["strict_ids_match"])
        self.assertFalse(glove.check_exact([1, 2], [.1, .2], [(1, .1), (3, .2)])["strict_ids_match"])
        with self.assertRaises(RuntimeError):
            glove.check_exact([1, 2], [.1, .2], [(1, .1), (3, .3)])
        with self.assertRaises(RuntimeError):
            glove.check_exact([1, 2], [.1, .2], [(1, .4), (2, .2)])

    def test_fixed_cosine_build_and_old_default(self):
        args = glove_run.parse_args(["--label", "glove-unit"])
        self.assertIn("vector_cosine_ops", run.build_sql(args))
        del args.operator_class
        self.assertIn("vector_l2_ops", run.build_sql(args))
        args.operator_class = "bad; DROP"
        with self.assertRaises(ValueError):
            run.build_sql(args)

    def test_formal_comparison_needs_repetitions_and_rejects_duplicates(self):
        with self.assertRaises(ValueError):
            glove_report.load_runs(["/tmp/same", "/tmp/same"])
        with self.assertRaises(ValueError):
            glove_report.summarize([])

    def test_summary_rejects_failed_or_mixed_protocol(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            for i in range(2):
                folder = base / str(i)
                folder.mkdir()
                (folder / "summary.json").write_text(json.dumps({
                    "status": "failed" if i == 0 else "passed", "cleanup": {"status": "complete"},
                    "internal_timing": {"status": "complete"}}))
            with self.assertRaises(ValueError):
                glove_report.load_runs([base / "0"])
            with patch.object(glove_report, "signature", side_effect=[1, 2]):
                with self.assertRaises(ValueError):
                    # Two distinct directories with passing data, inconsistent signatures.
                    (base / "0/summary.json").write_text((base / "1/summary.json").read_text())
                    glove_report.load_runs([base / "0", base / "1"])


@unittest.skipIf(h5py is None, "optional GloVe dependencies not installed")
class GloveInputTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "fixture.h5"
        with h5py.File(self.path, "w") as data:
            data.attrs["distance"] = "angular"
            data["train"] = np.array([[1, 0], [0, 1], [-1, 0]], dtype="float32")
            data["test"] = np.array([[1, 0], [0, 1]], dtype="float32")
            data["neighbors"] = np.array([[0, 1], [1, 0]], dtype="int32")
            data["distances"] = np.array([[0, 1], [0, 1]], dtype="float32")

    def test_valid_input_and_hash_pin(self):
        metadata = glove.inspect_dataset(self.path, expected_sha256=None)
        self.assertEqual(metadata["shapes"]["train"], [3, 2])
        with self.assertRaises(ValueError):
            glove.inspect_dataset(self.path)

    def test_reject_zero_nan_invalid_ids_and_order(self):
        for dataset, key, value in [("train", (0, 0), 0), ("train", (0, 0), float("nan")),
                                    ("neighbors", (0, 0), -1), ("neighbors", (0, 0), 1),
                                    ("distances", (0, 0), 1.5)]:
            with self.subTest(dataset=dataset, value=value):
                with h5py.File(self.path, "r+") as data:
                    old = data[dataset][key]
                    data[dataset][key] = value
                with self.assertRaises(ValueError):
                    glove.inspect_dataset(self.path, expected_sha256=None)
                with h5py.File(self.path, "r+") as data:
                    data[dataset][key] = old

    def test_binary_copy_row_layout(self):
        encoded = glove.binary_rows(np.array([[1, -2]], dtype="float32"), 7)
        self.assertEqual(struct.unpack("!hiqihh", encoded[:22]), (2, 8, 7, 12, 2, 0))
        self.assertEqual(struct.unpack("!ff", encoded[22:]), (1, -2))

    def test_subset_ground_truth_is_recomputed(self):
        plan = {"Plan": {"Node Type": "Seq Scan"}, "Execution Time": 1.0}
        # Fixture's full GT includes ID 3 outside the two-row subset; must not be used.
        with h5py.File(self.path, "r+") as data:
            data["neighbors"][0, 0] = 2
        with patch.object(glove, "_search", return_value=([(1, 0.0)], plan)) as search:
            result = glove.evaluate(None, self.path, 2, [0], [10], 1, 1, .95,
                                    Path(self.directory.name) / "subset", split_name="tuning")
        self.assertFalse(result["full_train"])
        self.assertEqual(result["by_ef_search"][0]["mean_recall"], 1)
        self.assertIsNone(search.call_args_list[0].kwargs.get("ef"))

    def test_failed_measurement_preserves_partial_evidence(self):
        plan = {"Plan": {"Node Type": "Seq Scan"}, "Execution Time": 1.0}
        output = Path(self.directory.name) / "partial"
        with patch.object(glove, "_search", side_effect=[([(1, 0)], plan), ([(1, 0)], plan), RuntimeError("cancelled")]):
            with self.assertRaises(RuntimeError):
                glove.evaluate(None, self.path, 2, [0], [10], 1, 2, .95, output, split_name="tuning")
        self.assertEqual(len((output / "measurements.jsonl").read_text().splitlines()), 1)
        self.assertFalse((output / "summary.json").exists())


if __name__ == "__main__":
    unittest.main()
