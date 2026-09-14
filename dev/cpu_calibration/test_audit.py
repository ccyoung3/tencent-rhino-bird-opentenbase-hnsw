"""Offline mutation checks against an explicitly supplied, completed artifact.

No calculation, Docker, or subprocess calls. Mutated files exist only in private
TemporaryDirectory copies; the supplied experiment directory is read-only.
Usage: python test_audit.py path/to/construction-run -v
"""
import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

import audit

FIXTURE = Path(sys.argv.pop(1)).resolve() if len(sys.argv) > 1 and not sys.argv[1].startswith('-') else None


def sync_raw(record):
    record['raw_stdout'] = json.dumps(record['result'])


class AuditMutations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if FIXTURE is None:
            raise RuntimeError('supply a completed construction run directory')
        cls.original_bytes = (FIXTURE / 'summary.json').read_bytes()
        cls.summary = audit.strict_loads(cls.original_bytes.decode())

    @classmethod
    def tearDownClass(cls):
        if (FIXTURE / 'summary.json').read_bytes() != cls.original_bytes:
            raise AssertionError('self-test changed source artifact')

    def one(self):
        return copy.deepcopy(self.summary['records'][0])

    def assert_bad_record(self, record):
        with self.assertRaises(ValueError):
            audit.audit_record(record, 'formal', 1)

    def test_complete_archived_chain_and_independent_answer(self):
        result = audit.audit_run(FIXTURE)
        self.assertEqual(result['review_status'], 'verified')
        self.assertEqual(result['process_records'], 39)
        self.assertEqual(result['independent_expected_checksum'], 2589109860917)
        self.assertEqual(audit.checksum(50000000), 86303660579)
        self.assertLess(audit.checksum(4000000000), 2 ** 64)

    def test_self_consistent_wrong_reference_cannot_pass(self):
        record = self.one()
        record['result']['expected_checksum'] += 1
        for process in record['result']['processes']:
            process['checksum'] += 1
        sync_raw(record)
        self.assert_bad_record(record)
        record = self.one()
        record['result']['processes'][2]['iterations'] -= 1
        sync_raw(record)
        self.assert_bad_record(record)

    def test_missing_duplicate_reordered_or_failed_formal_rejected(self):
        mutations = [lambda s: s['records'].pop(),
                     lambda s: s['records'].__setitem__(11, copy.deepcopy(s['records'][10])),
                     lambda s: s['records'].reverse(),
                     lambda s: s['records'][4].__setitem__('status', 'failed')]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                summary = copy.deepcopy(self.summary)
                mutation(summary)
                summary['attempts'] = summary['warmups'] + summary['records']
                with self.assertRaises(ValueError):
                    audit.audit_records(summary)

    def test_participant_identity_types_and_scope_rejected(self):
        mutations = [lambda d: d['processes'][1].__setitem__('pid', d['processes'][0]['pid']),
                     lambda d: d['processes'][0].__setitem__('pid', True),
                     lambda d: d['processes'][1].__setitem__('participant', True),
                     lambda d: d['processes'][1].__setitem__('role', 'leader'),
                     lambda d: d.__setitem__('scope', 'HNSW_acceptance'),
                     lambda d: d['processes'][2].__setitem__('user_cpu_us', -1)]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                record = self.one()
                mutation(record['result'])
                sync_raw(record)
                self.assert_bad_record(record)

    def test_json_duplicate_nonfinite_and_raw_divergence_rejected(self):
        for text in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}', '{"x":1e999}'):
            with self.assertRaises(ValueError):
                audit.strict_loads(text)
        record = self.one()
        record['raw_stdout'] = record['raw_stdout'].replace('"verified":true', '"verified":false')
        self.assert_bad_record(record)

    def test_clock_exact_boundary_and_both_exceeding_directions(self):
        for drift in (100000000, -100000000, 100000001, -100000001):
            record = self.one()
            before, after = record['host_clock_before'], record['host_clock_after']
            mono = after['monotonic_ns'] - before['monotonic_ns']
            after['realtime_ns'] = before['realtime_ns'] + mono + drift
            record['host_wall_elapsed_ns'] = mono + drift
            record['host_wall_minus_monotonic_ns'] = drift
            if abs(drift) <= 100000000:
                audit.audit_record(record, 'formal', 1)
            else:
                self.assert_bad_record(record)

    def test_ac_resource_and_warmup_in_statistics_rejected(self):
        record = self.one()
        record['ac_after'] = "Now drawing from 'Battery Power'"
        self.assert_bad_record(record)
        record = self.one()
        record['resources_after'] = record['resources_after'].replace('FILE:cpu.stat', 'FILE:unknown')
        self.assert_bad_record(record)
        summary = copy.deepcopy(self.summary)
        summary['descriptive']['outer_wall_s']['values'].insert(0, summary['warmups'][0]['result']['elapsed_ns'] / 1e9)
        with self.assertRaises(ValueError):
            audit.audit_records(summary)

    def test_cpu_sum_keeps_outer_wall_separate_and_does_not_gate_variation(self):
        record = self.one()
        data = record['result']
        data['elapsed_ns'] *= 2
        for process in data['processes']:
            process['elapsed_ns'] *= 2
            process['user_cpu_us'] *= 2
            process['system_cpu_us'] *= 2
        sync_raw(record)
        result = audit.audit_record(record, 'formal', 1)
        self.assertEqual(result['outer_wall_s'], data['elapsed_ns'] / 1e9)
        self.assertEqual(result['sum_process_cpu_s'], sum(p['user_cpu_us'] + p['system_cpu_us'] for p in data['processes']) / 1e6)
        # A negative host-minus-guest is returned for explicit review, never hidden
        # by dropping a sample or used as an invented performance eligibility gate.
        self.assertLess(result['host_minus_guest_s'], 0)

    def test_source_binary_and_cleanup_mutations_rejected_on_private_copies(self):
        mutations = [lambda root: (root / 'source/method.md').write_text('changed method'),
                     lambda root: (root / 'binary/calibrate').write_bytes(b'changed binary'),
                     lambda root: (root / 'cleanup.json').write_text('{"status":"failed"}')]
        for mutation in mutations:
            with tempfile.TemporaryDirectory(prefix='cpu-audit-mutation-') as directory:
                root = Path(directory) / 'fixture'
                shutil.copytree(FIXTURE, root)
                mutation(root)
                with self.assertRaises((ValueError, KeyError)):
                    audit.audit_run(root)

    def test_missing_distance_call_inside_loop_rejected(self):
        text = (FIXTURE / 'binary/disassembly.txt').read_text()
        audit.disassembly_evidence(text)
        with self.assertRaises(ValueError):
            audit.disassembly_evidence(text.replace('<distance32>', '<removed_distance>'))


if __name__ == '__main__':
    unittest.main()
