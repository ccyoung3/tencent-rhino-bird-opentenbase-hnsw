#!/usr/bin/env python3
"""Exploratory, post-completion variance decomposition; no inference or new workload."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import statistics

ROOT = Path(__file__).resolve().parents[3]
RUN = ROOT / 'experiments/hnsw_build/results/20260912T174623Z-bounded-crossover-formal'
EXPECTED_SHA = 'b7f221d7b8bbfa872f3b842f2ff267809bc4f1fd896813fac5bc94a2b3ddb1d3'
CONDITIONS = ('baseline', 'off', 'on', 'observed')


def check(test, message):
    if not test:
        raise ValueError(message)


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def corr(x, y):
    ax, ay = statistics.mean(x), statistics.mean(y)
    den = math.sqrt(sum((v-ax)**2 for v in x) * sum((v-ay)**2 for v in y))
    return sum((a-ax)*(b-ay) for a,b in zip(x,y))/den if den else None


def distribution(values):
    return dict(n=len(values), minimum=min(values), median=statistics.median(values), maximum=max(values))


def counters(text):
    sections = defaultdict(list)
    current = None
    for line in text.splitlines():
        if line.startswith('FILE:'):
            current = line[5:]
        elif current:
            sections[current].append(line)
    cpu = dict(line.split() for line in sections['cpu.stat'] if line)
    io = defaultdict(int)
    for line in sections['io.stat']:
        for part in line.split()[1:]:
            key, value = part.split('=')
            io[key] += int(value)
    return dict(cpu_seconds=int(cpu['usage_usec'])/1e6, user_seconds=int(cpu['user_usec'])/1e6,
                system_seconds=int(cpu['system_usec'])/1e6, read_bytes=io['rbytes'], write_bytes=io['wbytes'])


def calculate():
    check(sha(RUN/'summary.json') == EXPECTED_SHA, 'input summary identity changed')
    summary = json.loads((RUN/'summary.json').read_text())
    check(summary['status'] == 'completed' and len(summary['rows']) == 768
          and len(summary['warmups']) == 384, 'complete fixed experiment required')
    records, hashes = [], {}
    for category in ('rows','warmups'):
        for row in summary[category]:
            record = dict(row, category=category)
            before, after = (counters(row[side]['cgroup']) for side in ('resources_before','resources_after'))
            record.update({key:after[key]-before[key] for key in before})
            logpath = RUN/row['source']/'build.stderr.txt'
            hashes[str(logpath.relative_to(RUN))] = sha(logpath)
            log = logpath.read_text()
            spill = re.search(r'after (\d+) tuples',log)
            record['spill_after_tuples'] = int(spill[1]) if spill else None
            counts = [int(v) for v in re.findall(r'(?:worker|leader) processed (\d+) tuples',log)]
            if row['workers'] == 2:
                check(len(counts) == 3 and sum(counts) == (30000 if row['spill'] else 100000), 'worker count mismatch')
                record['worker_tuple_imbalance'] = max(counts)-min(counts)
            else:
                record['worker_tuple_imbalance'] = 0
            check(row['spill'] == (spill is not None), 'spill log mismatch')
            records.append(record)
    formal = [r for r in records if r['category']=='rows']
    keyed = {(r['panel'],r['workers'],r['spill'],r['condition'],r['repeat']):r for r in formal}
    check(len(keyed)==768, 'duplicate formal event')
    pairs, groups, phases, workloads = [], [], [], []
    for workers in (0,2):
        for spill in (False,True):
            for condition in CONDITIONS:
                current = []
                for panel in range(24):
                    a,b = (keyed[panel,workers,spill,condition,repeat] for repeat in (0,1))
                    item = dict(panel=panel,workers=workers,spill=spill,condition=condition,
                        first_source=a['source'],second_source=b['source'],
                        first_seconds=a['command_seconds'],second_seconds=b['command_seconds'],
                        first_cpu_seconds=a['cpu_seconds'],second_cpu_seconds=b['cpu_seconds'],
                        time_ratio=b['command_seconds']/a['command_seconds'],
                        cpu_ratio=b['cpu_seconds']/a['cpu_seconds'],
                        first_index_bytes=a['index_bytes'],second_index_bytes=b['index_bytes'],
                        index_bytes_delta=b['index_bytes']-a['index_bytes'],
                        first_position=a['position'],second_position=b['position'],
                        prior_idle_seconds=b['started_epoch']-(a['started_epoch']+a['civil_wall_seconds']),
                        worker_imbalance_delta=b['worker_tuple_imbalance']-a['worker_tuple_imbalance'],
                        host_load_delta=b['resources_before']['host_load_average'][0]-a['resources_before']['host_load_average'][0])
                    current.append(item)
                    pairs.append(item)
                sub=[r for r in formal if (r['workers'],r['spill'],r['condition'])==(workers,spill,condition)]
                tr=[math.log(p['time_ratio']) for p in current]
                groups.append(dict(workers=workers,spill=spill,condition=condition,pairs=24,
                    command_seconds=distribution([r['command_seconds'] for r in sub]),
                    cpu_over_command=distribution([r['cpu_seconds']/r['command_seconds'] for r in sub]),
                    repeat_change_percent=distribution([100*(p['time_ratio']-1) for p in current]),
                    absolute_repeat_change_percent=distribution([100*abs(p['time_ratio']-1) for p in current]),
                    log_time_cpu_repeat_correlation=corr(tr,[math.log(p['cpu_ratio']) for p in current]),
                    log_time_repeat_index_delta_correlation=corr(tr,[p['index_bytes_delta'] for p in current]),
                    log_time_repeat_worker_imbalance_delta_correlation=corr(tr,[p['worker_imbalance_delta'] for p in current]),
                    log_time_repeat_idle_gap_correlation=corr(tr,[p['prior_idle_seconds'] for p in current]),
                    log_time_repeat_host_load_delta_correlation=corr(tr,[p['host_load_delta'] for p in current]),
                    identical_size_pairs=sum(p['index_bytes_delta']==0 for p in current),
                    index_bytes=distribution([r['index_bytes'] for r in sub]),
                    io_read_bytes=distribution([r['read_bytes'] for r in sub]),
                    io_write_bytes=distribution([r['write_bytes'] for r in sub]),
                    zero_read_byte_builds=sum(r['read_bytes']==0 for r in sub)))
                if workers==2 and condition in ('on','observed'):
                    shares=defaultdict(list)
                    for r in sub:
                        timing=r['internal_timing']['records'][0]
                        for name,micros in timing['durations_us'].items():
                            if micros is not None:shares[name].append(100*micros/timing['total_us'])
                    phases.append(dict(workers=workers,spill=spill,condition=condition,formal_builds=len(sub),
                        phase_percent_of_internal_total={name:distribution(v) for name,v in shares.items()},
                        sql_minus_internal_seconds=distribution([r['command_seconds']-r['internal_timing']['records'][0]['total_us']/1e6 for r in sub])))
    for category in ('rows','warmups'):
        for workers in (0,2):
            for spill in (False,True):
                for condition in CONDITIONS:
                    sub=[r for r in records if (r['category'],r['workers'],r['spill'],r['condition'])==(category,workers,spill,condition)]
                    workloads.append(dict(category=category,workers=workers,spill=spill,condition=condition,
                        builds=len(sub),spill_after_tuples_counts=dict(Counter(str(r['spill_after_tuples']) for r in sub)),
                        worker_tuple_imbalance=distribution([r['worker_tuple_imbalance'] for r in sub]) if workers==2 else None))
    position=[]
    for spill in (False,True):
        for slot in range(4):
            sub=[p for p in pairs if p['workers']==2 and p['spill']==spill and p['first_position']==4+slot]
            position.append(dict(spill=spill,first_pass_slot=slot,intervening_builds_between_repeats=6-2*slot,
                pairs=len(sub),repeat_change_percent=distribution([100*(p['time_ratio']-1) for p in sub]),
                log_time_cpu_repeat_correlation=corr([math.log(p['time_ratio']) for p in sub],[math.log(p['cpu_ratio']) for p in sub])))
    examples=[]
    for spill in (False,True):
        sub=[p for p in pairs if p['workers']==2 and p['spill']==spill]
        examples.extend(sorted(sub,key=lambda p:abs(math.log(p['time_ratio'])),reverse=True)[:3])
    check(sha(RUN/'summary.json') == EXPECTED_SHA, 'input changed during analysis')
    return dict(schema=1,classification='post_completion_exploratory_not_confirmatory',
        created_at_utc=datetime.now(timezone.utc).isoformat(),source_directory=str(RUN.relative_to(ROOT)),
        source_summary_sha256=EXPECTED_SHA,script_sha256=sha(Path(__file__)),
        inputs=dict(formal_builds=768,warmups=384,parallel_formal_builds=384,parallel_warmups=192,
                    complete_logs_read=len(hashes),within_panel_repeat_pairs=384),
        choices=[
            'All 1152 completed records and their full stderr logs are read; no prior or interrupted run is read.',
            'All 16 worker/spill/condition groups are reported. Parallel groups are the focus; serial groups are context.',
            'Within-panel repeat contrasts are second/first, not candidate/baseline overhead estimates.',
            'Warmups are included only in workload/log coverage tables, never pooled into formal repeat contrasts.',
            'Positions are pooled across the four balanced conditions, with the pooling made explicit.',
            'The six displayed examples are mechanically the largest absolute log repeat contrasts, three per parallel scene; all 384 pairs remain included.'
        ], limitations=[
            'Exploratory correlations have no p-values or causal interpretation; repeated rows and groups are dependent.',
            'CPU counters cover the whole private container between boundary probes, not precisely only the CREATE INDEX statement.',
            'CPU-time changes cannot distinguish different instruction/work counts from different execution speeds.',
            'Identical index byte size does not establish identical graph topology; different sizes do not establish timing causality.',
            'I/O byte counters are neither physical-device latency nor continuous peak-pressure measurements.',
            'Internal elapsed phase times localize intervals; they are not CPU profiles.',
            'Nothing changes the primary 9-supported/3-not-established verdict, its threshold, or its samples.'
        ],groups=groups,parallel_timing_phases=phases,workload_logs=workloads,
        parallel_position_bins=position,extreme_examples=examples,all_within_panel_repeat_pairs=pairs,
        stderr_sha256=hashes)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path(__file__).with_name('parallel-variance.json'))
    args=parser.parse_args()
    check(not args.output.exists(),'refusing to overwrite exploratory evidence')
    value=calculate()
    with args.output.open('x') as stream:stream.write(json.dumps(value,indent=2)+'\n')
    print(json.dumps(dict(output=str(args.output),groups=len(value['groups']),logs=value['inputs']['complete_logs_read'],classification=value['classification'])))


if __name__=='__main__':
    main()
