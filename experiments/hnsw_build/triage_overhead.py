#!/usr/bin/env python3
"""Fixed-budget follow-up: equal-position dormant comparison and full ordering audit."""
import argparse
import itertools
import json
import math
import secrets
import statistics
import subprocess
import tarfile
import traceback
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import bounded_overhead as cost
import glove
import local_stack
import run

SCENES = [(0, True), (2, False)]
CONDITIONS = ["new_off", "new_on", "new_observed"]
PRIOR = run.RESULTS_ROOT / "20260910T075739Z-bounded-overhead"


def dump(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def old_analysis():
    summary = json.loads((PRIOR / "summary.json").read_text())
    groups = []
    for workers in (0, 2):
        for spill in (False, True):
            by = {(r["block"], r["variant"]): r for r in summary["rows"]
                  if (r["workers"], r["spill"]) == (workers, spill)}
            positions = []
            for position in (1, 2, 3):
                blocks = [b for b in range(12) if [1, 3, 2][b % 3] == position]
                ratios = [by[b, "new_off"]["command_seconds"] / by[b, "old_off"]["command_seconds"] for b in blocks]
                positions.append(dict(position=position, blocks=blocks, paired_ratios=ratios,
                                      median_ratio=statistics.median(ratios)))
            groups.append(dict(workers=workers, spill=spill, positions=positions))
    return {"source": PRIOR.name, "scope": "post-hoc exploratory stratification; all original rows retained",
            "groups": groups}


def inspect_images(output):
    # No database, writable image, network, or host mount. Let docker remove only
    # each newly created ephemeral inspection container and its anonymous volume.
    result = {}
    for variant in ("diagnostics-v2-seed42-arm64", "timing-v1-seed42-arm64"):
        image = "opentenbase-pg18-pgvector:" + variant
        item = json.loads(subprocess.check_output(["docker", "image", "inspect", image], text=True))[0]
        assert item["Id"] == local_stack.IMAGES[variant]
        command = ["docker", "run", "--rm", "--read-only", "--network", "none", "--entrypoint", "/bin/sh", image,
                   "-c", "sha256sum /opt/opentenbase/bin/postgres /opt/opentenbase/lib/postgresql/vector.so; "
                   "/opt/opentenbase/bin/pg_config --configure; /opt/opentenbase/bin/pg_config --cflags; "
                   "/opt/opentenbase/bin/pg_config --version; uname -m"]
        proc = subprocess.run(command, capture_output=True, text=True, timeout=30)
        if proc.returncode:
            raise RuntimeError("read-only image inspection failed")
        result[variant] = dict(id=item["Id"], created=item.get("Created"), layers=item["RootFS"]["Layers"],
            labels=item["Config"].get("Labels"), runtime_inspection=proc.stdout)
    dump(output / "image-inspection.json", result)
    # Hashes/configuration prove sameness of these artifacts, not exact extension source provenance.
    old, new = result.values()
    a, b = old["runtime_inspection"].splitlines(), new["runtime_inspection"].splitlines()
    assert a[0] == b[0] and a[2:] == b[2:], "server binary or build configuration differs; stop before comparison"
    return result


def setup(stack, connection, workers, spill):
    from psycopg import sql
    run.create_dataset(SimpleNamespace(rows=20000, dimensions=32, seed=.42, parallel_workers=workers))
    memory = "1MB" if spill else "128MB"
    connection.execute("SELECT set_config('maintenance_work_mem', %s, false)", (memory,))
    connection.execute("SELECT set_config('max_parallel_maintenance_workers', %s, false)", (str(workers),))
    connection.execute("SET max_parallel_workers=4; SET min_parallel_table_scan_size=0; SET client_min_messages=DEBUG1")
    password = secrets.token_hex(24)
    connection.execute(sql.SQL("CREATE ROLE hnsw_watcher LOGIN PASSWORD {}").format(sql.Literal(password)))
    connection.execute("GRANT pg_read_all_stats TO hnsw_watcher")
    return stack.connect(user="hnsw_watcher", password=password, readonly=True)


def aggregate(rows, blocks, orders):
    if blocks < 1 or not 1 <= orders <= 6:
        raise ValueError("invalid fixed-budget size")
    expected = set()
    for workers, spill in SCENES:
        for block in range(blocks):
            for variant in ("old_off", "new_off"):
                for position in (1, 2, 3):
                    expected.add(("A", workers, spill, block, variant, position))
        for block, order in enumerate(list(itertools.permutations(CONDITIONS))[:orders]):
            for position, variant in enumerate(order, 1):
                expected.add(("B", workers, spill, block, variant, position))
    actual = [(r["study"], r["workers"], r["spill"], r["block"], r["variant"], r["position"]) for r in rows]
    if len(actual) != len(expected) or set(actual) != expected or len({r["source"] for r in rows}) != len(rows):
        raise ValueError("missing, duplicated, or unexpected fixed-budget measurements")
    if not all(math.isfinite(r["command_seconds"]) and r["command_seconds"] > 0 for r in rows):
        raise ValueError("positive finite build times required")
    a = [r for r in rows if r["study"] == "A"]
    b = [r for r in rows if r["study"] == "B"]
    assert len(a) == blocks * 2 * 2 * 3 and len(b) == orders * 2 * 3
    assert len({r["source"] for r in rows}) == len(rows)
    matched, ordering = [], []
    for workers, spill in SCENES:
        by = {(r["block"], r["variant"], r["position"]): r for r in a
              if (r["workers"], r["spill"]) == (workers, spill)}
        assert len(by) == blocks * 6
        details = []
        for block in range(blocks):
            ratios = [by[block, "new_off", p]["command_seconds"] / by[block, "old_off", p]["command_seconds"]
                      for p in (1, 2, 3)]
            details.append(dict(block=block, position_ratios=ratios, median_ratio=statistics.median(ratios)))
        values = [r["median_ratio"] for r in details]
        matched.append(dict(workers=workers, spill=spill, blocks=details,
            median_change_percent=(statistics.median(values)-1)*100, upper_bound=cost.upper_median_bound(values),
            position_changes_percent=[(statistics.median(d["position_ratios"][p] for d in details)-1)*100 for p in range(3)]))
        selected = [r for r in b if (r["workers"], r["spill"]) == (workers, spill)]
        for condition in CONDITIONS:
            by_position = []
            for pos in (1, 2, 3):
                group = [r for r in selected if r["variant"] == condition and r["position"] == pos]
                if group:
                    by_position.append(dict(position=pos, n=len(group), median_seconds=statistics.median(r["command_seconds"] for r in group)))
            ordering.append(dict(workers=workers, spill=spill, condition=condition, positions=by_position))
    return dict(matched=matched, ordering=ordering)


def render(result):
    lines = ["# 默认关闭成本定位", "", "流程状态：" + result["status"], "",
        "正式协议 A：两版相同预热/重复次数，按位置匹配；B：新版完整六种条件排列。smoke 仅各1块/排列。旧数据不覆盖。",
        "passed 只表示预定流程完成，不表示所有性能验收通过。", "",
        "| 场景 | 块数 | 块内位置匹配后的中位变化 | 块比值总体中位数的单侧上界 |",
        "|---|---:|---:|---:|"]
    for g in result.get("analysis", {}).get("matched", []):
        u = g["upper_bound"]["upper_ratio"]
        upper = f"{(u-1)*100:+.2f}%" if u is not None else "样本不足，无有限上界"
        lines.append(f"| workers={g['workers']}, spill={g['spill']} | {len(g['blocks'])} | {g['median_change_percent']:+.2f}% | {upper} |")
    lines += ["", "- 统计单位是独立块，块内三次不视为三个独立块；6块的上界取最大块比值。",
        "- 仅两个预选场景；并行拓扑仍不固定，假定块独立也不能保证宿主没有相关负载。",
        "- 未复现较大变慢不等于零开销或所有场景都通过；不据此删掉旧结果。",
        "- 排列分析只有每条件每位置2次，描述性线索而非因果证明；详见summary.json和逐次原始记录。"]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    blocks, orders = (1, 1) if args.smoke else (6, 6)
    output = run.RESULTS_ROOT / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-bounded-triage" + ("-smoke" if args.smoke else ""))
    output.mkdir()
    paths = [Path(__file__).with_name(n) for n in ("triage_overhead.py", "bounded_overhead.py", "local_stack.py",
             "observe.py", "run.py", "timing.py", "glove.py", "glove_run.py")]
    protocol = dict(blocks=blocks, orders=orders, smoke=args.smoke, scenes=SCENES, warmups=2, formal_per_fixture=3,
        rows=20000, dimensions=32, m=16, ef_construction=64, prior_source=PRIOR.name,
        tooling_sha256={p.name: glove.file_sha256(p) for p in paths}, no_optional_stopping=True)
    dump(output / "protocol.json", protocol)
    with tarfile.open(output / "tooling-at-start.tar.gz", "x:gz") as archive:
        for p in paths:
            archive.add(p, arcname=p.name)
    dump(output / "prior-position-analysis.json", old_analysis())
    result = dict(status="running", rows=[], warmups=[])
    print(output, flush=True)
    try:
        result["images"] = inspect_images(output)
        permutations = list(itertools.permutations(CONDITIONS))[:orders]
        for study, repetitions in (("A", blocks), ("B", orders)):
            for block in range(repetitions):
                scenes = SCENES if block % 2 == 0 else SCENES[::-1]
                for workers, spill in scenes:
                    versions = (["old", "new"] if block % 2 == 0 else ["new", "old"]) if study == "A" else ["new"]
                    for version in versions:
                        variant = "diagnostics-v2-seed42-arm64" if version == "old" else "timing-v1-seed42-arm64"
                        folder = output / f"{study}-b{block:02d}-w{workers}" / version
                        with local_stack.owned_stack(folder, variant) as (stack, connection):
                            watcher = setup(stack, connection, workers, spill)
                            conditions = [version + "_off"] * 3 if study == "A" else list(permutations[block])
                            cases = [(True, p+1, version + "_off") for p in range(2)]
                            cases += [(False, p+1, condition) for p, condition in enumerate(conditions)]
                            for warmup, position, condition in cases:
                                case = folder / f"{'warmup' if warmup else 'formal'}-{position}-{condition}"
                                measurement = cost.measure(connection, watcher, case, condition, workers, spill)
                                previous = None if warmup or position == 1 else conditions[position-2]
                                record = {**measurement, "study": study, "block": block, "position": position,
                                          "previous_condition": previous, "source": str(case.relative_to(output))}
                                result["warmups" if warmup else "rows"].append(record)
                                dump(output / "summary.json", result)
                    print(f"Study {study} block {block+1}/{repetitions}, workers={workers} complete", flush=True)
        result["analysis"] = aggregate(result["rows"], blocks, orders)
        result["status"] = "passed"
    except (Exception, KeyboardInterrupt) as error:
        result["status"] = "failed"
        result["error"] = type(error).__name__ + ":" + (getattr(error, "sqlstate", None) or "")
        result["error_locations"] = [{"file": f.filename.rsplit("/", 1)[-1], "line": f.lineno} for f in traceback.extract_tb(error.__traceback__)]
        print(result["error"], flush=True)
    finally:
        dump(output / "summary.json", result)
        (output / "report.md").write_text(render(result))
    print(result["status"], flush=True)
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
