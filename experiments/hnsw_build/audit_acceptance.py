#!/usr/bin/env python3
"""Offline acceptance audit: immutable raw records, independent reaggregation, provenance."""
import argparse
import hashlib
import json
import re
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

import acceptance as a
import run
import timing

ROOT = run.PROJECT_ROOT
DOCS = {'README.md', 'docs/2026-09-02-project-brief.md', 'docs/2026-09-04-frozen-snapshot-review.md',
        'experiments/hnsw_build/README.md', 'experiments/hnsw_build/results/README.md'}


def audit_run(folder):
    folder = folder.resolve()
    if folder.parent != run.RESULTS_ROOT or '-bounded-acceptance-' not in folder.name:
        raise ValueError('only task-local acceptance results are accepted')
    protocol, result = a.read(folder / 'protocol.json'), a.read(folder / 'summary.json')
    assert result['status'] == 'completed'
    mode, aa = protocol['mode'], protocol['mode'] != 'formal'
    assert mode in ('smoke', 'aa', 'formal')
    n = 1 if mode == 'smoke' else 8 if aa else 24
    expected = a.schedule(8 if aa else 24, aa)[:n]
    assert json.loads(json.dumps(expected)) == protocol['schedule']
    assert protocol['panels'] == n
    assert protocol['common_build_manifest_sha256'] == a.sha(a.SNAPSHOT / 'build-manifest.json')
    with tarfile.open(folder / 'tooling-at-start.tar.gz') as archive:
        assert set(archive.getnames()) == set(protocol['sources'])
        for name, digest in protocol['sources'].items():
            assert hashlib.sha256(archive.extractfile(name).read()).hexdigest() == digest
    labels = ['aa_a', 'aa_b'] if aa else a.CONDITIONS
    keys = {(p, w, s, c) for p in range(n) for w, s in a.SCENES for c in labels}
    seen_paths = set()
    observations = 0
    for category in ('rows', 'warmups'):
        rows = result[category]
        assert len(rows) == len(keys)
        assert {(r['panel'], r['workers'], r['spill'], r['condition']) for r in rows} == keys
        for row in rows:
            directory = (folder / row['source']).resolve()
            assert directory.is_relative_to(folder) and directory not in seen_paths
            seen_paths.add(directory)
            raw = a.read(directory / 'measurement.json')
            compare = {**row}
            for key in ('condition', 'effective_condition', 'panel', 'source'):
                compare.pop(key)
            compare['condition'] = row['effective_condition']
            assert compare == raw
            assert raw['command_returncode'] == 0 and raw['warmup'] == (category == 'warmups')
            if 'host_controls' in protocol:
                assert raw['require_ac'] and raw['resources_before']['power_source'] == raw['resources_after']['power_source'] == 'AC'
                assert abs(raw['civil_wall_seconds'] - raw['command_seconds']) <= 1
            effective = 'off' if aa else row['condition']
            assert raw['condition'] == effective
            text = (directory / 'build.stderr.txt').read_text()
            parsed = timing.parse_build_timing(text, requested=effective in ('on', 'observed'), command_returncode=0)
            assert parsed == raw['internal_timing']
            workers = re.search(r'using (\d+) parallel workers', text)
            assert (int(workers[1]) if workers else 0) == raw['workers']
            assert ('graph no longer fits' in text) == raw['spill']
            if effective == 'observed' and category == 'rows':
                observation = a.read(directory / 'observer/summary.json')
                assert observation == raw['observer']['observation']
                assert observation['server']['read_only'] == 'on' and observation['build_outcome'] == 'unknown'
                assert observation['status'] in ('stopped', 'ended_unconfirmed')
                samples = [json.loads(line) for line in (directory / 'observer/samples.jsonl').read_text().splitlines()]
                assert len(samples) == observation['samples'] > 0
                assert any(s['state'] and s['state'].get('phase') for s in samples)
                assert sum(observation['observation_counts'].values()) == len(samples)
                observations += 1
    identities, cleanups = [], []
    build = a.read(a.SNAPSHOT / 'build-manifest.json')
    for p in range(n):
        data = []
        for label in labels:
            directory = folder / f'p{p:02d}' / label
            identity, cleanup = a.read(directory / 'identity.json'), a.read(directory / 'cleanup.json')
            variant = 'candidate' if aa or label != 'baseline' else 'baseline'
            assert identity['image'] == build['images'][variant + '-seed42']['id']
            attestation = ROOT / build['attempt_directory'] / f'identity-{variant}-seed42.txt'
            assert identity['source_attestation'] == attestation.read_text()
            assert cleanup == {'status': 'complete', 'errors': []}
            assert identity['memory_limit'] == 2*2**30 and identity['affinity'] == protocol['affinity']
            assert identity['data']['large']['rows'] == protocol['large_rows']
            assert identity['data']['small']['rows'] == protocol['small_rows']
            data.append(identity['data'])
            identities.append(identity['container_id'])
            cleanups.append(str(directory.relative_to(ROOT)))
        assert all(d == data[0] for d in data)
    assert len(identities) == len(set(identities)) == n*len(labels)
    analysis = None if mode == 'smoke' else a.summarize(result['rows'], n, aa)
    if analysis is not None:
        assert analysis == result['analysis']
    return dict(directory=str(folder.relative_to(ROOT)), formal_count=len(result['rows']),
                warmup_count=len(result['warmups']), verified_observers=observations,
                cleaned_instances=len(cleanups), analysis=analysis)


def audit_normal(folder):
    folder = folder.resolve()
    assert folder.parent == run.RESULTS_ROOT and folder.name.endswith('-bounded-acceptance-normal')
    normal, protocol = a.read(folder / 'summary.json'), a.read(folder / 'protocol.json')
    assert normal['status'] == 'passed' and len(normal['builds']) == 16 and len(normal['checks']) == 20
    expected = {(w, s, c) for w, s in a.SCENES for c in a.CONDITIONS}
    assert {(r['workers'], r['spill'], r['condition']) for r in normal['builds']} == expected
    archive_path = folder / 'tooling-at-start.tar.gz'
    if not archive_path.exists():
        archive_path = folder / 'tooling-recovered-by-protocol-hash.tar.gz'
        assert (folder / 'tooling-provenance.md').exists()
    with tarfile.open(archive_path) as archive:
        assert set(archive.getnames()) == set(protocol['source_sha256'])
        for name, digest in protocol['source_sha256'].items():
            assert hashlib.sha256(archive.extractfile(name).read()).hexdigest() == digest
    observers = 0
    for row in normal['builds']:
        directory = (folder / row['source']).resolve()
        assert directory.is_relative_to(folder)
        raw = a.read(directory / 'measurement.json')
        assert raw == {k: v for k, v in row.items() if k != 'source'}
        assert row['command_returncode'] == 0 and row['image'] == protocol['images'][row['condition']]
        assert row['internal_timing'] == timing.parse_build_timing((directory / 'build.stderr.txt').read_text(),
            requested=row['condition'] in ('on', 'observed'), command_returncode=0)
        query = a.read(directory / 'query-check.json')
        assert query['valid'] and len(query['answer']) == 10 and query['answer'][0] == [1, 0.]
        assert len({r[0] for r in query['answer']}) == 10
        assert 'Index Scan' in json.dumps(query['plan']) and 'items_hnsw' in json.dumps(query['plan'])
        if row['condition'] == 'observed':
            observed = a.read(directory / 'observer/summary.json')
            assert observed == row['observer']['observation']
            assert observed['status'] in ('stopped', 'ended_unconfirmed') and observed['server']['read_only'] == 'on'
            assert observed['build_outcome'] == 'unknown'
            samples = [json.loads(line) for line in (directory / 'observer/samples.jsonl').read_text().splitlines()]
            assert len(samples) == observed['samples'] > 0 and observed['phases']
            observers += 1
    cleanups = list(folder.rglob('cleanup.json'))
    assert len(cleanups) == 4 and all(a.read(p) == {'status': 'complete', 'errors': []} for p in cleanups)
    return dict(directory=str(folder.relative_to(ROOT)), builds=16, checks=20, verified_observers=observers, cleaned_instances=4,
                tooling_archive=str(archive_path.relative_to(ROOT)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--formal', type=Path)
    mode.add_argument('--checkpoint', action='store_true', help='verify available work, never mark performance accepted')
    parser.add_argument('--aa', type=Path, action='append', default=[],
                        help='include a completed A/A screen in a checkpoint, including a failed screen; repeatable')
    parser.add_argument('--normal', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.aa and not args.checkpoint:
        parser.error('--aa is only for --checkpoint; a formal audit reads its own gate')
    args.normal, args.output = args.normal.resolve(), args.output.resolve()
    assert not args.output.exists(), 'never overwrite a completed audit'
    screens = []
    for folder in args.aa:
        assert a.read(folder / 'protocol.json')['mode'] == 'aa', 'checkpoint screens must be complete A/A runs'
        screens.append(audit_run(folder))
    formal = gate = None
    if args.formal:
        formal = audit_run(args.formal)
        protocol = a.read(args.formal / 'protocol.json')
        assert protocol['mode'] == 'formal'
        gate_path = Path(protocol['gate_directory'])
        gate = audit_run(gate_path)
        assert protocol['gate_sha256'] == a.sha(gate_path / 'summary.json')
        assert formal['analysis']['all_supported'] and gate['analysis']['all_supported']
        assert protocol['sources'] == a.read(gate_path / 'protocol.json')['sources']
        for name, digest in protocol['sources'].items():
            assert a.sha(Path(a.__file__).parent / name) == digest
    normal = audit_normal(args.normal)
    old_path = ROOT / 'dev/snapshots/20260910-default-off-triage/audit.json'
    old = a.read(old_path)
    intentional = []
    for name, digest in old['sha256'].items():
        current = a.sha(ROOT / name)
        if current != digest:
            assert name in DOCS, 'unexpected mutation of previous frozen evidence: ' + name
            intentional.append(dict(path=name, previous=digest, current=current))
    diff = subprocess.check_output(['git', '-C', str(ROOT / 'pgvector'), 'diff', 'HEAD', '--binary'])
    assert hashlib.sha256(diff).hexdigest() == '99da7d1050501be3d8060989511f26c39f0571e0a14c1d09a809c4a1fbf2bcc2'
    build = a.read(a.SNAPSHOT / 'build-manifest.json')
    for name, digest in build['candidate_changes'].items():
        assert a.sha(ROOT / 'pgvector' / name) == digest
    assert not subprocess.check_output(['docker', 'ps', '-aq', '--filter', 'label=hnsw.acceptance.run']).strip()
    assert not subprocess.check_output(['docker', 'volume', 'ls', '-q', '--filter', 'label=hnsw.acceptance.run']).strip()
    tests = []
    for executable in (sys.executable, '/usr/bin/python3'):
        command = [executable, '-m', 'unittest', 'discover', '-s', 'experiments/hnsw_build', '-p', 'test_*.py', '-q']
        p = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=60)
        assert p.returncode == 0, p.stderr
        tests.append(dict(command=command, returncode=p.returncode, stdout=p.stdout, stderr=p.stderr))
    files = [ROOT / n for n in DOCS] + list((ROOT / 'dev/overhead').glob('*'))
    files += [ROOT / 'docs/2026-09-11-overhead-acceptance.md']
    files += list(Path(a.__file__).parent.glob('*acceptance*.py'))
    for directory in [a.SNAPSHOT, *run.RESULTS_ROOT.glob('*-bounded-acceptance-*')]:
        files += [p for p in directory.rglob('*') if p.is_file()]
    value = dict(status='performance_pending' if args.checkpoint else 'passed', audited_at_utc=datetime.now(timezone.utc).isoformat(),
        scope='local controlled total-overhead acceptance; not universal or production SLA',
        formal=formal, gate=gate, aa_screens=screens, normal=normal, tests=tests,
        previous_audit_sha256=a.sha(old_path), previous_files=len(old['sha256']), intentional_document_updates=intentional,
        candidate_tracked_diff_sha256=hashlib.sha256(diff).hexdigest(), local_fixture_resources_absent=True,
        sha256={str(p.relative_to(ROOT)): a.sha(p) for p in sorted(set(files)) if p.is_file() and p != args.output})
    a.dump(args.output, value)
    print(json.dumps({'status': value['status'], 'files': len(value['sha256']), 'audit': str(args.output)}))


if __name__ == '__main__':
    main()
