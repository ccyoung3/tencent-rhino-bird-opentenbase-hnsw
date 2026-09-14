#!/usr/bin/env python3
"""Fixed-budget mirrored crossover for total HNSW diagnostic cost.

This is a new prospective protocol. It does not change or pass the old A/A gate.
Two measurements within a panel form ONE replicate, never two independent ones.
"""
import argparse
import hashlib
import itertools
import json
import math
import random
import statistics
import tarfile
import traceback
from datetime import datetime, timezone
from pathlib import Path

import acceptance as a
import acceptance_stack as stack
import observe
import run
import timing

PANELS = 24
SEED = 20260912
CONFIDENCE = 1 - .05 / 12


def schedule():
    rng = random.Random(SEED)
    orders = {}
    for scene in a.SCENES:
        pool = list(itertools.permutations(a.CONDITIONS))
        rng.shuffle(pool)
        orders[scene] = pool
    scenes = list(itertools.permutations(a.SCENES))
    slots = list(itertools.permutations(a.CONDITIONS))
    rng.shuffle(scenes)
    rng.shuffle(slots)
    return [dict(panel=p, slots=list(slots[p]), scenes=[dict(workers=w, spill=s,
        warmup_order=list(orders[w, s][p]),
        order=list(orders[w, s][p]) + list(reversed(orders[w, s][p])))
        for w, s in scenes[p]]) for p in range(PANELS)]


def summarize(rows, panels=PANELS):
    expected = {(p, w, s, c, repeat) for p in range(panels) for w, s in a.SCENES
                for c in a.CONDITIONS for repeat in (0, 1)}
    keyed = {(r['panel'], r['workers'], r['spill'], r['condition'], r['repeat']): r for r in rows}
    if len(rows) != len(expected) or set(keyed) != expected:
        raise ValueError('missing or duplicate crossover measurements')
    if any(not math.isfinite(r['command_seconds']) or r['command_seconds'] <= 0 for r in rows):
        raise ValueError('positive finite times required')
    groups = []
    for w, s in a.SCENES:
        for label in a.CONDITIONS[1:]:
            ratios = []
            coverage = 0
            for p in range(panels):
                # Equal center in execution-position space reduces linear log-
                # drift; it does NOT guarantee equal wall-clock centers or remove
                # arbitrary drift. Both actual start times remain in raw data.
                contrast = sum(math.log(keyed[p,w,s,label,r]['command_seconds']) -
                               math.log(keyed[p,w,s,'baseline',r]['command_seconds']) for r in (0,1))/2
                ratios.append(math.exp(contrast))
                coverage += sum(bool(keyed[p,w,s,label,r].get('observer', {}).get('observation', {}).get('phases'))
                                and keyed[p,w,s,label,r].get('observer', {}).get('observation', {}).get('samples', 0) > 0
                                for r in (0,1))
            upper = a.upper(ratios, CONFIDENCE)
            # A lower bound can distinguish established >5% regression from
            # insufficient precision. It is a separate one-sided family.
            inverse = a.upper([1/r for r in ratios], CONFIDENCE)
            lower = 1/inverse['ratio'] if inverse['ratio'] else None
            passing = (upper['ratio'] is not None and upper['ratio'] < 1.05
                       and not math.isclose(upper['ratio'], 1.05, rel_tol=1e-12))
            if label == 'observed':
                passing = passing and coverage == 2*panels
            groups.append(dict(workers=w, spill=s, condition=label, reference='baseline', panels=panels,
                ratios=ratios, median_change_percent=100*(statistics.median(ratios)-1), upper=upper,
                lower_ratio=lower, observed_with_progress=coverage if label == 'observed' else None,
                verdict='supported' if passing else 'regression_supported' if lower and lower > 1.05
                        else 'not_established'))
    return dict(estimand='population median of paired within-panel two-run geometric-mean time ratios',
                groups=groups, all_supported=all(g['verdict'] == 'supported' for g in groups))


def source_paths():
    return [Path(m.__file__) for m in (a, stack, observe, run, timing)] + [Path(__file__)]


def render(result):
    lines = ['# 整套诊断镜像顺序对照', '', '运行状态：' + result['status'], '',
        '| worker | spill | 条件 / 原版 | 面板比值中位变化 | 联合单侧上界变化 | 判断 |',
        '|---:|---|---|---:|---:|---|']
    for g in result.get('analysis', {}).get('groups', []):
        bound = g['upper']['ratio']
        shown = f"{100*(bound-1):+.2f}%" if bound is not None else '无有限上界'
        lines.append(f"| {g['workers']} | {g['spill']} | {g['condition']} | {g['median_change_percent']:+.2f}% | {shown} | {g['verdict']} |")
    lines += ['', '- 每面板每条件两次测量先取几何均值，再与原版配对；24面板才是24个统计单位。',
        '- 12项单侧上界采用精确二项分布顺序统计量与Bonferroni；参考线仍为5%。',
        '- 结论以独立、可比较的面板为前提；时序相关和不规则漂移仍是限制。',
        '- 正逆序只平衡执行位置，不保证墙钟中心完全相同；不承诺消除所有系统噪声。',
        '- 对照为seed42受控构建；常规构建的功能验证另有记录。不是生产SLA或最坏单次开销保证。',
        '- 旧A/A结果保持未通过；本协议不使用其作为性能准入条件，也不宣称旧协议通过。',
        '- 所有样本保留；不按结果追加面板或删除异常值。未建立支持不等于已证明C回归。']
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('smoke', 'formal'))
    args = parser.parse_args()
    build = a.read(a.SNAPSHOT / 'build-manifest.json')
    if build['status'] != 'passed':
        raise RuntimeError('common source-attested build required')
    for name, digest in build['candidate_changes'].items():
        if a.sha(run.PROJECT_ROOT / 'pgvector' / name) != digest:
            raise RuntimeError('candidate no longer matches frozen images')
    ordered = schedule()[:1] if args.mode == 'smoke' else schedule()
    images = {label: build['images'][('baseline' if label == 'baseline' else 'candidate') + '-seed42']['id']
              for label in a.CONDITIONS}
    output = run.RESULTS_ROOT / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-bounded-crossover-' + args.mode)
    output.mkdir()
    paths = source_paths()
    protocol = dict(schema=1, mode=args.mode, panels=len(ordered), schedule=ordered, images=images,
        large_rows=100000, small_rows=30000, dimensions=32, m=16, ef_construction=64, affinity='0-9',
        warmups_per_scene_condition=1, measurements_per_scene_condition=2,
        formal_count=len(ordered)*32, warmup_count=len(ordered)*16,
        primary_estimand='population median of paired within-panel two-run geometric-mean time ratios',
        primary_upper_confidence=CONFIDENCE, comparisons=12, strict_upper_ratio_limit=1.05,
        no_aa_gate=True, old_protocol_status='unchanged; failed screens remain failed',
        no_optional_stopping=True, no_effect_based_restarts=True,
        acceptance='all 12 upper bounds <1.05, complete validated measurements and observer coverage',
        source_sha256={p.name: a.sha(p) for p in paths},
        common_build_manifest_sha256=a.sha(a.SNAPSHOT / 'build-manifest.json'),
        method_review_sha256=a.sha(run.PROJECT_ROOT / 'docs/2026-09-12-performance-method-review.md'),
        created_at_utc=datetime.now(timezone.utc).isoformat())
    a.dump(output / 'protocol.json', protocol)
    (output / 'method-review-at-start.md').write_bytes(
        (run.PROJECT_ROOT / 'docs/2026-09-12-performance-method-review.md').read_bytes())
    with tarfile.open(output / 'tooling-at-start.tar.gz', 'x:gz') as archive:
        for path in paths:
            archive.add(path, arcname=path.name)
    result = dict(status='running', rows=[], warmups=[])
    print(output, flush=True)
    try:
        with stack.keep_awake():
            if stack.power_source() != 'AC':
                raise RuntimeError('AC power required')
            for step in ordered:
                p = step['panel']
                selected = {label: images[label] for label in step['slots']}
                with stack.panel(output / f'p{p:02d}', selected, large_rows=100000,
                                 small_rows=30000, affinity='0-9') as replicas:
                    for scene in step['scenes']:
                        w, s = scene['workers'], scene['spill']
                        events = [(label, True, 0) for label in scene['warmup_order']]
                        events += [(label, False, int(pos >= 4)) for pos, label in enumerate(scene['order'])]
                        for pos, (label, warmup, repeat) in enumerate(events):
                            path = replicas[label].folder / f"w{w}-s{int(s)}-{'warmup' if warmup else 'formal'}-{repeat}"
                            item = a.measure(replicas[label], path, label, w, s, warmup)
                            row = dict(item, panel=p, repeat=repeat, position=pos,
                                       source=str(path.relative_to(output)))
                            result['warmups' if warmup else 'rows'].append(row)
                            a.dump(output / 'summary.json', result)
                        print(f'Panel {p+1}/{len(ordered)}, workers={w}, spill={s} complete', flush=True)
                if {path.name: a.sha(path) for path in paths} != protocol['source_sha256']:
                    raise RuntimeError('measurement source changed during execution')
            result['status'] = 'completed'
            if args.mode == 'formal':
                result['analysis'] = summarize(result['rows'])
    except (Exception, KeyboardInterrupt) as error:
        result['status'] = 'failed'
        result['error'] = type(error).__name__ + ':' + (getattr(error, 'sqlstate', None) or '')
        result['error_locations'] = [dict(file=f.filename.rsplit('/',1)[-1], line=f.lineno)
                                     for f in traceback.extract_tb(error.__traceback__)]
    finally:
        result['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
        a.dump(output / 'summary.json', result)
        (output / 'report.md').write_text(render(result))
    print(result['status'], flush=True)
    return 0 if result['status'] == 'completed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
