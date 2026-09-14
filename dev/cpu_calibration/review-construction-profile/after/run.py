#!/usr/bin/env python3
"""One bounded exploratory CPU calibration; never an overhead acceptance test."""
import argparse
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parent
BASES = {
    'opentenbase-pg18-pgvector:timing-v1-test-arm64': 'sha256:583632f8a2ba73f694ffed52fcd8e9a9a385da94c2602bfd65de1086a92148c6',
    'opentenbase-pg18-pgvector:timing-v1-arm64': 'sha256:af1ee2f012f452048c080b591c5456e8a5a83fea77fb4df6e53f4d28ba395fc7',
}
RESOURCE_SCRIPT = 'for f in cpu.stat cpu.max cpuset.cpus.effective memory.current memory.events io.stat; do printf "FILE:%s\\n" "$f"; cat "/sys/fs/cgroup/$f" || exit; done; printf "FILE:cpu.pressure\\n"; if [ -r /sys/fs/cgroup/cpu.pressure ]; then cat /sys/fs/cgroup/cpu.pressure; else printf "unavailable\\n"; fi'
PROFILES = {
    'short': {'budget_s': 180, 'probe_timeout_s': 15, 'sizing_probes': 1, 'warmup_probes': 0,
              'iterations_per_process': None, 'max_clock_drift_ns': None},
    'construction': {'budget_s': 300, 'probe_timeout_s': 30, 'sizing_probes': 0, 'warmup_probes': 1,
                     'iterations_per_process': 1500000000, 'max_clock_drift_ns': 100000000},
}


def select_iterations(profile, sizing_elapsed_s=None):
    config = PROFILES[profile]
    if profile == 'construction':
        if sizing_elapsed_s is not None:
            raise ValueError('construction profile does not perform sizing')
        return config['iterations_per_process']
    if sizing_elapsed_s is None or not math.isfinite(sizing_elapsed_s) or sizing_elapsed_s <= 0:
        raise ValueError('short profile needs a positive finite sizing duration')
    return max(20, min(50, math.floor((5 * 2 / sizing_elapsed_s) + 0.5))) * 1000000


def host_clock():
    before = time.monotonic_ns()
    realtime = time.time_ns()
    after = time.monotonic_ns()
    return {'realtime_ns': realtime, 'monotonic_ns': (before + after) // 2,
            'sampling_span_ns': after - before}


def clock_delta(before, after):
    wall = after['realtime_ns'] - before['realtime_ns']
    monotonic = after['monotonic_ns'] - before['monotonic_ns']
    return {'host_wall_elapsed_ns': wall, 'host_monotonic_elapsed_ns': monotonic,
            'host_wall_minus_monotonic_ns': wall - monotonic}


def integer_reference(iterations):
    if type(iterations) is not int or not 1 <= iterations <= 4000000000:
        raise ValueError('iterations must be an integer in [1, 4000000000]')
    period = []
    for i in range(1024):
        index = (i * 17) & 1023
        period.append(sum((((index * 11 + j * 7 + index // 13) % 17 - 8)
                           - ((index * 3 + j * 5 + index // 7) % 19 - 9)) ** 2 for j in range(32)))
    return sum(period) * (iterations // 1024) + sum(period[:iterations % 1024])


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def recover_owned_container(command, name, nonce, image_id):
    """Recover only this attempt's identity, including after create timed out.

    A daemon-side create can succeed before the client returns its ID. Never
    infer ownership from the name alone or treat arbitrary errors as absence.
    """
    result = command(['docker', 'container', 'inspect', name], check=False, cleanup_call=True)
    if result.returncode:
        if 'no such container' in result.stderr.lower() or 'no such object' in result.stderr.lower():
            return None
        raise RuntimeError('cannot establish whether owned container exists')
    objects = json.loads(result.stdout)
    if not isinstance(objects, list) or len(objects) != 1:
        raise RuntimeError('ambiguous container identity; leaving object untouched')
    identity = objects[0]
    if (identity.get('Name') != '/' + name
            or identity.get('Image') != image_id
            or identity.get('Config', {}).get('Labels', {}).get('cpu.calibration.nonce') != nonce
            or not re.fullmatch('[0-9a-f]{64}', identity.get('Id', ''))):
        raise RuntimeError('container ownership mismatch; leaving object untouched')
    return identity


def main(profile='short', method_path=None):
    if profile not in PROFILES:
        raise ValueError('unknown profile: ' + str(profile))
    config = PROFILES[profile]
    if method_path is None:
        method_path = (ROOT.parents[1] / 'docs/2026-09-13-construction-duration-calibration.md'
                       if profile == 'construction' else ROOT / 'README.md')
    inputs = {name: ROOT / name for name in ('calibrate.c', 'Dockerfile', 'compile.sh', 'run.py')}
    inputs['method.md'] = Path(method_path)
    nonce = uuid.uuid4().hex[:12]
    run = ROOT / 'results' / (dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + nonce)
    run.mkdir(parents=True, exist_ok=False)
    source = run / 'source'
    source.mkdir()
    for name, input_path in inputs.items():
        shutil.copy2(input_path, source / name)
    source_hashes = {p.name: sha(p) for p in source.iterdir()}
    deadline = time.monotonic() + config['budget_s']
    command_number = 0
    container = None
    container_name = 'cpu-calibration-' + nonce
    creation_attempted = False
    image_id = None
    protocol_sha256 = None
    cleanup = {'status': 'not_created'}
    summary = {'schema': 2, 'test_only': True, 'profile': profile, 'status': 'running', 'started_at_utc': stamp(),
               'nonce': nonce, 'sources': source_hashes, 'records': [], 'attempts': [], 'warmups': [],
               'run_directory': str(run)}
    write(run / 'summary.json', summary)

    def command(args, *, timeout=20, check=True, cleanup_call=False):
        nonlocal command_number
        command_number += 1
        record = {'argv': args, 'started_at_utc': stamp()}
        started = time.monotonic()
        try:
            remaining = 20 if cleanup_call else deadline - started
            if remaining <= 0:
                raise TimeoutError(f"fixed {config['budget_s']}-second budget exhausted")
            result = subprocess.run(args, capture_output=True, text=True, timeout=min(timeout, remaining))
            record.update(returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)
        except (Exception, KeyboardInterrupt) as error:
            record.update(error=repr(error))
            for field in ('stdout', 'stderr'):
                value = getattr(error, field, None)
                if value is not None:
                    record[field] = value.decode(errors='replace') if isinstance(value, bytes) else value
            raise
        finally:
            record.update(finished_at_utc=stamp(), host_elapsed_s=time.monotonic() - started)
            write(run / f'command-{command_number:03d}.json', record)
        if check and result.returncode:
            raise RuntimeError(f'command {command_number} failed: {result.returncode}')
        return result

    def ac():
        result = command(['pmset', '-g', 'batt'], timeout=5)
        if "Now drawing from 'AC Power'" not in result.stdout:
            raise RuntimeError('AC power was not established; stopping without replacement')
        return result.stdout

    def resources():
        return command(['docker', 'exec', container, '/bin/sh', '-c', RESOURCE_SCRIPT]).stdout

    def probe(kind, number, iterations):
        record = {'kind': kind, 'number': number, 'iterations_per_process': iterations, 'started_at_utc': stamp()}
        path = run / f'{kind}-{number:02d}.json'
        try:
            record['ac_before'] = ac()
            record['resources_before'] = resources()
            record['host_clock_before'] = host_clock()
            try:
                result = command(['docker', 'exec', container, '/opt/cpu-calibration/calibrate', str(iterations)],
                                 timeout=config['probe_timeout_s'])
            finally:
                record['host_clock_after'] = host_clock()
                record.update(clock_delta(record['host_clock_before'], record['host_clock_after']))
            record['raw_stdout'] = result.stdout
            record['raw_stderr'] = result.stderr
            record['resources_after'] = resources()
            record['ac_after'] = ac()
            data = json.loads(result.stdout)
            record['result'] = data
            if config['max_clock_drift_ns'] is not None:
                if (record['host_monotonic_elapsed_ns'] <= 0
                        or abs(record['host_wall_minus_monotonic_ns']) > config['max_clock_drift_ns']):
                    raise RuntimeError('host realtime/monotonic difference exceeds construction protocol')
                assert data['schema'] == 1 and data['test_only'] is True
                assert data['scope'] == 'fixed_arithmetic_three_processes'
                assert data['dimensions'] == 32 and data['inputs'] == 1024 and data['elapsed_ns'] > 0
                assert data['expected_checksum'] == integer_reference(iterations)
                assert [p['role'] for p in data['processes']] == ['leader', 'worker', 'worker']
            assert data['verified'] is True and data['affinity'] == list(range(10))
            assert data['iterations_per_process'] == iterations
            assert len(data['processes']) == 3 and len({p['pid'] for p in data['processes']}) == 3
            assert {p['participant'] for p in data['processes']} == {0, 1, 2}
            for p in data['processes']:
                assert p['iterations'] == iterations and p['checksum'] == data['expected_checksum']
                assert p['user_cpu_us'] >= 0 and p['system_cpu_us'] >= 0 and p['elapsed_ns'] > 0
            record['status'] = 'verified'
            return record
        except (Exception, KeyboardInterrupt) as error:
            record.update(status='failed', error=repr(error))
            raise
        finally:
            record['finished_at_utc'] = stamp()
            write(path, record)
            summary['attempts'].append(record)
            if kind == 'formal':
                summary['records'].append(record)
            elif kind == 'warmup':
                summary['warmups'].append(record)
            else:
                summary['sizing'] = record
            write(run / 'summary.json', summary)

    initial_protocol = {
        'schema': 2, 'test_only': True, 'profile': profile, 'created_at_utc': stamp(), 'sources': source_hashes,
        'scope': 'fixed arithmetic loop only; process setup and integer reference excluded; outer wall includes barrier/reaping',
        'participants': 3, 'dimensions': 32, 'input_vectors': 1024, 'linux_guest_cpu_affinity': list(range(10)),
        'network': 'none', 'database': 'none', 'memory_bytes': 536870912, 'bases': BASES,
        'sizing_probes': config['sizing_probes'], 'sizing_iterations_per_process': 5000000 if profile == 'short' else None,
        'warmup_probes': config['warmup_probes'], 'warmup_used_for_selection_or_statistics': False,
        'selection_rule': ('round half up (5M * 2 seconds / sizing outer elapsed seconds) to whole million, clamp 20M..50M; duration only'
                           if profile == 'short' else 'fixed 1500000000 per process; no sizing or duration/variance eligibility gate'),
        'budget_including_build_s': config['budget_s'], 'probe_timeout_s': config['probe_timeout_s'],
        'container_sleep_s': config['budget_s'], 'cleanup_outside_budget': True,
        'max_host_realtime_monotonic_difference_ns': config['max_clock_drift_ns'],
        'clock_drift_rule': 'record both clocks; construction only: abs(delta realtime - delta monotonic) > 100ms invalidates and stops; no replacement',
        'formal_probes': 12, 'schedule': list(range(1, 13)), 'stop_on_failure': True, 'replacement_or_extra_probes': False,
        'limitations': ['Exploratory fixed-work calibration, not HNSW or 5% acceptance.',
                        'No normalization of existing observations.', 'CPU time per work unit does not establish hardware frequency.',
                        'Existing unrelated containers remain untouched; ambient host/VM contention is not controlled.'],
    }
    write(run / 'initial-protocol.json', initial_protocol)
    try:
        images = {}
        for tag, expected in BASES.items():
            info = json.loads(command(['docker', 'image', 'inspect', tag]).stdout)[0]
            assert info['Id'] == expected, f'image identity changed: {tag}'
            images[tag] = info
        write(run / 'base-images.json', images)
        ac()
        tag = 'opentenbase-cpu-calibration:' + nonce
        command(['docker', 'build', '--network=none', '--pull=false', '--progress=plain', '-t', tag, str(source)], timeout=60)
        image = json.loads(command(['docker', 'image', 'inspect', tag]).stdout)[0]
        base_layers = images['opentenbase-pg18-pgvector:timing-v1-arm64']['RootFS']['Layers']
        assert image['RootFS']['Layers'][:len(base_layers)] == base_layers
        for base_tag, expected in BASES.items():
            assert json.loads(command(['docker', 'image', 'inspect', base_tag]).stdout)[0]['Id'] == expected
        write(run / 'built-image.json', image)
        image_id = image['Id']
        write(run / 'cleanup-scope.json', {'container_name': container_name, 'nonce': nonce, 'image_id': image_id})
        creation_attempted = True
        result = command(['docker', 'create', '--name', container_name,
                          '--label', 'cpu.calibration.nonce=' + nonce, '--network', 'none',
                          '--read-only', '--cpuset-cpus', '0-9', '--memory', '512m', '--memory-swap', '512m',
                          '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', image['Id'], str(config['budget_s'])])
        container = result.stdout.strip()
        assert len(container) == 64
        identity = json.loads(command(['docker', 'inspect', container]).stdout)[0]
        assert identity['Config']['Labels']['cpu.calibration.nonce'] == nonce and identity['Image'] == image['Id']
        write(run / 'container-identity.json', identity)
        command(['docker', 'start', container])
        command(['docker', 'cp', container + ':/opt/cpu-calibration', str(run / 'binary')])
        binary_hashes = {p.name: sha(p) for p in (run / 'binary').iterdir()}
        assert binary_hashes['calibrate.c'] == source_hashes['calibrate.c']
        write(run / 'binary-hashes.json', binary_hashes)
        command(['docker', 'exec', container, '/bin/sh', '-c', 'uname -a; id; cat /proc/self/status'])
        if profile == 'construction':
            parser_checks = {'schema': 1, 'scope': 'invalid arguments only; no calculation', 'records': []}
            for argument in ('', '-1', '+1', 'abc', '4000000001'):
                result = command(['docker', 'exec', container, '/opt/cpu-calibration/calibrate', argument], check=False)
                parser_checks['records'].append({'argument': argument, 'returncode': result.returncode,
                                                'stdout': result.stdout, 'stderr': result.stderr})
                write(run / 'invalid-input-checks.json', parser_checks)
                if result.returncode != 2 or result.stdout:
                    raise RuntimeError('compiled input validation failed before any calculation')
            parser_checks['status'] = 'verified'
            write(run / 'invalid-input-checks.json', parser_checks)
        if profile == 'short':
            sizing = probe('sizing', 1, 5000000)
            iterations = select_iterations(profile, sizing['result']['elapsed_ns'] / 1e9)
        else:
            iterations = select_iterations(profile)
        protocol = dict(initial_protocol, frozen_at_utc=stamp(), iterations_per_process=iterations,
                        image_id=image['Id'], binary_sha256=binary_hashes['calibrate'])
        if profile == 'short':
            protocol['sizing_sha256'] = sha(run / 'sizing-01.json')
        else:
            protocol['invalid_input_checks_sha256'] = sha(run / 'invalid-input-checks.json')
            protocol['expected_checksum_per_process'] = integer_reference(iterations)
        write(run / 'protocol.json', protocol)
        protocol_sha256 = sha(run / 'protocol.json')
        summary['protocol_sha256'] = protocol_sha256
        if profile == 'construction':
            probe('warmup', 1, iterations)
        for number in range(1, 13):
            probe('formal', number, iterations)
        checksums = {r['result']['expected_checksum'] for r in summary['records']}
        assert len(checksums) == 1
        walls = [r['result']['elapsed_ns'] / 1e9 for r in summary['records']]
        cpus = [sum(p['user_cpu_us'] + p['system_cpu_us'] for p in r['result']['processes']) / 1e6 for r in summary['records']]
        def describe(values):
            return {'values': values, 'min': min(values), 'max': max(values), 'median': statistics.median(values),
                    'max_over_min': max(values) / min(values), 'sample_cv': statistics.stdev(values) / statistics.mean(values)}
        summary.update(status='completed', protocol_sha256=protocol_sha256,
                       descriptive={'outer_wall_s': describe(walls), 'sum_process_cpu_s': describe(cpus)},
                       binary_hashes=binary_hashes)
    except (Exception, KeyboardInterrupt) as error:
        summary.update(status='failed', error=repr(error))
    finally:
        if creation_attempted:
            try:
                identity = recover_owned_container(command, container_name, nonce, image_id)
                if identity is None:
                    cleanup = {'status': 'verified_absent', 'container_name': container_name, 'nonce': nonce}
                else:
                    if container is not None and identity['Id'] != container:
                        raise RuntimeError('container ID changed; leaving object untouched')
                    container = identity['Id']
                    write(run / 'cleanup-recovered-identity.json', identity)
                    command(['docker', 'rm', '-f', '-v', container], cleanup_call=True)
                    check = command(['docker', 'inspect', container], check=False, cleanup_call=True)
                    assert check.returncode != 0 and 'no such object' in check.stderr.lower()
                    for mount in identity['Mounts']:
                        if mount['Type'] == 'volume':
                            check_volume = command(['docker', 'volume', 'inspect', mount['Name']], check=False, cleanup_call=True)
                            assert check_volume.returncode != 0 and 'no such volume' in check_volume.stderr.lower()
                    cleanup = {'status': 'verified', 'container_id': container, 'nonce': nonce,
                               'removed_owned_volumes': identity['Mounts']}
            except (Exception, KeyboardInterrupt) as error:
                cleanup = {'status': 'failed', 'container_id': container, 'error': repr(error)}
                summary['status'] = 'failed'
        try:
            summary['input_hashes_at_finish'] = {name: sha(path) for name, path in inputs.items()}
            if summary['input_hashes_at_finish'] != source_hashes:
                raise RuntimeError('source or method changed during execution')
            if {p.name: sha(p) for p in source.iterdir()} != source_hashes:
                raise RuntimeError('archived source or method changed during execution')
            if protocol_sha256 is not None and sha(run / 'protocol.json') != protocol_sha256:
                raise RuntimeError('frozen protocol changed during execution')
            summary['source_hashes_unchanged'] = True
        except (Exception, KeyboardInterrupt) as error:
            summary.update(status='failed', source_hashes_unchanged=False, source_verification_error=repr(error))
        summary.update(cleanup=cleanup, finished_at_utc=stamp())
        write(run / 'cleanup.json', cleanup)
        write(run / 'summary.json', summary)
        print(json.dumps({'status': summary['status'], 'run_directory': str(run), 'error': summary.get('error'), 'cleanup': cleanup}))
    return 0 if summary['status'] == 'completed' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=tuple(PROFILES), default='short')
    raise SystemExit(main(parser.parse_args().profile))
