#!/usr/bin/env python3
"""One bounded exploratory CPU calibration; never an overhead acceptance test."""
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
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
RESOURCE_SCRIPT = 'for f in cpu.stat cpu.max cpu.pressure cpuset.cpus.effective memory.current memory.events io.stat; do printf "FILE:%s\\n" "$f"; cat "/sys/fs/cgroup/$f" || exit; done'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def main():
    nonce = uuid.uuid4().hex[:12]
    run = ROOT / 'results' / (dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + nonce)
    run.mkdir(parents=True, exist_ok=False)
    source = run / 'source'
    source.mkdir()
    for name in ('calibrate.c', 'Dockerfile', 'compile.sh', 'run.py'):
        shutil.copy2(ROOT / name, source / name)
    source_hashes = {p.name: sha(p) for p in source.iterdir()}
    deadline = time.monotonic() + 180
    command_number = 0
    container = None
    cleanup = {'status': 'not_created'}
    summary = {'schema': 1, 'test_only': True, 'status': 'running', 'started_at_utc': stamp(),
               'nonce': nonce, 'sources': source_hashes, 'records': [], 'run_directory': str(run)}
    write(run / 'summary.json', summary)

    def command(args, *, timeout=20, check=True, cleanup_call=False):
        nonlocal command_number
        command_number += 1
        record = {'argv': args, 'started_at_utc': stamp()}
        started = time.monotonic()
        try:
            remaining = 20 if cleanup_call else deadline - started
            if remaining <= 0:
                raise TimeoutError('fixed 180-second budget exhausted')
            result = subprocess.run(args, capture_output=True, text=True, timeout=min(timeout, remaining))
            record.update(returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)
        except Exception as error:
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
            result = command(['docker', 'exec', container, '/opt/cpu-calibration/calibrate', str(iterations)], timeout=15)
            record['raw_stdout'] = result.stdout
            record['raw_stderr'] = result.stderr
            record['resources_after'] = resources()
            record['ac_after'] = ac()
            data = json.loads(result.stdout)
            assert data['verified'] is True and data['affinity'] == list(range(10))
            assert data['iterations_per_process'] == iterations
            assert len(data['processes']) == 3 and len({p['pid'] for p in data['processes']}) == 3
            assert {p['participant'] for p in data['processes']} == {0, 1, 2}
            for p in data['processes']:
                assert p['iterations'] == iterations and p['checksum'] == data['expected_checksum']
                assert p['user_cpu_us'] >= 0 and p['system_cpu_us'] >= 0 and p['elapsed_ns'] > 0
            record['result'] = data
            record['status'] = 'verified'
            return record
        except Exception as error:
            record.update(status='failed', error=repr(error))
            raise
        finally:
            record['finished_at_utc'] = stamp()
            write(path, record)

    initial_protocol = {
        'schema': 1, 'test_only': True, 'created_at_utc': stamp(), 'sources': source_hashes,
        'scope': 'fixed arithmetic loop only; process setup and integer reference excluded; outer wall includes barrier/reaping',
        'participants': 3, 'dimensions': 32, 'input_vectors': 1024, 'linux_guest_cpu_affinity': list(range(10)),
        'network': 'none', 'database': 'none', 'memory_bytes': 536870912, 'bases': BASES,
        'sizing_probes': 1, 'sizing_iterations_per_process': 5000000,
        'selection_rule': 'round half up (5M * 2 seconds / sizing outer elapsed seconds) to whole million, clamp 20M..50M; duration only',
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
        result = command(['docker', 'create', '--name', 'cpu-calibration-' + nonce,
                          '--label', 'cpu.calibration.nonce=' + nonce, '--network', 'none',
                          '--read-only', '--cpuset-cpus', '0-9', '--memory', '512m', '--memory-swap', '512m',
                          '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', image['Id'], '180'])
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
        sizing = probe('sizing', 1, 5000000)
        summary['sizing'] = sizing
        elapsed_s = sizing['result']['elapsed_ns'] / 1e9
        iterations = max(20, min(50, math.floor((5 * 2 / elapsed_s) + 0.5))) * 1000000
        protocol = dict(initial_protocol, frozen_at_utc=stamp(), iterations_per_process=iterations,
                        sizing_sha256=sha(run / 'sizing-01.json'), image_id=image['Id'], binary_sha256=binary_hashes['calibrate'])
        write(run / 'protocol.json', protocol)
        for number in range(1, 13):
            summary['records'].append(probe('formal', number, iterations))
            write(run / 'summary.json', summary)
        checksums = {r['result']['expected_checksum'] for r in summary['records']}
        assert len(checksums) == 1
        walls = [r['result']['elapsed_ns'] / 1e9 for r in summary['records']]
        cpus = [sum(p['user_cpu_us'] + p['system_cpu_us'] for p in r['result']['processes']) / 1e6 for r in summary['records']]
        def describe(values):
            return {'values': values, 'min': min(values), 'max': max(values), 'median': statistics.median(values),
                    'max_over_min': max(values) / min(values), 'sample_cv': statistics.stdev(values) / statistics.mean(values)}
        summary.update(status='completed', protocol_sha256=sha(run / 'protocol.json'),
                       descriptive={'outer_wall_s': describe(walls), 'sum_process_cpu_s': describe(cpus)},
                       binary_hashes=binary_hashes)
    except Exception as error:
        summary.update(status='failed', error=repr(error))
    finally:
        if container:
            try:
                identity = json.loads(command(['docker', 'inspect', container], cleanup_call=True).stdout)[0]
                assert identity['Id'] == container and identity['Config']['Labels']['cpu.calibration.nonce'] == nonce
                command(['docker', 'rm', '-f', '-v', container], cleanup_call=True)
                check = command(['docker', 'inspect', container], check=False, cleanup_call=True)
                assert check.returncode != 0 and 'No such object' in check.stderr
                cleanup = {'status': 'verified', 'container_id': container, 'nonce': nonce,
                           'removed_owned_volumes': identity['Mounts']}
            except Exception as error:
                cleanup = {'status': 'failed', 'container_id': container, 'error': repr(error)}
                summary['status'] = 'failed'
        summary.update(cleanup=cleanup, finished_at_utc=stamp())
        write(run / 'cleanup.json', cleanup)
        write(run / 'summary.json', summary)
        print(json.dumps({'status': summary['status'], 'run_directory': str(run), 'error': summary.get('error'), 'cleanup': cleanup}))
    return 0 if summary['status'] == 'completed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
