#!/usr/bin/env python3
"""Read-only independent audit of the fixed twelve-build instrumentation bridge.

Reuses standard-library audit helpers, never the measured runners. This single
panel describes instrumented/plain ratios; it does not update 5% acceptance.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import random
import re
import tarfile

import audit_crossover as timing_audit
import audit_mechanism as work_audit

ROOT = Path(__file__).resolve().parents[2]
LABELS = ('plain-baseline', 'counter-baseline', 'plain-on', 'counter-on')
DESCRIPTION_SCOPE = 'one exploratory panel; two repeats are not independent acceptance evidence'
require, read, digest = work_audit.require, work_audit.read, work_audit.digest


def description(rows):
    expected = {(label, repeat) for label in LABELS for repeat in (0, 1)}
    keyed = {(r['label'], r['repeat']): r for r in rows}
    require(len(rows) == 8 and set(keyed) == expected, 'missing or duplicate bridge measurements')
    require(all(work_audit.positive(row['command_seconds']) for row in rows), 'invalid bridge duration')
    groups = []
    for condition in ('baseline', 'on'):
        labels = (f'plain-{condition}', f'counter-{condition}')
        values = {label: [keyed[label, repeat]['command_seconds'] for repeat in (0, 1)] for label in labels}
        # Independent log-domain computation; exactly one geometric mean per image.
        geometric = {label: math.exp(math.fsum(math.log(v) for v in times) / 2)
                     for label, times in values.items()}
        groups.append(dict(condition=condition, times=values, geometric_seconds=geometric,
            instrumented_over_plain_ratio=geometric[labels[1]] / geometric[labels[0]]))
    return dict(scope=DESCRIPTION_SCOPE, groups=groups)


def audit_run(folder):
    folder = Path(folder).resolve()
    require(folder.parent == ROOT / 'experiments/hnsw_build/results' and folder.name.endswith('-mechanism-bridge'),
            'not a task-local bridge run')
    protocol, result = read(folder / 'protocol.json'), read(folder / 'summary.json')
    require(result['status'] == 'completed', 'incomplete bridge cannot yield descriptive conclusions')
    fixed = dict(schema=1, exploratory=True, no_acceptance_inference=True, formal_count=8, warmup_count=4,
        workers=2, spill=False, rows=100000, dimensions=32, memory='256MB', m=16, ef_construction=64,
        affinity='0-9', no_effect_based_sample_addition=True)
    for key, expected in fixed.items():
        require(type(protocol.get(key)) is type(expected) and protocol[key] == expected, 'protocol mismatch: ' + key)
    order = list(LABELS)
    random.Random(202609131).shuffle(order)
    require(protocol['slots'] == list(LABELS) and protocol['warmup_order'] == order and
            protocol['order'] == order + order[::-1], 'bridge slot/order differs from fixed schedule')
    expected_sources = {'acceptance.py', 'acceptance_stack.py', 'mechanism_diagnostic.py',
                        'run.py', 'timing.py', 'instrumentation_bridge.py'}
    require(set(protocol['sources']) == expected_sources, 'measured source set mismatch')
    for name, key in (('plain-manifest-at-start.json', 'plain_manifest_sha256'),
                      ('counter-manifest-at-start.json', 'counter_manifest_sha256'),
                      ('method-at-start.md', 'method_sha256')):
        require(digest(folder / name) == protocol[key], 'snapshot hash mismatch: ' + name)
    with tarfile.open(folder / 'tooling-at-start.tar.gz') as archive:
        members = archive.getmembers()
        require(len(members) == len(expected_sources) and {m.name for m in members} == expected_sources,
                'source archive set mismatch')
        for member in members:
            require(member.isfile() and hashlib.sha256(archive.extractfile(member).read()).hexdigest()
                    == protocol['sources'][member.name], 'archived measured source hash mismatch')
    plain, counter = read(folder / 'plain-manifest-at-start.json'), read(folder / 'counter-manifest-at-start.json')
    require(plain['status'] == counter['status'] == 'passed' and counter['test_only'] is True,
            'images lack successful source-attested build evidence')
    require(counter['prior_manifest_sha256'] == protocol['plain_manifest_sha256'] and
            counter['candidate_changes'] == plain['candidate_changes'] and
            counter['baseline_commit'] == plain['baseline_commit'], 'instrumentation built from another candidate/baseline')
    require(set(protocol['images']) == set(protocol['identity_sha256']) == set(LABELS), 'image labels mismatch')
    identities = {}
    for slot, label in enumerate(LABELS):
        variant = 'baseline' if label.endswith('baseline') else 'candidate'
        expected = plain['images'][variant + '-seed42'] if label.startswith('plain-') else counter['images'][variant]
        directory = folder / 'p00' / label
        identity = read(directory / 'identity.json')
        require(identity['image'] == protocol['images'][label] == expected['id'] and
                re.fullmatch(r'sha256:[0-9a-f]{64}', identity['image']), 'image identity mismatch')
        require(hashlib.sha256(identity['source_attestation'].encode()).hexdigest() ==
                protocol['identity_sha256'][label] == expected['identity_sha256'], 'source/binary attestation mismatch')
        require(identity['port'] == 55432 + slot and identity['affinity'] == '0-9' and
                identity['memory_limit'] == 2 * 2 ** 30, 'instance slot/resources mismatch')
        require(identity['data']['large']['rows'] == 100000 and identity['data']['small']['rows'] == 30000,
                'fixture size mismatch')
        require(read(directory / 'cleanup.json') == {'status': 'complete', 'errors': []}, 'incomplete owned cleanup')
        identities[label] = identity
    require(len({i['container_id'] for i in identities.values()}) == 4 and
            len({i['system_identifier'] for i in identities.values()}) == 4, 'instance reuse')
    require(all(i['data'] == identities[LABELS[0]]['data'] for i in identities.values()), 'fixture digest mismatch')
    lookup, paths, counter_paths, artifacts, warnings = {}, set(), set(), {}, []
    for category, expected_count in (('rows', 8), ('warmups', 4)):
        require(len(result[category]) == expected_count, 'wrong bridge measurement count')
        for row in result[category]:
            label = row['label']
            require(label in LABELS, 'unknown bridge condition')
            key = (label, category, row['repeat'])
            require(key not in lookup, 'duplicate bridge measurement')
            lookup[key] = row
            path = (folder / row['source']).resolve()
            require(path.is_relative_to(folder) and path not in paths, 'unsafe/repeated measurement path')
            paths.add(path)
            raw = read(path / 'measurement.json')
            require(raw == {k: v for k, v in row.items() if k not in ('label', 'repeat', 'position', 'source')},
                    'summary differs from original measurement')
            condition = 'baseline' if label.endswith('baseline') else 'on'
            require(raw['condition'] == condition and raw['workers'] == 2 and raw['spill'] is False
                    and raw['warmup'] is (category == 'warmups') and raw['require_ac'] is True
                    and raw['command_returncode'] == 0 and 'error' not in raw, 'invalid build completion/configuration')
            require(raw['image'] == identities[label]['image'] and work_audit.integer(raw['index_bytes'], 1),
                    'measurement image or final index size mismatch')
            require(all(work_audit.positive(raw[k]) for k in ('command_seconds', 'civil_wall_seconds', 'started_epoch'))
                    and abs(raw['command_seconds'] - raw['civil_wall_seconds']) <= 1, 'invalid/suspended build clocks')
            boundary = []
            for side in ('resources_before', 'resources_after'):
                resource = raw[side]
                require(resource['power_source'] == 'AC' and len(resource['host_load_average']) == 3 and
                        all(type(v) in (int, float) and math.isfinite(v) and v >= 0 for v in resource['host_load_average']),
                        'invalid power or host resource evidence')
                values = timing_audit.resource_fields(resource['cgroup'])
                boundary.append(values)
                if values['throttled_usec'] or any(values['memory_events'].values()):
                    warnings.append(dict(source=row['source'], boundary=side, counters=values))
            require(boundary[1]['cpu_usage_usec'] >= boundary[0]['cpu_usage_usec'], 'reversed CPU counter')
            text = (path / 'build.stderr.txt').read_text()
            require(re.findall(r'using (\d+) parallel workers', text) == ['2'] and 'graph no longer fits' not in text,
                    'actual workers/spill differ from bridge configuration')
            bridge = read(path / 'bridge.json')
            instrumented = label.startswith('counter-')
            require(set(bridge) == {'index_oid', 'instrumented'} and work_audit.integer(bridge['index_oid'], 1)
                    and bridge['instrumented'] is instrumented, 'actual index query/instrumentation mismatch')
            if instrumented:
                work = work_audit.independent_records(text, 100000, bridge['index_oid'])
                require(read(path / 'work.json') == work, 'parsed counters differ from machine log or actual index OID')
                counter_paths.add(path)
            else:
                require('HNSW_MECHANISM ' not in text and not (path / 'work.json').exists(), 'plain image emitted counters')
            timing_audit.validate_timing(text, raw)
            if condition == 'on':
                record = raw['internal_timing']['records'][0]
                require(record['index_oid'] == bridge['index_oid'], 'timing record differs from actual index OID')
                if instrumented:
                    leader = next(r for r in work['records'] if r['worker_number'] == -1)
                    require(record['pid'] == leader['pid'], 'timing and work leader PID mismatch')
            for name in ('measurement.json', 'build.stderr.txt', 'bridge.json') + (('work.json',) if instrumented else ()):
                artifacts[str((path / name).relative_to(folder))] = digest(path / name)
    require({p.resolve() for p in folder.rglob('measurement.json')} == {p / 'measurement.json' for p in paths}
            and {p.resolve() for p in folder.rglob('bridge.json')} == {p / 'bridge.json' for p in paths}
            and {p.resolve() for p in folder.rglob('work.json')} == {p / 'work.json' for p in counter_paths},
            'missing or extra raw evidence outside the twelve scheduled builds')
    require(len(counter_paths) == 6, 'expected exactly six instrumented builds')
    events = [(label, 'warmups', 0) for label in order]
    events += [(label, 'rows', int(i >= 4)) for i, label in enumerate(order + order[::-1])]
    first_start, previous_end = None, None
    for position, (label, category, repeat) in enumerate(events):
        require((label, category, repeat) in lookup, 'missing scheduled bridge event')
        row = lookup.pop((label, category, repeat))
        expected_path = f"p00/{label}/{'warmup' if category == 'warmups' else 'measure'}-{repeat}"
        require(row['position'] == position and row['source'] == expected_path, 'event position/path mismatch')
        start = row['started_epoch']
        require(previous_end is None or start >= previous_end - 1e-6, 'overlapping or reordered bridge builds')
        if first_start is None:
            first_start = start
        previous_end = start + row['civil_wall_seconds']
    require(not lookup and datetime.fromisoformat(protocol['created_at_utc']).timestamp() <= first_start
            and datetime.fromisoformat(result['finished_at_utc']).timestamp() >= previous_end, 'invalid run chronology')
    independent = description(result['rows'])
    require(timing_audit.almost_equal(result.get('description'), independent), 'independent geometric means/ratios differ')
    return dict(audit_status='verified', status='exploratory_bridge_verified', exploratory=True,
        no_acceptance_inference=True, panels=1, formal_count=8, warmup_count=4,
        verified_counter_builds=6, verified_counter_records=18, verified_actual_index_records=12,
        verified_instance_identities=4, verified_cleanup_records=4, source_archive_verified=True,
        actual_sequence_verified=True, description=independent, boundary_resource_warnings=warnings,
        live_resource_absence='not queried; owned cleanup records verified offline',
        limitation='One exploratory panel; two repeats are not independent units. These ratios do not update the 5% acceptance or uniquely identify host-frequency/compilation causes.',
        protocol_sha256=digest(folder / 'protocol.json'), summary_sha256=digest(folder / 'summary.json'),
        raw_artifacts_sha256=artifacts,
        audit_source_sha256={p.name: digest(p) for p in (Path(__file__), Path(work_audit.__file__), Path(timing_audit.__file__))},
        audited_at_utc=datetime.now(timezone.utc).isoformat())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True, type=Path)
    parser.add_argument('--output', type=Path, help='optional new JSON artifact; refuses overwrite')
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
