"""Offline protocol tests; subprocess is mocked except a parser-only C harness."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import run


class ProfileTests(unittest.TestCase):
    def test_selection_boundaries_and_construction_is_not_adaptive(self):
        self.assertEqual(run.select_iterations('short', 0.02120388), 50000000)
        self.assertEqual(run.select_iterations('short', 10), 20000000)
        self.assertEqual(run.select_iterations('short', 0.4), 25000000)
        self.assertEqual(run.select_iterations('construction'), 1500000000)
        for invalid in (0, -1, float('nan'), float('inf'), None):
            with self.assertRaises(ValueError):
                run.select_iterations('short', invalid)
        with self.assertRaises(ValueError):
            run.select_iterations('construction', 0.4)
        with self.assertRaises(ValueError):
            run.main('unknown')
        self.assertEqual(run.integer_reference(50000000), 86303660579)
        self.assertEqual(run.integer_reference(1500000000), 2589109860917)
        self.assertLess(run.integer_reference(4000000000), 2**64)
        for invalid in (0, -1, 4000000001, 1.5, True):
            with self.assertRaises(ValueError):
                run.integer_reference(invalid)

    def simulate(self, profile='construction', *, failure_probe=None, failure=None, drift_probe=None,
                 drift_ns=0, mutate_method=False, mutate_protocol=False):
        state = {'probes': [], 'clock_calls': 0, 'removed': False, 'timeouts': [], 'invalid': []}
        image_id = 'sha256:' + 'a' * 64
        container_id = 'b' * 64
        identity = {}
        with tempfile.TemporaryDirectory(prefix='cpu-calibration-profile-test-') as directory:
            root = Path(directory)
            for name in ('calibrate.c', 'Dockerfile', 'compile.sh', 'run.py', 'README.md'):
                shutil.copy2(run.ROOT / name, root / name)
            method = root / 'method.md'
            method.write_text('Frozen offline fixture method.\n')
            def response(stdout='', stderr='', returncode=0):
                return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)
            def fake_subprocess(args, **kwargs):
                if args[:3] == ['pmset', '-g', 'batt']:
                    return response("Now drawing from 'AC Power'\n")
                if args[:3] == ['docker', 'image', 'inspect']:
                    return response(json.dumps([{'Id': run.BASES.get(args[3], image_id), 'RootFS': {'Layers': ['locked-base']}}]))
                if args[:2] == ['docker', 'build']:
                    return response()
                if args[:2] == ['docker', 'create']:
                    state['container_sleep'] = args[-1]
                    identity.update(Id=container_id, Image=image_id, Name='/' + args[args.index('--name') + 1],
                                    Config={'Labels': {'cpu.calibration.nonce': args[args.index('--label') + 1].split('=', 1)[1]}}, Mounts=[])
                    return response(container_id)
                if args == ['docker', 'inspect', container_id]:
                    return response('[]', 'error: no such object: ' + container_id, 1) if state['removed'] else response(json.dumps([identity]))
                if args[:3] == ['docker', 'container', 'inspect']:
                    return response(json.dumps([identity]))
                if args[:2] == ['docker', 'start']:
                    return response()
                if args[:2] == ['docker', 'cp']:
                    destination = Path(args[-1])
                    destination.mkdir()
                    shutil.copy2(root / 'calibrate.c', destination / 'calibrate.c')
                    (destination / 'calibrate').write_bytes(b'offline fake binary')
                    return response()
                if args[:2] == ['docker', 'rm']:
                    self.assertEqual(args[-1], container_id)
                    state['removed'] = True
                    return response(container_id)
                if args[:4] == ['docker', 'exec', container_id, '/bin/sh']:
                    return response('offline resource snapshot\n')
                if args[:4] == ['docker', 'exec', container_id, '/opt/cpu-calibration/calibrate']:
                    argument = args[-1]
                    if argument in ('', '-1', '+1', 'abc', '4000000001'):
                        state['invalid'].append(argument)
                        return response(returncode=2)
                    iterations = int(argument)
                    index = len(state['probes'])
                    state['probes'].append(iterations)
                    state['timeouts'].append(kwargs['timeout'])
                    if mutate_protocol:
                        protocol_path = next((root / 'results').glob('*/protocol.json'))
                        if index == 0:
                            state['original_protocol_hash'] = hashlib.sha256(protocol_path.read_bytes()).hexdigest()
                        if index == 4:
                            # Change only protocol bytes; source/method and JSON content stay unchanged.
                            protocol_path.write_text(protocol_path.read_text() + '\n')
                            state['changed_protocol_hash'] = hashlib.sha256(protocol_path.read_bytes()).hexdigest()
                    if index == failure_probe:
                        if failure == 'interrupt':
                            raise KeyboardInterrupt('offline interruption')
                        if failure == 'timeout':
                            raise subprocess.TimeoutExpired(args, kwargs['timeout'], output='partial raw evidence')
                    checksum = {5000000: 8630366129, 50000000: 86303660579, 1500000000: 2589109860917}[iterations]
                    if index == failure_probe and failure == 'checksum':
                        checksum += 1
                    elapsed = 12000000000 if index == 4 else 6000000000
                    if index == 0:
                        elapsed = 21203880 if profile == 'short' else 1000000  # no warmup duration gate
                    if mutate_method and index == 12:
                        method.write_text('Changed during run.\n')
                    return response(json.dumps({'schema': 1, 'test_only': True, 'verified': True,
                        'scope': 'fixed_arithmetic_three_processes', 'dimensions': 32, 'inputs': 1024,
                        'iterations_per_process': iterations, 'expected_checksum': checksum, 'elapsed_ns': elapsed,
                        'affinity': list(range(10)), 'processes': [
                            {'participant': i, 'role': 'leader' if i == 0 else 'worker', 'pid': 100 + i,
                             'iterations': iterations, 'checksum': checksum, 'user_cpu_us': 6000000,
                             'system_cpu_us': 0, 'elapsed_ns': elapsed} for i in range(3)]}))
                raise AssertionError('unexpected command: ' + repr(args))

            def fake_clock():
                call = state['clock_calls']
                state['clock_calls'] += 1
                instant = call * 6000000000
                delta = drift_ns if call % 2 and call // 2 == drift_probe else 0
                return {'realtime_ns': instant + delta, 'monotonic_ns': instant, 'sampling_span_ns': 0}

            with patch.object(run, 'ROOT', root), patch.object(run.subprocess, 'run', side_effect=fake_subprocess), patch.object(run, 'host_clock', side_effect=fake_clock):
                with contextlib.redirect_stdout(io.StringIO()):
                    status = run.main(profile, method_path=method)
            directories = list((root / 'results').iterdir())
            self.assertEqual(len(directories), 1)
            files = {p.name: json.loads(p.read_text()) for p in directories[0].glob('*.json')}
            return status, state, files

    def test_construction_keeps_warmup_and_all_twelve_including_extreme_value(self):
        status, state, files = self.simulate()
        self.assertEqual(status, 0)
        self.assertEqual(state['probes'], [1500000000] * 13)
        self.assertEqual(state['invalid'], ['', '-1', '+1', 'abc', '4000000001'])
        self.assertEqual(state['container_sleep'], '300')
        self.assertEqual(state['timeouts'], [30] * 13)
        summary = files['summary.json']
        self.assertEqual(len(summary['warmups']), 1)
        self.assertEqual(len(summary['records']), 12)
        self.assertEqual(len(summary['attempts']), 13)
        self.assertNotIn('sizing', summary)
        self.assertEqual(summary['descriptive']['outer_wall_s']['values'][3], 12)
        self.assertEqual(summary['descriptive']['outer_wall_s']['min'], 6)  # warmup excluded
        self.assertTrue(summary['source_hashes_unchanged'])
        self.assertEqual(files['protocol.json']['expected_checksum_per_process'], 2589109860917)
        self.assertTrue(state['removed'])

    def test_short_default_selection_and_no_new_clock_gate(self):
        status, state, files = self.simulate('short', drift_probe=0, drift_ns=100000001)
        self.assertEqual(status, 0)
        self.assertEqual(state['probes'], [5000000] + [50000000] * 12)
        self.assertEqual(state['invalid'], [])
        self.assertEqual(state['timeouts'], [15] * 13)
        self.assertEqual(state['container_sleep'], '180')
        self.assertEqual(files['summary.json']['warmups'], [])
        self.assertIsNone(files['protocol.json']['max_host_realtime_monotonic_difference_ns'])

    def test_failure_stops_without_discarding_or_replacing_attempted_probes(self):
        cases = [(0, 'checksum'), (3, 'checksum'), (3, 'interrupt'), (3, 'timeout')]
        for index, failure in cases:
            with self.subTest(index=index, failure=failure):
                status, state, files = self.simulate(failure_probe=index, failure=failure)
                self.assertEqual(status, 1)
                self.assertEqual(len(state['probes']), index + 1)
                summary = files['summary.json']
                self.assertEqual(len(summary['attempts']), index + 1)
                self.assertEqual(summary['attempts'][-1]['status'], 'failed')
                self.assertEqual(len(summary['records']), index)
                self.assertNotIn('descriptive', summary)
                self.assertEqual(summary['cleanup']['status'], 'verified')
                self.assertTrue(state['removed'])
                if failure == 'interrupt':
                    self.assertIn('KeyboardInterrupt', summary['error'])
                if failure == 'timeout':
                    self.assertTrue(any(v.get('stdout') == 'partial raw evidence' for k, v in files.items() if k.startswith('command-')))

    def test_clock_threshold_is_absolute_and_source_changes_invalidate(self):
        for drift, expected_status in ((100000000, 0), (100000001, 1), (-100000001, 1)):
            status, state, files = self.simulate(drift_probe=2, drift_ns=drift)
            self.assertEqual(status, expected_status)
            self.assertEqual(len(state['probes']), 3 if expected_status else 13)
            if expected_status:
                self.assertEqual(files['summary.json']['records'][-1]['host_wall_minus_monotonic_ns'], drift)
        status, state, files = self.simulate(mutate_method=True)
        self.assertEqual(status, 1)
        self.assertEqual(len(state['probes']), 13)
        self.assertFalse(files['summary.json']['source_hashes_unchanged'])

    def test_protocol_only_tampering_fails_with_existing_frozen_digest_check(self):
        status, state, files = self.simulate(mutate_protocol=True)
        self.assertNotEqual(state['original_protocol_hash'], state['changed_protocol_hash'])
        summary = files['summary.json']
        self.assertEqual(status, 1)
        self.assertEqual(summary['status'], 'failed')
        self.assertEqual(summary['protocol_sha256'], state['original_protocol_hash'])
        self.assertEqual(summary['input_hashes_at_finish'], summary['sources'])
        self.assertIn('frozen protocol changed', summary['source_verification_error'])
        self.assertEqual(len(summary['attempts']), 13)
        self.assertEqual(len(summary['records']), 12)
        self.assertEqual(summary['cleanup']['status'], 'verified')
        self.assertTrue(state['removed'])


class CParserTests(unittest.TestCase):
    def test_actual_parser_boundaries_without_calculate_or_fork(self):
        text = (run.ROOT / 'calibrate.c').read_text()
        begin = text.index('static int parse_iterations(')
        end = text.index('\nint main(', begin)
        parser = text[begin:end]
        harness = '#include <stdint.h>\n#include <inttypes.h>\n#include <stdlib.h>\n#include <errno.h>\n#include <stdio.h>\n' + parser
        harness += '\nint main(int argc, char **argv) { uint64_t n; if (argc != 2 || !parse_iterations(argv[1], &n)) return 2; printf("%" PRIu64 "\\n", n); return 0; }\n'
        with tempfile.TemporaryDirectory(prefix='cpu-calibration-parser-test-') as directory:
            path = Path(directory)
            (path / 'parser.c').write_text(harness)
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', str(path / 'parser.c'), '-o', str(path / 'parser')], check=True, capture_output=True, text=True)
            for argument in ('1', '1500000000', '4000000000'):
                result = subprocess.run([str(path / 'parser'), argument], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stdout.strip(), argument)
            for argument in ('', '-1', '-18446744073709551615', '+1', 'abc', '0', '4000000001', '18446744073709551616', ' 1', '1 '):
                result = subprocess.run([str(path / 'parser'), argument], capture_output=True, text=True)
                self.assertEqual(result.returncode, 2, argument)
                self.assertEqual(result.stdout, '')


if __name__ == '__main__':
    unittest.main()
