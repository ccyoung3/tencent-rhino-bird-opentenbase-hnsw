"""Read-only feasibility arithmetic; never launches a benchmark or passes a gate."""
from pathlib import Path
import datetime as dt
import hashlib
import json
import math

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / 'experiments/hnsw_build/results/20260912T174623Z-bounded-crossover-formal/summary.json'
EXPECTED = 'b7f221d7b8bbfa872f3b842f2ff267809bc4f1fd896813fac5bc94a2b3ddb1d3'
OUTPUT = Path(__file__).resolve().parent


def tail(n, k, p):
    return math.fsum(math.comb(n, i) * p**i * (1-p)**(n-i) for i in range(k, n+1))


def required_rank(n):
    return next(k for k in range(1, n+1) if tail(n, k, .5) <= .05/12)


def main():
    before = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    assert before == EXPECTED
    data = json.loads(SOURCE.read_text())
    groups = [g for g in data['analysis']['groups'] if g['verdict'] == 'not_established']
    assert len(groups) == 3 and required_rank(24) == 19
    observed = []
    for group in groups:
        ratios = group['ratios']
        assert len(ratios) == 24
        below = sum(r < 1.05 and not math.isclose(r, 1.05, rel_tol=1e-12) for r in ratios)
        observed.append(dict(workers=group['workers'], spill=group['spill'], condition=group['condition'],
                             below_reference=below, panels=24, empirical_probability=below/24))
    needed = [r for r in data['rows'] + data['warmups'] if r['workers'] == 2 and
              ((not r['spill'] and r['condition'] in ('baseline', 'off', 'on')) or
               (r['spill'] and r['condition'] in ('baseline', 'on')))]
    assert len(needed) == 24 * 15
    seconds_per_panel = sum(r['command_seconds'] for r in needed) / 24
    scenarios = []
    for n in (24, 48, 72, 96, 144, 192):
        rank = required_rank(n)
        powers = [tail(n, rank, g['empirical_probability']) for g in observed]
        scenarios.append(dict(panels=n, required_below_reference=rank,
            null_probability=tail(n, rank, .5), plugin_support_probabilities=powers,
            plugin_joint_lower_bound=max(0, 1-sum(1-p for p in powers)),
            sql_hours_using_old_durations=seconds_per_panel*n/3600,
            sensitivity={str(p): tail(n, rank, p) for p in (.6, .65, .7, .75, .8)}))
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == before
    result = dict(schema=1, generated_at_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
        scope='Offline planning only; no new observations, power guarantee, acceptance or execution protocol.',
        source=str(SOURCE.relative_to(ROOT)), source_sha256=before,
        analysis_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        observed=observed, scenarios=scenarios, sql_seconds_per_panel=seconds_per_panel,
        limits=[
            'Uses the old one-sided per-comparison alpha .05/12 only as a planning illustration.',
            'A new study must separately specify repeated-testing and cross-stage claims; old nine plus new three is not automatically a jointly controlled claim.',
            'Binomial calculations assume independent, comparable panels and constant P(ratio < 1.05).',
            'Empirical probabilities from only 24 panels are uncertain; plugging them in ignores estimation error and time drift.',
            'Joint lower bounds use the union bound, not independence among the three comparisons; they are conditional on assumed probabilities.',
            'SQL time extrapolates old selected observations only, excludes setup/cleanup and new monitoring, and is not a runtime bound.',
            'More repetitions do not remove systematic confounding; this analysis does not select or authorize a new sample size.',
            'The original study and its verdicts remain unchanged.'])
    lines = ['# 三项性能验证的离线可行性初算', '',
        '本页只使用旧数据做抽样设计的初算，没有运行数据库或固定算术负载，没有改变原判定。', '',
        '原24面板中，三项低于1.05的面板数依次为16、16、17；旧严格上界规则需要至少19。',
        '下面将这三个经验比例暂作未来概率，沿用旧单项α=0.05/12，计算二项分布尾概率。',
        '**这些比例只有24个面板支撑，表内概率忽略了估计不确定性及时间漂移，不是达标承诺。**', '',
        '| 新面板数 | 所需低于5%的面板数 | 无spill/off支持概率 | 无spill/on | spill/on | 三项同时支持的条件下界 | 仅SQL小时估算 |',
        '|---:|---:|---:|---:|---:|---:|---:|']
    for row in scenarios:
        probabilities = ' | '.join(f'{p:.1%}' for p in row['plugin_support_probabilities'])
        lines.append(f"| {row['panels']} | {row['required_below_reference']} | {probabilities} | {row['plugin_joint_lower_bound']:.1%} | {row['sql_hours_using_old_durations']:.2f} |")
    lines += ['',
        '例如144面板的约80.5%联合下界只在上述概率及独立面板假设成立时有效。',
        '若真实的单面板低于参考线概率只有0.60，同样144面板的单项支持概率约36.2%。',
        '因此不能依据表中的点估计直接确定144或192面板，更不能承诺跑完通过。', '',
        '耗时按原场景中所需普通原版/off/on测量与预热外推：每面板15次构建；不含实例准备、清理或新增采集。',
        '这不是完整12比较的成本，也不能把旧9项与新3项直接拼成同一置信水平的全部达标结论。', '',
        '下一步应评估经验概率不确定性与时段相关，明确新旧判定关系、可接受预算和固定停止规则；',
        '并盘点本机性能采集能力，只有在新测量具有合理信息收益时才制定执行协议。',
        '有计划的新增独立验证可以提高精度；它不要求先证明C缺陷，但不能替代对系统性混杂的处理。', '',
        '原始摘要与本脚本SHA、全量敏感性表见 [planning.json](planning.json)。', '']
    targets = [OUTPUT/'planning.json', OUTPUT/'report.md']
    if any(p.exists() for p in targets):
        raise FileExistsError('refusing to overwrite planning artifacts')
    with targets[0].open('x') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
        f.write('\n')
    with targets[1].open('x') as f:
        f.write('\n'.join(lines))
    print('Offline planning complete; original summary unchanged; no workload executed.')


if __name__ == '__main__':
    main()
