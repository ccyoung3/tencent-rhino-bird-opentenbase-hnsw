#!/usr/bin/env python3
"""Post-completion descriptive temporal checks; standard library only.

Recompute from the identified immutable summary. No significance test, causal
claim, acceptance rule, exclusion, new measurement, or independence proof.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics

EXPECTED_SUMMARY_SHA256 = 'b7f221d7b8bbfa872f3b842f2ff267809bc4f1fd896813fac5bc94a2b3ddb1d3'
SCENES = ((0, False), (0, True), (2, False), (2, True))
LABELS = ('baseline', 'off', 'on', 'observed')
PANELS = 24


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def pearson(x, y):
    require(len(x) == len(y) and len(x) >= 2, 'paired observations required')
    mx, my = statistics.mean(x), statistics.mean(y)
    denominator = math.sqrt(sum((v - mx) ** 2 for v in x) * sum((v - my) ** 2 for v in y))
    if not denominator:
        return None  # Correlation of a constant sequence is undefined, not zero.
    return sum((i - mx) * (j - my) for i, j in zip(x, y)) / denominator


def calculate(summary):
    require(summary.get('status') == 'completed', 'descriptive checks require a complete run')
    rows = summary['rows']
    require(len(rows) == 768 and len(summary['warmups']) == 384, 'incomplete fixed run')
    expected = {(p, w, s, c, r) for p in range(PANELS) for w, s in SCENES for c in LABELS for r in (0, 1)}
    keyed = {(r['panel'], r['workers'], r['spill'], r['condition'], r['repeat']): r for r in rows}
    require(len(keyed) == len(rows) and set(keyed) == expected, 'missing or duplicate measured event')
    require(all(type(r['command_seconds']) in (int, float) and math.isfinite(r['command_seconds'])
                and r['command_seconds'] > 0 for r in rows), 'invalid command time')
    first_starts = [min(r['started_epoch'] for r in rows if r['panel'] == p) for p in range(PANELS)]
    require(all(x < y for x, y in zip(first_starts, first_starts[1:])), 'panel numbers are not time ordered')
    groups = []
    for workers, spill in SCENES:
        for condition in LABELS[1:]:
            ratios = []
            for panel in range(PANELS):
                first = keyed[panel, workers, spill, condition, 0]['command_seconds'] / keyed[panel, workers, spill, 'baseline', 0]['command_seconds']
                second = keyed[panel, workers, spill, condition, 1]['command_seconds'] / keyed[panel, workers, spill, 'baseline', 1]['command_seconds']
                ratios.append(math.sqrt(first * second))
            log_ratios = list(map(math.log, ratios))
            groups.append(dict(workers=workers, spill=spill, condition=condition, reference='baseline',
                panels=24, measurements_per_condition_per_panel=2,
                lag1_log_ratio_pearson_correlation=pearson(log_ratios[:-1], log_ratios[1:]),
                lag1_paired_points=23,
                panel_number_log_ratio_pearson_correlation=pearson(list(range(24)), log_ratios),
                first12_panel_ids=list(range(12)), last12_panel_ids=list(range(12, 24)),
                first12_median_change_percent=100 * (statistics.median(ratios[:12]) - 1),
                last12_median_change_percent=100 * (statistics.median(ratios[12:]) - 1)))
    return groups


def main():
    folder = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--summary', type=Path, default=folder / 'summary.json')
    parser.add_argument('--output', type=Path, default=folder / 'descriptive-diagnostics.json')
    args = parser.parse_args()
    require(not args.output.exists(), 'refusing to overwrite existing diagnostic evidence')
    actual_sha = sha(args.summary)
    require(actual_sha == EXPECTED_SUMMARY_SHA256, 'input summary SHA differs from this completed run')
    summary = json.loads(args.summary.read_text())
    value = dict(schema=1, kind='post_completion_descriptive_temporal_checks',
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        summary_file=args.summary.name, summary_sha256=actual_sha,
        script_file=Path(__file__).name, script_sha256=sha(Path(__file__)),
        completed_run_finished_at_utc=summary['finished_at_utc'],
        formal_measurement_count=768, warmup_count=384, group_count=12,
        statistical_unit='one within-panel two-run geometric-mean ratio; 24 units per group',
        panel_order='zero-based panel number; first measured start times independently verified as increasing',
        log_base='natural', correlation='Pearson product-moment sample correlation; null if variance is zero',
        half_summary='median of the 12 original ratios, expressed as 100*(median-1); no samples removed',
        status_scope='description only; no pass/fail, significance, causality, or independence conclusion',
        safeguards=dict(primary_analysis_modified=False,acceptance_rules_modified=False,
                        samples_deleted=False,samples_added=False,significance_tests_performed=False,
                        causal_attribution_made=False,independence_proven=False),
        limitations=[
            'These checks were specified and calculated after the complete formal run; they are descriptive.',
            'Correlations and half-run summaries do not identify a causal mechanism or prove temporal independence.',
            'The 12 groups share the same host and paired baseline runs; these diagnostics are not independent experiments.',
            'No p-values, confidence intervals, diagnostic cutoffs, exclusions, or adjusted primary verdicts are introduced.',
            'Primary conclusions remain those of the prospectively fixed protocol and independent audit.'
        ], groups=calculate(summary))
    require(sha(args.summary) == actual_sha, 'input summary changed during read-only calculation')
    with args.output.open('x') as stream:
        stream.write(json.dumps(value, indent=2) + '\n')
    print(json.dumps(dict(output=str(args.output),groups=len(value['groups']),summary_sha256=actual_sha,
                          scope=value['status_scope'])))


if __name__ == '__main__':
    main()
