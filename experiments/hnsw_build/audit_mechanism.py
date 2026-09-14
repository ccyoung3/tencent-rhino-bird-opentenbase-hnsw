#!/usr/bin/env python3
"""Independent, standard-library-only audit of bounded mechanism diagnostics.

Never imports measured tooling, starts a database, pools smoke with diagnosis,
or interprets work-normalized instrumentation as a performance acceptance.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import itertools
import json
import math
from pathlib import Path
import random
import re
import tarfile

ROOT = Path(__file__).resolve().parents[2]
LABELS = ('baseline', 'off', 'on')
SCENES = {
    'no-spill': dict(table='large', rows=100000, memory='256MB', spill='none'),
    'immediate-spill': dict(table='small', rows=30000, memory='4MB', spill='zero'),
    'partial-spill': dict(table='small', rows=30000, memory='8MB', spill='partial'),
}
PHASES = ('setup', 'memory_build', 'spill_drain', 'flush', 'disk_insert', 'finalize', 'wal', 'cleanup')
COUNTERS = ('callbacks_seen', 'successful_inserts', 'distance_calls', 'elements_initialized',
            'user_cpu_us', 'system_cpu_us', 'elapsed_us')
PREFIX = 'NOTICE: HNSW_MECHANISM '


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate JSON field: ' + key)
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError('nonfinite JSON value: ' + value)


def decode(text):
    return json.loads(text, object_pairs_hook=unique_object, parse_constant=reject_constant)


def read(path):
    return decode(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def integer(value, minimum=0):
    return type(value) is int and value >= minimum


def positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def independent_records(text, rows, index_oid):
    marked = [line for line in text.splitlines() if 'HNSW_MECHANISM ' in line]
    require(len(marked) == 3 and all(line.startswith(PREFIX) for line in marked),
            'expected exactly three NOTICE counter records')
    records = [decode(line[len(PREFIX):]) for line in marked]
    for record in records:
        require(isinstance(record, dict), 'counter record is not an object')
        require(type(record.get('schema')) is int and record['schema'] == 1
                and record.get('test_only') is True and record.get('scope') == 'scan_and_insert'
                and record.get('mode') == 'native', 'counter schema or exploratory scope mismatch')
        require(integer(record.get('pid'), 1) and integer(record.get('index_oid'), 1)
                and type(record.get('worker_number')) is int, 'invalid process or index identity')
        number = record['worker_number']
        require(number in (-1, 0, 1) and record.get('role') == ('leader' if number == -1 else 'worker')
                and record['index_oid'] == index_oid, 'counter role or actual index mismatch')
        require(all(integer(record.get(key)) for key in COUNTERS) and record['elapsed_us'] > 0,
                'invalid integer counter or participant elapsed time')
        hist = record.get('level_hist')
        require(isinstance(hist, list) and len(hist) == 64 and all(integer(v) for v in hist),
                'invalid level histogram')
        require(0 < sum(hist) == record['elements_initialized'] == record['callbacks_seen']
                == record['successful_inserts'], 'participant tuple/histogram coverage mismatch')
        require(record['distance_calls'] > 0 and record['user_cpu_us'] + record['system_cpu_us'] > 0,
                'participant has no measured distance work or CPU')
    require(len({r['pid'] for r in records}) == 3 and
            {r['worker_number'] for r in records} == {-1, 0, 1}, 'duplicate participant')
    require(sum(r['callbacks_seen'] for r in records) == rows, 'incomplete heap coverage')
    totals = {key: sum(r[key] for r in records) for key in COUNTERS if key != 'elapsed_us'}
    totals['cpu_seconds'] = (totals['user_cpu_us'] + totals['system_cpu_us']) / 1000000
    totals['level_hist'] = [sum(r['level_hist'][level] for r in records) for level in range(64)]
    # Parallel elapsed intervals overlap; summing them would not be wall time.
    totals['max_participant_elapsed_seconds'] = max(r['elapsed_us'] for r in records) / 1000000
    return dict(scope='scan_and_insert', records=records, totals=totals)


def expected_schedule(mode):
    rng = random.Random(20260913)
    orders = list(itertools.permutations(LABELS))
    rng.shuffle(orders)
    scenes = list(SCENES)
    rng.shuffle(scenes)
    schedule = [dict(panel=p, slots=list(LABELS if p == 0 else LABELS[::-1]),
        scenes=[dict(scene=scene, warmup_order=list(orders[3 * p + i]),
                     order=list(orders[3 * p + i]) + list(orders[3 * p + i][::-1]))
                for i, scene in enumerate(scenes if p == 0 else scenes[::-1])]) for p in range(2)]
    if mode == 'smoke':
        schedule = schedule[:1]
        for scene in schedule[0]['scenes']:
            scene['order'] = []
    return schedule


def validate_timing(text, raw):
    encoded = [line.split('hnsw build timing: ', 1)[1] for line in text.splitlines()
               if 'hnsw build timing: ' in line]
    if raw['condition'] != 'on':
        require(not encoded and raw['internal_timing'] == {'status': 'not_requested', 'records': []},
                'disabled timing emitted a record')
        return
    require(len(encoded) == 1, 'timing-enabled build must emit one summary')
    record = decode(encoded[0])
    for key, expected in dict(version=1, status='complete', scope='hnsw_build', clock='elapsed_wall',
                              fork=0, parallel_workers=2, spill=raw['scene'] != 'no-spill').items():
        require(type(record.get(key)) is type(expected) and record[key] == expected,
                'timing header mismatch: ' + key)
    require(record.get('index_oid') == raw['index_oid'] and integer(record.get('total_us'), 1),
            'timing index or duration mismatch')
    leader = next(r for r in raw['work']['records'] if r['role'] == 'leader')
    require(record.get('pid') == leader['pid'], 'timing and counter leader PID mismatch')
    require([p.get('phase') for p in record['phases']] == list(PHASES), 'unexpected timing phase order')
    boundary, durations = 0, {}
    for phase in record['phases']:
        name, start, end = phase['phase'], phase['start_us'], phase['end_us']
        absent = raw['scene'] == 'no-spill' and name in ('spill_drain', 'disk_insert')
        if absent or (name == 'wal' and start is None and end is None):
            require(start is None and end is None, 'unexpected absent-phase timing')
            durations[name] = None
        else:
            require(integer(start) and integer(end) and start == boundary and end >= start,
                    'timing gap, overlap, or reversed boundary')
            durations[name], boundary = end - start, end
    require(boundary == record['total_us'], 'timing phases do not cover total')
    record['durations_us'] = durations
    dominant = max(((name, value) for name, value in durations.items() if value is not None), key=lambda p: p[1])
    expected = dict(status='complete', records=[record], dominant_phase=dominant[0],
                    dominant_fraction=dominant[1] / record['total_us'])
    require(raw['internal_timing'] == expected, 'raw timing differs from log')


def audit_run(folder):
    folder = Path(folder).resolve()
    require(folder.parent == ROOT / 'experiments/hnsw_build/results' and '-mechanism-' in folder.name,
            'not a task-local mechanism run')
    protocol, result = read(folder / 'protocol.json'), read(folder / 'summary.json')
    require(result['status'] == 'completed', 'incomplete run: no mechanism conclusion or acceptance')
    mode = protocol['mode']
    require(mode in ('smoke', 'diagnosis'), 'unknown mechanism mode')
    panels, formal, warmups = (1, 0, 9) if mode == 'smoke' else (2, 36, 18)
    fixed = dict(schema=1, exploratory=True, workers=2, affinity='0-9', formal_count=formal,
                 warmup_count=warmups, no_acceptance_inference=True, no_effect_based_sample_addition=True)
    for key, expected in fixed.items():
        require(type(protocol.get(key)) is type(expected) and protocol[key] == expected,
                'protocol field mismatch: ' + key)
    require(protocol['schedule'] == expected_schedule(mode) and protocol['scenes'] == SCENES,
            'protocol schedule or scene settings changed')
    require(protocol['scope'] == 'participant scan_and_insert counters exclude final leader flush/WAL/cleanup',
            'unexpected mechanism scope')
    require(set(protocol['sources']) == {'acceptance.py', 'acceptance_stack.py', 'run.py', 'timing.py',
                                        'mechanism_diagnostic.py'}, 'unexpected measured source set')
    require(digest(folder / 'method-at-start.md') == protocol['method_sha256'], 'frozen method hash mismatch')
    require(digest(folder / 'build-manifest-at-start.json') == protocol['build_manifest_sha256'],
            'frozen image manifest hash mismatch')
    with tarfile.open(folder / 'tooling-at-start.tar.gz') as archive:
        members = archive.getmembers()
        require(len(members) == len(protocol['sources']) and {m.name for m in members} == set(protocol['sources']),
                'source archive set mismatch')
        for member in members:
            require(member.isfile() and hashlib.sha256(archive.extractfile(member).read()).hexdigest()
                    == protocol['sources'][member.name], 'archived source hash mismatch')
    build = read(folder / 'build-manifest-at-start.json')
    require(build['status'] == 'passed' and build['test_only'] is True, 'not an attested test-only image build')
    require(set(protocol['images']) == set(LABELS), 'image labels mismatch')
    identities, datasets = {}, []
    for panel in protocol['schedule']:
        for slot, label in enumerate(panel['slots']):
            directory = folder / f"p{panel['panel']:02d}" / label
            identity = read(directory / 'identity.json')
            expected = build['images']['baseline' if label == 'baseline' else 'candidate']
            require(identity['image'] == protocol['images'][label] == expected['id'] and
                    re.fullmatch(r'sha256:[0-9a-f]{64}', identity['image']), 'image ID mismatch')
            require(hashlib.sha256(identity['source_attestation'].encode()).hexdigest() == expected['identity_sha256'],
                    'source/binary attestation mismatch')
            require(identity['port'] == 55432 + slot and identity['affinity'] == '0-9' and
                    identity['memory_limit'] == 2 * 2 ** 30, 'instance slot or resource mismatch')
            require(identity['data']['large']['rows'] == 100000 and identity['data']['small']['rows'] == 30000,
                    'fixture row count mismatch')
            require(read(directory / 'cleanup.json') == {'status': 'complete', 'errors': []}, 'incomplete owned cleanup')
            identities[panel['panel'], label] = identity
            datasets.append(identity['data'])
    require(all(data == datasets[0] for data in datasets), 'fixture data differs across images/panels')
    require(len({v['container_id'] for v in identities.values()}) == panels * 3 and
            len({v['system_identifier'] for v in identities.values()}) == panels * 3, 'instance reuse')
    lookup, paths = {}, set()
    for category, expected_count in (('rows', formal), ('warmups', warmups)):
        require(len(result[category]) == expected_count, 'wrong measurement count: ' + category)
        for row in result[category]:
            key = (row['panel'], row['scene'], row['condition'], category, row['repeat'])
            require(key not in lookup, 'duplicate measurement identity')
            lookup[key] = row
            directory = (folder / row['source']).resolve()
            require(directory.is_relative_to(folder) and directory not in paths, 'unsafe or repeated raw path')
            paths.add(directory)
            raw = read(directory / 'measurement.json')
            require(raw == {k: v for k, v in row.items() if k not in ('panel', 'repeat', 'position', 'source')},
                    'summary row differs from raw measurement')
            require(raw['validation'] == 'passed' and raw['command_returncode'] == 0 and 'error' not in raw
                    and raw['warmup'] is (category == 'warmups'), 'invalid successful-build evidence')
            config = SCENES[row['scene']]
            require(raw['config'] == config and raw['workers'] == 2 and
                    raw['image'] == identities[row['panel'], row['condition']]['image'], 'raw workload/image mismatch')
            require(integer(raw['index_oid'], 1) and integer(raw['index_bytes'], 1), 'invalid completed index')
            require(all(positive(raw[key]) for key in ('command_seconds', 'civil_wall_seconds', 'started_epoch')) and
                    abs(raw['command_seconds'] - raw['civil_wall_seconds']) <= 1, 'invalid or suspended timing window')
            require(all(raw[side]['power_source'] == 'AC' for side in ('resources_before', 'resources_after')),
                    'power changed during build')
            text = (directory / 'build.stderr.txt').read_text()
            work = independent_records(text, config['rows'], raw['index_oid'])
            require(raw['work'] == work, 'stored mechanism counters differ from machine log')
            workers = re.findall(r'using (\d+) parallel workers', text)
            require(workers == ['2'], 'actual parallel-worker count mismatch')
            spills = re.findall(r'graph no longer fits into maintenance_work_mem after (\d+) tuples', text)
            after = int(spills[0]) if len(spills) == 1 else None
            require(raw['spill_after_tuples'] == after, 'raw spill count differs from log')
            if config['spill'] == 'none':
                require(not spills, 'unexpected spill')
            elif config['spill'] == 'zero':
                require(len(spills) == 1 and after == 0, 'expected immediate spill')
            else:
                require(len(spills) == 1 and 0 < after < config['rows'], 'expected partial spill')
            validate_timing(text, raw)
    expected_paths = {path / 'measurement.json' for path in paths}
    require({path.resolve() for path in folder.rglob('measurement.json')} == expected_paths,
            'extra or missing raw measurement outside the fixed run')
    previous_end, first_start = None, None
    for panel in protocol['schedule']:
        for scene in panel['scenes']:
            events = [(c, 'warmups', 0) for c in scene['warmup_order']]
            events += [(c, 'rows', int(i >= 3)) for i, c in enumerate(scene['order'])]
            for position, (label, category, repeat) in enumerate(events):
                key = (panel['panel'], scene['scene'], label, category, repeat)
                require(key in lookup, 'missing scheduled event')
                row = lookup.pop(key)
                suffix = 'warmup' if category == 'warmups' else 'measure'
                expected_path = f"p{panel['panel']:02d}/{label}/{scene['scene']}-{suffix}-{repeat}"
                require(row['source'] == expected_path and row['position'] == position, 'event path or position mismatch')
                start = row['started_epoch']
                require(previous_end is None or start >= previous_end - 1e-6, 'overlapping/reordered builds')
                if first_start is None:
                    first_start = start
                previous_end = start + row['civil_wall_seconds']
    require(not lookup, 'unexpected unscheduled event')
    require(datetime.fromisoformat(protocol['created_at_utc']).timestamp() <= first_start and
            datetime.fromisoformat(result['finished_at_utc']).timestamp() >= previous_end, 'invalid run chronology')
    return dict(audit_status='verified', status='smoke_verified' if mode == 'smoke' else 'mechanism_evidence_verified',
        mode=mode, exploratory=True, no_acceptance_inference=True, formal_count=formal, warmup_count=warmups,
        verified_counter_records=(formal + warmups) * 3, verified_instance_identities=panels * 3,
        verified_cleanup_records=panels * 3, source_archive_verified=True, actual_sequence_verified=True,
        live_resource_absence='not queried; owned cleanup records verified offline',
        scope=protocol['scope'],
        limitation='Test-only instrumentation can alter scheduling. Work/CPU normalization is descriptive and cannot establish <5% diagnostic overhead.',
        protocol_sha256=digest(folder / 'protocol.json'), summary_sha256=digest(folder / 'summary.json'),
        audit_tool_sha256=digest(Path(__file__)), audited_at_utc=datetime.now(timezone.utc).isoformat())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True, type=Path)
    parser.add_argument('--output', type=Path, help='optional new audit artifact; refuses overwrite')
    args = parser.parse_args()
    if args.output:
        require(not args.output.exists(), 'refusing to overwrite an audit artifact')
    result = audit_run(args.run)
    encoded = json.dumps(result, indent=2) + '\n'
    if args.output:
        with args.output.open('x') as stream:
            stream.write(encoded)
    print(encoded, end='')


if __name__ == '__main__':
    main()
