#!/usr/bin/env python3
"""Build isolated workload-counter images; never change the candidate checkout."""
import argparse
import hashlib
import io
import json
import shutil
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import instrument

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PRIOR = ROOT / 'dev/snapshots/20260911-overhead-acceptance/build-manifest.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(args):
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    prior = json.loads(PRIOR.read_text())
    repository = ROOT / 'pgvector'
    assert prior['status'] == 'passed'
    assert command(['git', '-C', str(repository), 'rev-parse', 'HEAD']) == prior['baseline_commit']
    diff = subprocess.check_output(['git', '-C', str(repository), 'diff', 'HEAD', '--binary'])
    assert hashlib.sha256(diff).hexdigest() == prior['candidate_tracked_diff_sha256']
    assert all(sha(repository / n) == h for n, h in prior['candidate_changes'].items())
    for tag, digest in prior['bases'].items():
        assert command(['docker', 'image', 'inspect', '--format', '{{.Id}}',
                        'opentenbase-pg18-pgvector:' + tag]) == digest
    context = Path(tempfile.mkdtemp(prefix='hnsw-mechanism-build-'))
    archive = subprocess.check_output(['git', '-C', str(repository), 'archive', '--format=tar', 'HEAD'])
    assert hashlib.sha256(archive).hexdigest() == prior['baseline_archive_sha256']
    result = dict(schema=1, test_only=True, status='building',
        started_at_utc=datetime.now(timezone.utc).isoformat(), build_context=str(context),
        prior_manifest_sha256=sha(PRIOR), baseline_commit=prior['baseline_commit'],
        candidate_changes=prior['candidate_changes'], bases=prior['bases'],
        baseline_archive_sha256=prior['baseline_archive_sha256'],
        candidate_tracked_diff_sha256=prior['candidate_tracked_diff_sha256'],
        inputs={p.name: sha(p) for p in (Path(__file__), HERE/'instrument.py', HERE/'compile.sh', HERE/'Dockerfile')},
        sources={}, images={})
    for variant in ('baseline', 'candidate'):
        source_dir = context / variant
        source_dir.mkdir()
        with tarfile.open(fileobj=io.BytesIO(archive)) as source:
            source.extractall(source_dir, filter='data')
        if variant == 'candidate':
            for name in prior['candidate_changes']:
                shutil.copyfile(repository/name, source_dir/name)
        before = {str(p.relative_to(source_dir)): p.read_bytes() for p in (source_dir/'src').glob('*') if p.is_file()}
        instrument.instrument(source_dir)
        import difflib
        patch = ''
        for name, content in before.items():
            after = (source_dir/name).read_bytes()
            if content != after:
                patch += ''.join(difflib.unified_diff(content.decode().splitlines(True), after.decode().splitlines(True),
                    fromfile=f'a/{name}', tofile=f'b/{name}'))
        (output/f'{variant}-instrumentation.patch').write_text(patch)
        result['sources'][variant] = {str(p.relative_to(source_dir)): sha(p)
            for p in sorted((source_dir/'src').glob('*')) if p.suffix in ('.c', '.h')}
    for name in ('Dockerfile', 'compile.sh'):
        shutil.copyfile(HERE/name, context/name)
    with tarfile.open(output/'instrumented-source.tar.gz', 'x:gz') as target:
        for variant in ('baseline', 'candidate'):
            target.add(context/variant, arcname=variant)
    (output/'build-start.json').write_text(json.dumps(result, indent=2)+'\n')
    for variant in ('baseline', 'candidate'):
        tag = f'opentenbase-pg18-pgvector:mechanism-{output.name}-{variant}-arm64'
        with (output/f'build-{variant}.log').open('w') as stream:
            process = subprocess.run(['docker', 'build', '--pull=false', '--network=none', '--progress=plain',
                '--build-arg', 'VARIANT='+variant, '-t', tag, str(context)], cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
        if process.returncode:
            raise RuntimeError('isolated counter image failed; inspect saved build log')
        digest = command(['docker', 'image', 'inspect', '--format', '{{.Id}}', tag])
        identity = command(['docker', 'run', '--rm', '--network', 'none', '--read-only', '--entrypoint', '/bin/cat',
                            digest, '/opt/hnsw-acceptance-identity.txt'])+'\n'
        (output/f'identity-{variant}.txt').write_text(identity)
        assert all(f'{h}  {n}' in identity for n,h in result['sources'][variant].items())
        parent = json.loads(command(['docker','image','inspect',prior['bases']['timing-v1-arm64']]))[0]
        built = json.loads(command(['docker','image','inspect',digest]))[0]
        assert built['RootFS']['Layers'][:len(parent['RootFS']['Layers'])] == parent['RootFS']['Layers']
        result['images'][variant] = dict(tag=tag, id=digest, identity_sha256=hashlib.sha256(identity.encode()).hexdigest())
        print(variant, digest, flush=True)
    assert all(sha(repository/n)==h for n,h in prior['candidate_changes'].items())
    for tag, digest in prior['bases'].items():
        assert command(['docker','image','inspect','--format','{{.Id}}','opentenbase-pg18-pgvector:'+tag]) == digest
    assert result['inputs'] == {p.name:sha(p) for p in (Path(__file__),HERE/'instrument.py',HERE/'compile.sh',HERE/'Dockerfile')}
    result.update(status='passed', finished_at_utc=datetime.now(timezone.utc).isoformat())
    (output/'build-manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    print(output/'build-manifest.json', flush=True)


if __name__ == '__main__':
    main()
