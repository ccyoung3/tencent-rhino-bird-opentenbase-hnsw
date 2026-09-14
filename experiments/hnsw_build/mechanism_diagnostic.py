#!/usr/bin/env python3
"""Bounded exploratory HNSW work/CPU diagnosis, never a performance acceptance."""
import argparse
import itertools
import json
import random
import re
import tarfile
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import acceptance as a
import acceptance_stack as stack
import run
import timing

CONDITIONS = ('baseline', 'off', 'on')
SCENES = {
    'no-spill': dict(table='large', rows=100000, memory='256MB', spill='none'),
    'immediate-spill': dict(table='small', rows=30000, memory='4MB', spill='zero'),
    'partial-spill': dict(table='small', rows=30000, memory='8MB', spill='partial'),
}
PREFIX = 'HNSW_MECHANISM '


def parse_records(text, rows, index_oid):
    def unique_object(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError('duplicate counter field')
            value[key] = item
        return value
    def reject_constant(value):
        raise ValueError('nonfinite JSON counter')
    records = []
    for line in text.splitlines():
        if line.startswith('NOTICE: '+PREFIX):
            records.append(json.loads(line[len('NOTICE: '+PREFIX):], object_pairs_hook=unique_object,
                                      parse_constant=reject_constant))
    if len(records) != 3:
        raise ValueError('exactly two workers and one leader required')
    if len({r['pid'] for r in records}) != 3 or {r['worker_number'] for r in records} != {-1,0,1}:
        raise ValueError('unique process identities required')
    keys = ('callbacks_seen', 'successful_inserts', 'distance_calls', 'elements_initialized',
            'user_cpu_us', 'system_cpu_us', 'elapsed_us')
    for r in records:
        if (type(r['schema']) is not int or r['schema'] != 1 or r['test_only'] is not True
                or r['scope'] != 'scan_and_insert' or r['mode'] != 'native'):
            raise ValueError('unsupported counter schema or scope')
        if (any(type(r[k]) is not int for k in ('pid','worker_number','index_oid'))
                or r['pid'] <= 0 or r['index_oid'] <= 0):
            raise ValueError('valid process and index identifiers required')
        if r['role'] != ('leader' if r['worker_number'] == -1 else 'worker') or r['index_oid'] != index_oid:
            raise ValueError('wrong role or index')
        if any(type(r[k]) is not int or r[k] < 0 for k in keys) or r['elapsed_us'] == 0:
            raise ValueError('nonnegative integer counters and positive elapsed time required')
        hist = r['level_hist']
        if len(hist) != 64 or any(type(v) is not int or v < 0 for v in hist):
            raise ValueError('64 nonnegative integer histogram entries required')
        if sum(hist) != r['elements_initialized']:
            raise ValueError('histogram does not cover initialized elements')
        if not 0 < r['successful_inserts'] == r['callbacks_seen'] == r['elements_initialized']:
            raise ValueError('all nonnull unique fixture tuples must be processed')
        if r['distance_calls'] <= 0 or r['user_cpu_us'] + r['system_cpu_us'] <= 0:
            raise ValueError('positive scan workload and CPU required')
    if sum(r['callbacks_seen'] for r in records) != rows:
        raise ValueError('participants do not cover the complete heap')
    totals = {k: sum(r[k] for r in records) for k in keys if k != 'elapsed_us'}
    totals['cpu_seconds'] = (totals['user_cpu_us']+totals['system_cpu_us'])/1e6
    totals['level_hist'] = [sum(r['level_hist'][i] for r in records) for i in range(64)]
    totals['max_participant_elapsed_seconds'] = max(r['elapsed_us'] for r in records)/1e6
    return dict(scope='scan_and_insert', records=records, totals=totals)


def schedule():
    rng = random.Random(20260913)
    orders = list(itertools.permutations(CONDITIONS))
    rng.shuffle(orders)
    scenes = list(SCENES)
    rng.shuffle(scenes)
    return [dict(panel=p, slots=list(CONDITIONS if p==0 else reversed(CONDITIONS)),
        scenes=[dict(scene=s, warmup_order=list(orders[3*p+i]),
                     order=list(orders[3*p+i])+list(reversed(orders[3*p+i])))
                for i,s in enumerate(scenes if p==0 else reversed(scenes))]) for p in range(2)]


def measure(replica, output, condition, scene, warmup):
    output.mkdir()
    config = SCENES[scene]
    enabled = condition == 'on'
    conn = replica.connect()
    notices = []
    def notice(diag):
        notices.append((diag.severity_nonlocalized or 'NOTICE')+': '+(diag.message_primary or '')+
                       ('\nDETAIL: '+diag.message_detail if diag.message_detail else ''))
    item = dict(condition=condition, scene=scene, warmup=warmup, image=replica.image, config=config, workers=2)
    error = None
    try:
        conn.execute('SET client_min_messages=DEBUG1; SET min_parallel_table_scan_size=0; SET max_parallel_maintenance_workers=2')
        conn.execute("SELECT set_config('maintenance_work_mem',%s,false)", (config['memory'],))
        if condition != 'baseline':
            conn.execute("SELECT set_config('hnsw.build_timing',%s,false)", ('on' if enabled else 'off',))
        conn.execute(f"ALTER TABLE hnsw_accept.{config['table']} SET (parallel_workers=2)")
        conn.execute('DROP INDEX IF EXISTS hnsw_accept.items_hnsw; CHECKPOINT')
        item['resources_before'] = replica.counters()
        if item['resources_before']['power_source'] != 'AC':
            raise RuntimeError('AC required')
        conn.add_notice_handler(notice)
        started = time.perf_counter()
        item['started_epoch'] = time.time()
        conn.execute(f"CREATE INDEX items_hnsw ON hnsw_accept.{config['table']} USING hnsw (embedding vector_l2_ops) WITH (m=16,ef_construction=64)")
        item['command_seconds'] = time.perf_counter()-started
        item['civil_wall_seconds'] = time.time()-item['started_epoch']
        item['command_returncode'] = 0
        conn.remove_notice_handler(notice)
        item['resources_after'] = replica.counters()
        index_oid,index_bytes = conn.execute("SELECT 'hnsw_accept.items_hnsw'::regclass::oid, pg_relation_size('hnsw_accept.items_hnsw')").fetchone()
        item.update(index_oid=index_oid, index_bytes=index_bytes)
        text = '\n'.join(notices)+'\n'
        item['internal_timing'] = timing.parse_build_timing(text, requested=enabled, command_returncode=0)
        item['work'] = parse_records(text, config['rows'], index_oid)
        actual = re.search(r'using (\d+) parallel workers', text)
        if not actual or int(actual[1]) != 2:
            raise ValueError('two workers required')
        spill = re.findall(r'graph no longer fits into maintenance_work_mem after (\d+) tuples', text)
        item['spill_after_tuples'] = int(spill[0]) if len(spill)==1 else None
        valid_spill = (not spill if config['spill']=='none' else
            len(spill)==1 and (int(spill[0])==0 if config['spill']=='zero' else 0<int(spill[0])<config['rows']))
        if not valid_spill:
            raise ValueError('configured spill regime not realized')
        if item['internal_timing']['status'] != ('complete' if enabled else 'not_requested'):
            raise ValueError('timing state mismatch')
        a.validate_host(item['resources_before'],item['resources_after'],item['command_seconds'],item['civil_wall_seconds'],True)
        item['validation'] = 'passed'
    except BaseException as caught:
        error = caught
        item['validation'] = 'failed'
        item['error'] = type(caught).__name__+':'+(getattr(caught,'sqlstate',None) or '')
    finally:
        (output/'build.stderr.txt').write_text('\n'.join(notices)+'\n')
        a.dump(output/'measurement.json',item)
        conn.close()
    if error:
        raise error
    return item


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest',type=Path)
    parser.add_argument('--mode',choices=('smoke','diagnosis'),default='diagnosis')
    args = parser.parse_args()
    build = a.read(args.manifest)
    if build['status'] != 'passed' or build['test_only'] is not True:
        raise RuntimeError('source-attested instrumented images required')
    for name,digest in build['candidate_changes'].items():
        if a.sha(run.PROJECT_ROOT/'pgvector'/name) != digest:
            raise RuntimeError('candidate changed since isolated build')
    output = run.RESULTS_ROOT/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-mechanism-'+args.mode)
    output.mkdir()
    paths = [Path(m.__file__) for m in (a,stack,run,timing)]+[Path(__file__)]
    ordered = schedule()
    if args.mode=='smoke':
        ordered = ordered[:1]
        # Validate every scene/condition once. These nine warmups are not pooled.
        for scene in ordered[0]['scenes']:
            scene['order'] = []
    images = {c:build['images']['baseline' if c=='baseline' else 'candidate']['id'] for c in CONDITIONS}
    protocol = dict(schema=1, exploratory=True, mode=args.mode, created_at_utc=datetime.now(timezone.utc).isoformat(),
        schedule=ordered, images=images, scenes=SCENES, workers=2, affinity='0-9',
        formal_count=0 if args.mode=='smoke' else 36, warmup_count=9 if args.mode=='smoke' else 18,
        no_acceptance_inference=True, no_effect_based_sample_addition=True,
        scope='participant scan_and_insert counters exclude final leader flush/WAL/cleanup',
        limitation='instrumentation can change scheduling; native worker randomness and graph topology remain variable',
        sources={p.name:a.sha(p) for p in paths}, build_manifest_sha256=a.sha(args.manifest))
    a.dump(output/'protocol.json',protocol)
    (output/'build-manifest-at-start.json').write_bytes(args.manifest.read_bytes())
    method = run.PROJECT_ROOT/'docs/2026-09-13-parallel-mechanism-diagnostic.md'
    (output/'method-at-start.md').write_bytes(method.read_bytes())
    protocol['method_sha256'] = a.sha(method)
    a.dump(output/'protocol.json',protocol)
    with tarfile.open(output/'tooling-at-start.tar.gz','x:gz') as archive:
        for p in paths:
            archive.add(p,arcname=p.name)
    result = dict(status='running',rows=[],warmups=[])
    print(output,flush=True)
    try:
        with stack.keep_awake():
            if stack.power_source() != 'AC':
                raise RuntimeError('AC required')
            for step in ordered:
                selected = {c:images[c] for c in step['slots']}
                with stack.panel(output/f"p{step['panel']:02d}",selected,large_rows=100000,small_rows=30000,affinity='0-9') as replicas:
                    for replica in replicas.values():
                        expected = build['images']['baseline' if replica==replicas['baseline'] else 'candidate']['identity_sha256']
                        import hashlib
                        if hashlib.sha256(replica.identity['source_attestation'].encode()).hexdigest()!=expected:
                            raise ValueError('source attestation mismatch')
                    for scene in step['scenes']:
                        events = [(c,True,0) for c in scene['warmup_order']]
                        events += [(c,False,int(i>=3)) for i,c in enumerate(scene['order'])]
                        for position,(c,warmup,repeat) in enumerate(events):
                            path = replicas[c].folder/f"{scene['scene']}-{'warmup' if warmup else 'measure'}-{repeat}"
                            item = measure(replicas[c],path,c,scene['scene'],warmup)
                            row = dict(item,panel=step['panel'],repeat=repeat,position=position,source=str(path.relative_to(output)))
                            result['warmups' if warmup else 'rows'].append(row)
                            a.dump(output/'summary.json',result)
                        print(f"Panel {step['panel']+1}/{len(ordered)} {scene['scene']} complete",flush=True)
                if {p.name:a.sha(p) for p in paths} != protocol['sources']:
                    raise RuntimeError('measurement code changed while running')
        if len(result['rows'])!=protocol['formal_count'] or len(result['warmups'])!=protocol['warmup_count']:
            raise ValueError('incomplete fixed schedule')
        result['status']='completed'
    except (Exception,KeyboardInterrupt) as error:
        result['status']='failed'
        result['error']=type(error).__name__+':'+(getattr(error,'sqlstate',None) or '')
        result['error_locations']=[dict(file=f.filename.rsplit('/',1)[-1],line=f.lineno) for f in traceback.extract_tb(error.__traceback__)]
    finally:
        result['finished_at_utc']=datetime.now(timezone.utc).isoformat()
        a.dump(output/'summary.json',result)
    print(result['status'],flush=True)
    return 0 if result['status']=='completed' else 1


if __name__=='__main__':
    raise SystemExit(main())
