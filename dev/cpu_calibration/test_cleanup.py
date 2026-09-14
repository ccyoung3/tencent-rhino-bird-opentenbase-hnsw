"""Offline ownership-recovery checks. No Docker invocation or CPU workload."""
import copy
import contextlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import run


class CleanupRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.name = 'cpu-calibration-testnonce'
        self.nonce = 'testnonce'
        self.image = 'sha256:' + 'a' * 64
        self.identity = {'Id': 'b' * 64, 'Name': '/' + self.name, 'Image': self.image,
                         'Config': {'Labels': {'cpu.calibration.nonce': self.nonce}}, 'Mounts': []}

    def recover(self, command):
        # Any accidental use of a real subprocess in these tests is a failure.
        with patch.object(run.subprocess, 'run', side_effect=AssertionError('offline test')):
            return run.recover_owned_container(command, self.name, self.nonce, self.image)

    def test_create_timeout_but_daemon_created_owned_object(self):
        # No create stdout/ID is available; only the pre-recorded name/nonce/image.
        command = Mock(return_value=SimpleNamespace(returncode=0, stdout=json.dumps([self.identity]), stderr=''))
        self.assertEqual(self.recover(command), self.identity)
        command.assert_called_once_with(['docker', 'container', 'inspect', self.name], check=False, cleanup_call=True)
        summary, mutations = self.simulate_create_timeout('owned')
        self.assertEqual(summary['status'], 'failed')  # original timeout is preserved
        self.assertEqual(summary['cleanup']['status'], 'verified')
        self.assertEqual(mutations, [['docker', 'rm', '-f', '-v', self.identity['Id']]])

    def test_non_owned_or_ambiguous_object_is_not_recovered(self):
        variations = []
        for field, value in [('Name', '/unrelated'), ('Image', 'sha256:' + 'c' * 64), ('Id', 'invalid')]:
            identity = copy.deepcopy(self.identity)
            identity[field] = value
            variations.append([identity])
        identity = copy.deepcopy(self.identity)
        identity['Config']['Labels']['cpu.calibration.nonce'] = 'someone-else'
        variations.extend([[identity], [], [self.identity, self.identity]])
        for objects in variations:
            with self.subTest(objects=objects):
                command = Mock(return_value=SimpleNamespace(returncode=0, stdout=json.dumps(objects), stderr=''))
                with self.assertRaises(RuntimeError):
                    self.recover(command)
                self.assertEqual(command.call_count, 1)  # inspect only; no mutation
        summary, mutations = self.simulate_create_timeout('non_owned')
        self.assertEqual(summary['cleanup']['status'], 'failed')
        self.assertIn('ownership mismatch', summary['cleanup']['error'])
        self.assertEqual(mutations, [])

    def test_explicit_absence_is_distinguished_from_daemon_error(self):
        for message in ('Error: No such container: ' + self.name, 'error: no such object: ' + self.name):
            command = Mock(return_value=SimpleNamespace(returncode=1, stdout='[]', stderr=message))
            self.assertIsNone(self.recover(command))
            self.assertEqual(command.call_count, 1)
        command = Mock(return_value=SimpleNamespace(returncode=1, stdout='', stderr='Cannot connect to Docker daemon'))
        with self.assertRaises(RuntimeError):
            self.recover(command)
        self.assertEqual(command.call_count, 1)
        summary, mutations = self.simulate_create_timeout('absent')
        self.assertEqual(summary['cleanup']['status'], 'verified_absent')
        self.assertEqual(mutations, [])

    def simulate_create_timeout(self, mode):
        """Exercise main's actual finally branch when create never returns ID."""
        mutations = []
        created = {}
        def fake_subprocess(args, **kwargs):
            result = lambda stdout='', stderr='', returncode=0: SimpleNamespace(
                stdout=stdout, stderr=stderr, returncode=returncode)
            if args[:3] == ['pmset', '-g', 'batt']:
                return result("Now drawing from 'AC Power'\n")
            if args[:3] == ['docker', 'image', 'inspect']:
                image_id = run.BASES.get(args[3], self.image)
                return result(json.dumps([{'Id': image_id, 'RootFS': {'Layers': ['locked-base']}}]))
            if args[:2] == ['docker', 'build']:
                return result()
            if args[:2] == ['docker', 'create']:
                created['name'] = args[args.index('--name') + 1]
                created['nonce'] = args[args.index('--label') + 1].split('=', 1)[1]
                raise subprocess.TimeoutExpired(args, 20)
            if args[:3] == ['docker', 'container', 'inspect']:
                self.assertEqual(args[3], created['name'])
                if mode == 'absent':
                    return result('[]', 'error: no such container: ' + created['name'], 1)
                identity = copy.deepcopy(self.identity)
                identity['Name'] = '/' + created['name']
                identity['Config']['Labels']['cpu.calibration.nonce'] = created['nonce'] if mode == 'owned' else 'other-task'
                return result(json.dumps([identity]))
            if args[:2] == ['docker', 'rm']:
                self.assertEqual(mode, 'owned')
                mutations.append(args)
                return result(self.identity['Id'])
            if args == ['docker', 'inspect', self.identity['Id']]:
                return result('[]', 'error: no such object: ' + self.identity['Id'], 1)
            raise AssertionError('unexpected command (no workload permitted): ' + repr(args))

        with tempfile.TemporaryDirectory(prefix='cpu-calibration-cleanup-test-') as directory:
            test_root = Path(directory)
            for name in ('calibrate.c', 'Dockerfile', 'compile.sh', 'run.py', 'README.md'):
                shutil.copy2(run.ROOT / name, test_root / name)
            with patch.object(run, 'ROOT', test_root), patch.object(run.subprocess, 'run', side_effect=fake_subprocess):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(run.main(), 1)
            summaries = list((test_root / 'results').glob('*/summary.json'))
            self.assertEqual(len(summaries), 1)
            summary = json.loads(summaries[0].read_text())
            self.assertIn('TimeoutExpired', summary['error'])
            self.assertEqual(summary['records'], [])
            return summary, mutations


if __name__ == '__main__':
    unittest.main()
