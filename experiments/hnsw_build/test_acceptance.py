import copy
import itertools
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import acceptance as a
import acceptance_stack as stack


def fixture(aa):
    rows = []
    for step in a.schedule(8 if aa else 24, aa):
        for scene in step['scenes']:
            for label in scene['order']:
                rows.append(dict(panel=step['panel'], workers=scene['workers'], spill=scene['spill'],
                    condition=label, command_seconds=10., observer={'observation': {'phases': ['loading tuples'], 'samples': 2}}))
    return rows


class AcceptanceTest(unittest.TestCase):
    def test_host_suspension_or_power_change_fails(self):
        ac, battery = {'power_source': 'AC'}, {'power_source': 'Battery'}
        a.validate_host(ac, ac, 10., 10.01, True)
        a.validate_host(battery, battery, 10., 10.01, False)
        for before, after, mono, civil in ((ac, ac, 10., 960.), (ac, battery, 10., 10.),
                                           (battery, ac, 10., 10.), (ac, ac, 0., 0.),
                                           (ac, ac, 10., float('nan'))):
            with self.assertRaises(RuntimeError):
                a.validate_host(before, after, mono, civil, True)

    def test_power_preflight(self):
        for output, expected in (("Now drawing from 'AC Power'", 'AC'), ("Now drawing from 'Battery Power'", 'Battery')):
            with patch.object(stack.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout=output)):
                self.assertEqual(stack.power_source(), expected)
        with patch.object(stack.subprocess, 'run', return_value=SimpleNamespace(returncode=1, stdout='')):
            with self.assertRaises(RuntimeError):
                stack.power_source()

    def test_help(self):
        p = subprocess.run([sys.executable, a.__file__, '--help'], capture_output=True)
        self.assertEqual(p.returncode, 0, p.stderr.decode())

    def test_formal_positions_and_predecessors_balanced(self):
        steps = a.schedule(24, False)
        self.assertEqual(steps, a.schedule(24, False))
        for w, s in a.SCENES:
            orders = [scene['order'] for step in steps for scene in step['scenes']
                      if (scene['workers'], scene['spill']) == (w, s)]
            self.assertEqual(set(orders), set(itertools.permutations(a.CONDITIONS)))
            self.assertNotEqual(orders, list(itertools.permutations(a.CONDITIONS)))
            for label in a.CONDITIONS:
                for position in range(4):
                    self.assertEqual(sum(order[position] == label for order in orders), 6)
                for other in set(a.CONDITIONS) - {label}:
                    self.assertEqual(sum(order[p:p+2] == (label, other) for order in orders for p in range(3)), 6)
        self.assertEqual(len({tuple((s['workers'], s['spill']) for s in p['scenes']) for p in steps}), 24)

    def test_aa_orders_balanced(self):
        for w, s in a.SCENES:
            orders = [scene['order'] for step in a.schedule(8, True) for scene in step['scenes']
                      if (scene['workers'], scene['spill']) == (w, s)]
            self.assertEqual(orders.count(('aa_a', 'aa_b')), 4)
            self.assertEqual(orders.count(('aa_b', 'aa_a')), 4)

    def test_exact_upper_bound_and_family_coverage(self):
        bound = a.upper(list(range(1, 25)), 1-.05/12)
        self.assertGreaterEqual(bound['coverage'], 1-.05/12)
        preceding = sum(math.comb(24, i) for i in range(bound['rank']-1)) / 2**24
        self.assertLess(preceding, 1-.05/12)
        self.assertEqual(bound['ratio'], bound['rank'])
        self.assertIsNone(a.upper([1], .95)['ratio'])

    def test_equal_data_passes_and_regression_fails(self):
        for aa in (True, False):
            rows = fixture(aa)
            self.assertTrue(a.summarize(rows, 8 if aa else 24, aa)['all_supported'])
            for row in rows:
                if row['condition'] == ('aa_b' if aa else 'off'):
                    row['command_seconds'] *= 1.06
            self.assertFalse(a.summarize(rows, 8 if aa else 24, aa)['all_supported'])

    def test_invalid_data_rejected(self):
        rows = fixture(False)
        cases = [rows[:-1], rows + rows[:1]]
        for value in (0, -1, float('nan'), float('inf')):
            changed = copy.deepcopy(rows)
            changed[0]['command_seconds'] = value
            cases.append(changed)
        for changed in cases:
            with self.assertRaises(ValueError):
                a.summarize(changed, 24, False)

    def test_missing_observer_progress_is_not_pass(self):
        rows = fixture(False)
        next(r for r in rows if r['condition'] == 'observed')['observer'] = {}
        self.assertFalse(a.summarize(rows, 24, False)['all_supported'])

    def test_formal_uses_original_baseline_not_off_as_reference(self):
        rows = fixture(False)
        for row in rows:
            if row['condition'] != 'baseline':
                row['command_seconds'] = 10.6
        result = a.summarize(rows, 24, False)
        self.assertEqual(len(result['groups']), 12)
        self.assertTrue(all(g['reference'] == 'baseline' and g['verdict'] == 'not_established' for g in result['groups']))

    def test_exact_five_percent_is_not_strictly_below_threshold(self):
        rows = fixture(False)
        for row in rows:
            if row['condition'] != 'baseline':
                row['command_seconds'] = 10.5
        self.assertFalse(a.summarize(rows, 24, False)['all_supported'])

    def test_aa_suspicious_speedup_is_also_unstable(self):
        rows = fixture(True)
        for row in rows:
            if row['condition'] == 'aa_b':
                row['command_seconds'] = 9.4
        self.assertFalse(a.summarize(rows, 8, True)['all_supported'])

    def test_aa_noise_fails_without_deleting_outlier(self):
        rows = fixture(True)
        next(r for r in rows if r['condition'] == 'aa_b')['command_seconds'] = 13.
        result = a.summarize(rows, 8, True)
        self.assertFalse(result['all_supported'])
        self.assertTrue(any(len(g['ratios']) == 8 and max(g['ratios']) == 1.3 for g in result['groups']))

    def test_occupied_port_refuses_before_docker(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(stack.socket, 'create_connection') as connect, patch.object(stack, 'docker') as docker:
            with self.assertRaisesRegex(RuntimeError, 'occupied'):
                with stack.panel(Path(folder) / 'panel', {'a': 'image', 'b': 'image'}, large_rows=10000, small_rows=10000):
                    self.fail('must not start')
            docker.assert_not_called()
            connect.assert_called_once()

    def test_cleanup_preserves_wrong_owner(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(stack, 'docker', return_value='[{"Id":"id","Config":{"Labels":{"hnsw.acceptance.run":"foreign"}}}]') as docker:
            replica = stack.Replica(Path(folder), 'image', 55432, 'own', '0-3')
            replica.container_id = 'id'
            self.assertTrue(replica.close())
            self.assertEqual(docker.call_count, 1)


if __name__ == '__main__':
    unittest.main()
