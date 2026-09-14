"""Offline validation of native-randomness mechanism evidence; no database work."""
import copy
import json
import unittest

import audit_mechanism as audit
import mechanism_diagnostic as mechanism


def fixture():
    return [dict(schema=1, test_only=True, scope='scan_and_insert', mode='native',
        role='leader' if number == -1 else 'worker', worker_number=number,
        pid=100 + position, index_oid=123, callbacks_seen=10, successful_inserts=10,
        distance_calls=100 * (position + 1), elements_initialized=10,
        level_hist=[10] + [0] * 63, user_cpu_us=1000000 * (position + 1),
        system_cpu_us=100000 * (position + 1), elapsed_us=1000000 * (position + 2))
        for position, number in enumerate((-1, 0, 1))]


def log(records):
    return '\n'.join('NOTICE: HNSW_MECHANISM ' + json.dumps(record) for record in records) + '\n'


class MechanismTest(unittest.TestCase):
    def test_cpu_and_work_are_summed_but_elapsed_is_not(self):
        parsed = mechanism.parse_records(log(fixture()), 30, 123)
        self.assertEqual(parsed['scope'], 'scan_and_insert')
        self.assertEqual(parsed['totals']['callbacks_seen'], 30)
        self.assertEqual(parsed['totals']['successful_inserts'], 30)
        self.assertEqual(parsed['totals']['elements_initialized'], 30)
        self.assertEqual(parsed['totals']['distance_calls'], 600)
        self.assertEqual(parsed['totals']['cpu_seconds'], 6.6)
        self.assertEqual(parsed['totals']['level_hist'], [30] + [0] * 63)
        self.assertEqual(parsed['totals']['max_participant_elapsed_seconds'], 4.)
        self.assertNotIn('elapsed_us', parsed['totals'])
        self.assertNotIn('elapsed_seconds', parsed['totals'])
        self.assertNotIn('all_supported', parsed)

    def test_background_notices_do_not_become_counter_records(self):
        text = 'DEBUG: using 2 parallel workers\n' + log(fixture()) + 'NOTICE: unrelated notice\n'
        self.assertEqual(mechanism.parse_records(text, 30, 123)['records'], fixture())

    def test_missing_extra_and_duplicate_participants_are_rejected(self):
        records = fixture()
        for changed in (records[:-1], records + records[:1], records[:-1] + records[:1]):
            with self.subTest(records=changed), self.assertRaises(ValueError):
                mechanism.parse_records(log(changed), 30, 123)

    def test_duplicate_json_fields_and_nonfinite_values_are_rejected(self):
        text = log(fixture())
        duplicate = text.replace('"schema": 1', '"schema": 1, "schema": 1', 1)
        with self.assertRaises(ValueError):
            mechanism.parse_records(duplicate, 30, 123)
        for value in (float('nan'), float('inf'), -float('inf')):
            changed = fixture()
            changed[0]['distance_calls'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                mechanism.parse_records(log(changed), 30, 123)

    def test_schema_scope_and_native_mode_are_required(self):
        for key, value in (('schema', True), ('schema', 1.), ('schema', 2),
                           ('test_only', False), ('test_only', 1), ('scope', 'whole_build'),
                           ('mode', 'seed42')):
            changed = fixture()
            changed[0][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                mechanism.parse_records(log(changed), 30, 123)

    def test_process_role_and_actual_index_identity_are_required(self):
        for key, value in (('pid', 0), ('pid', True), ('pid', 100.), ('pid', 101),
                           ('worker_number', 0), ('worker_number', 2), ('worker_number', -1.),
                           ('index_oid', 0), ('index_oid', True), ('index_oid', 123.),
                           ('index_oid', 124), ('role', 'worker')):
            changed = fixture()
            changed[0][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                mechanism.parse_records(log(changed), 30, 123)
        with self.assertRaises(ValueError):
            mechanism.parse_records(log(fixture()), 30, 124)

    def test_counters_require_nonnegative_integers_and_positive_work(self):
        keys = ('callbacks_seen', 'successful_inserts', 'distance_calls', 'elements_initialized',
                'user_cpu_us', 'system_cpu_us', 'elapsed_us')
        for key in keys:
            for value in (-1, True, 1.5):
                changed = fixture()
                changed[0][key] = value
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    mechanism.parse_records(log(changed), 30, 123)
        for key in ('distance_calls', 'elapsed_us'):
            changed = fixture()
            changed[0][key] = 0
            with self.subTest(key=key), self.assertRaises(ValueError):
                mechanism.parse_records(log(changed), 30, 123)
        changed = fixture()
        changed[0]['user_cpu_us'] = changed[0]['system_cpu_us'] = 0
        with self.assertRaises(ValueError):
            mechanism.parse_records(log(changed), 30, 123)

    def test_histogram_and_all_fixture_rows_must_be_covered(self):
        for hist in ([10] + [0] * 62, [10] + [0] * 64, [9] + [0] * 63,
                     [10, -1] + [0] * 62, [10, True] + [0] * 62,
                     [10, .5] + [0] * 62):
            changed = fixture()
            changed[0]['level_hist'] = hist
            with self.subTest(hist=hist), self.assertRaises(ValueError):
                mechanism.parse_records(log(changed), 30, 123)
        for key in ('callbacks_seen', 'successful_inserts', 'elements_initialized'):
            changed = fixture()
            changed[0][key] -= 1
            with self.subTest(key=key), self.assertRaises(ValueError):
                mechanism.parse_records(log(changed), 30, 123)
        with self.assertRaises(ValueError):
            mechanism.parse_records(log(fixture()), 29, 123)

    def test_diagnostic_schedule_is_fixed_and_each_pair_is_mirrored(self):
        schedule = mechanism.schedule()
        self.assertEqual(schedule, mechanism.schedule())
        self.assertEqual([p['panel'] for p in schedule], [0, 1])
        self.assertEqual(schedule[0]['slots'], list(reversed(schedule[1]['slots'])))
        self.assertEqual([s['scene'] for s in schedule[0]['scenes']],
                         [s['scene'] for s in reversed(schedule[1]['scenes'])])
        formal = warmups = 0
        for panel in schedule:
            self.assertEqual({s['scene'] for s in panel['scenes']}, set(mechanism.SCENES))
            for scene in panel['scenes']:
                self.assertEqual(set(scene['warmup_order']), set(mechanism.CONDITIONS))
                self.assertEqual(scene['order'], scene['warmup_order'] + list(reversed(scene['warmup_order'])))
                formal += len(scene['order'])
                warmups += len(scene['warmup_order'])
        self.assertEqual((formal, warmups), (36, 18))
        # The independent smoke path uses only the first panel's nine warmups.
        smoke = copy.deepcopy(schedule[:1])
        for scene in smoke[0]['scenes']:
            scene['order'] = []
        self.assertEqual(sum(len(s['warmup_order']) for s in smoke[0]['scenes']), 9)
        self.assertFalse(any(s['order'] for s in smoke[0]['scenes']))

    def test_independent_counter_recomputation_and_schedule_match(self):
        text = log(fixture())
        self.assertEqual(audit.independent_records(text, 30, 123), mechanism.parse_records(text, 30, 123))
        self.assertEqual(audit.expected_schedule('diagnosis'), mechanism.schedule())
        smoke = mechanism.schedule()[:1]
        for scene in smoke[0]['scenes']:
            scene['order'] = []
        self.assertEqual(audit.expected_schedule('smoke'), smoke)

    def test_independent_parser_rejects_identity_work_and_nonfinite_corruption(self):
        for key, value in (('worker_number', 0), ('index_oid', 124), ('role', 'worker'),
                           ('callbacks_seen', 9), ('level_hist', [9] + [0] * 63),
                           ('distance_calls', float('nan')), ('user_cpu_us', True)):
            changed = fixture()
            changed[0][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                audit.independent_records(log(changed), 30, 123)
        with self.assertRaises(ValueError):
            audit.independent_records(log(fixture()).replace('"schema": 1', '"schema": 1, "schema": 1', 1), 30, 123)


if __name__ == '__main__':
    unittest.main()
