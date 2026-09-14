#!/usr/bin/env python3
"""Twelve-build exploratory bridge between plain and counter-instrumented images."""
import hashlib
import json
import math
import random
import tarfile
import traceback
from datetime import datetime, timezone
from pathlib import Path

import acceptance as a
import acceptance_stack as stack
import mechanism_diagnostic as mechanism
import run
import timing

LABELS = ('plain-baseline','counter-baseline','plain-on','counter-on')


def main():
    plain_path = a.SNAPSHOT/'build-manifest.json'
    counter_path = run.PROJECT_ROOT/'dev/snapshots/20260913-mechanism-diagnostic/build-01/build-manifest.json'
    plain, counter = a.read(plain_path), a.read(counter_path)
    assert plain['status']==counter['status']=='passed' and counter['test_only'] is True
    assert counter['prior_manifest_sha256']==a.sha(plain_path)
    for name,digest in plain['candidate_changes'].items():
        assert a.sha(run.PROJECT_ROOT/'pgvector'/name)==digest
    images, identities = {}, {}
    for label in LABELS:
        variant = 'baseline' if label.endswith('baseline') else 'candidate'
        details = plain['images'][variant+'-seed42'] if label.startswith('plain-') else counter['images'][variant]
        images[label],identities[label] = details['id'],details['identity_sha256']
    order = list(LABELS)
    random.Random(202609131).shuffle(order)
    output = run.RESULTS_ROOT/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-mechanism-bridge')
    output.mkdir()
    paths = [Path(m.__file__) for m in (a,stack,mechanism,run,timing)]+[Path(__file__)]
    method = run.PROJECT_ROOT/'docs/2026-09-13-instrumentation-bridge.md'
    protocol = dict(schema=1, exploratory=True, no_acceptance_inference=True, formal_count=8,warmup_count=4,
        created_at_utc=datetime.now(timezone.utc).isoformat(),workers=2,spill=False,rows=100000,dimensions=32,
        memory='256MB',m=16,ef_construction=64,affinity='0-9',slots=list(LABELS),
        warmup_order=order,order=order+list(reversed(order)),images=images,identity_sha256=identities,
        no_effect_based_sample_addition=True,plain_manifest_sha256=a.sha(plain_path),counter_manifest_sha256=a.sha(counter_path),
        method_sha256=a.sha(method),sources={p.name:a.sha(p) for p in paths})
    a.dump(output/'protocol.json',protocol)
    (output/'plain-manifest-at-start.json').write_bytes(plain_path.read_bytes())
    (output/'counter-manifest-at-start.json').write_bytes(counter_path.read_bytes())
    (output/'method-at-start.md').write_bytes(method.read_bytes())
    with tarfile.open(output/'tooling-at-start.tar.gz','x:gz') as archive:
        for p in paths:
            archive.add(p,arcname=p.name)
    result = dict(status='running',rows=[],warmups=[])
    print(output,flush=True)
    try:
        with stack.keep_awake():
            if stack.power_source()!='AC':
                raise RuntimeError('AC required')
            with stack.panel(output/'p00',images,large_rows=100000,small_rows=30000,affinity='0-9') as replicas:
                for label,replica in replicas.items():
                    assert hashlib.sha256(replica.identity['source_attestation'].encode()).hexdigest()==identities[label]
                events = [(label,True,0) for label in order]
                events += [(label,False,int(i>=4)) for i,label in enumerate(protocol['order'])]
                for position,(label,warmup,repeat) in enumerate(events):
                    path = replicas[label].folder/f"{'warmup' if warmup else 'measure'}-{repeat}"
                    condition = 'baseline' if label.endswith('baseline') else 'on'
                    item = a.measure(replicas[label],path,condition,2,False,warmup)
                    text = (path/'build.stderr.txt').read_text()
                    with replicas[label].connect() as conn:
                        oid = conn.execute("SELECT 'hnsw_accept.items_hnsw'::regclass::oid").fetchone()[0]
                    a.dump(path/'bridge.json',dict(index_oid=oid,instrumented=label.startswith('counter-')))
                    if label.startswith('counter-'):
                        # All three records must refer to the same actual index.
                        a.dump(path/'work.json',mechanism.parse_records(text,100000,oid))
                    elif mechanism.PREFIX in text:
                        raise ValueError('plain image emitted test instrumentation')
                    result['warmups' if warmup else 'rows'].append(dict(item,label=label,repeat=repeat,
                        position=position,source=str(path.relative_to(output))))
                    a.dump(output/'summary.json',result)
                    print(f'Validated {position+1}/12',flush=True)
        assert len(result['rows'])==8 and len(result['warmups'])==4
        assert {p.name:a.sha(p) for p in paths}==protocol['sources']
        result['status']='completed'
        ratios = []
        for condition in ('baseline','on'):
            selected = {label:[r['command_seconds'] for r in result['rows'] if r['label']==label]
                        for label in (f'plain-{condition}',f'counter-{condition}')}
            geometric = {label:math.sqrt(values[0]*values[1]) for label,values in selected.items()}
            ratios.append(dict(condition=condition,times=selected,geometric_seconds=geometric,
                instrumented_over_plain_ratio=geometric[f'counter-{condition}']/geometric[f'plain-{condition}']))
        result['description'] = dict(scope='one exploratory panel; two repeats are not independent acceptance evidence',groups=ratios)
    except (Exception,KeyboardInterrupt) as error:
        result.update(status='failed',error=type(error).__name__+':'+(getattr(error,'sqlstate',None) or ''),
            error_locations=[dict(file=f.filename.rsplit('/',1)[-1],line=f.lineno) for f in traceback.extract_tb(error.__traceback__)])
    finally:
        result['finished_at_utc']=datetime.now(timezone.utc).isoformat()
        a.dump(output/'summary.json',result)
    print(result['status'],flush=True)
    return 0 if result['status']=='completed' else 1


if __name__=='__main__':
    raise SystemExit(main())
