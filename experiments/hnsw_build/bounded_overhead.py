#!/usr/bin/env python3
"""Fixed-budget paired costs: dormant timing, enabled timing, and read-only observer."""
import argparse
import json
import math
import re
import secrets
import statistics
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import glove
import local_stack
import observe
import run
import timing

EFFECTS = {"dormant_timing": ("new_off", "old_off"),
           "enabled_timing": ("new_on", "new_off"),
           "observer": ("new_observed", "new_on")}


def upper_median_bound(values, confidence=.95):
    """Exact distribution-free order-statistic upper bound for population median.

    Assumes independent sampled blocks. Discreteness is conservative; small n
    may provide no finite bound. This is not a bound on every future run.
    """
    if not values or not all(math.isfinite(v) and v > 0 for v in values):
        raise ValueError("positive finite paired ratios required")
    ordered, n = sorted(values), len(values)
    cumulative = 0
    for k in range(1, n + 1):
        cumulative += math.comb(n, k - 1) / 2**n
        if cumulative >= confidence:
            return {"upper_ratio": ordered[k - 1], "rank": k, "coverage": cumulative}
    return {"upper_ratio": None, "rank": None, "coverage": None}


def summarize(rows, expected_blocks):
    groups = []
    if len({(r["workers"], r["spill"], r["block"], r["variant"]) for r in rows}) != len(rows):
        raise ValueError("duplicate measurements")
    for workers in (0, 2):
        for spill in (False, True):
            records = [r for r in rows if r["workers"] == workers and r["spill"] == spill]
            if len(records) != expected_blocks * 4:
                raise ValueError("incomplete fixed-budget experiment")
            indexed = {(r["block"], r["variant"]): r for r in records}
            observations = [r.get("observer", {}).get("observation", {}) for r in records if r["variant"] == "new_observed"]
            coverage = sum(bool(o.get("phases")) and o.get("samples", 0) > 0 for o in observations)
            for effect, (numerator, denominator) in EFFECTS.items():
                values = [indexed[(b, numerator)]["command_seconds"] / indexed[(b, denominator)]["command_seconds"]
                          for b in range(expected_blocks)]
                bound = upper_median_bound(values)
                groups.append({"workers": workers, "spill": spill, "effect": effect, "pairs": len(values),
                    "paired_ratios": values, "median_change_percent": (statistics.median(values) - 1) * 100,
                    "upper_bound": bound, "reference_limit_percent": 5,
                    "observer_runs_with_progress": coverage if effect == "observer" else None,
                    "verdict": "supported_below_reference" if bound["upper_ratio"] is not None and bound["upper_ratio"] < 1.05 else "not_established"})
                if effect == "observer" and coverage != expected_blocks:
                    groups[-1]["verdict"] = "insufficient_observation_coverage"
    return groups


def measure(connection, watcher, path, variant, workers, spill):
    path.mkdir()
    enabled = variant in ("new_on", "new_observed")
    if variant != "old_off":
        connection.execute("SELECT set_config('hnsw.build_timing', %s, false)", ("on" if enabled else "off",))
    connection.execute("DROP INDEX IF EXISTS hnsw_diag.items_embedding_hnsw_idx")
    notices = []
    def notice(diag):
        notices.append((diag.severity_nonlocalized or "NOTICE") + ": " + (diag.message_primary or "") +
                       ("\nDETAIL: " + diag.message_detail if diag.message_detail else ""))
    connection.add_notice_handler(notice)
    stop = threading.Event()
    observed = {"attachment_probes": 0}
    thread = None
    def watch():
        try:
            # A PID may be idle immediately before CREATE INDEX. Explicitly wait
            # with the same one-second cadence; probes are part of observer cost.
            while not stop.is_set():
                row = observe.sample(watcher, connection.info.backend_pid)
                observed["attachment_probes"] += 1
                if row and row.get("phase"):
                    observed["observation"] = observe.observe(watcher, connection.info.backend_pid,
                        path / "observer", interval=1., duration=1800., stop=stop)
                    break
                stop.wait(1.)
        except Exception as error:
            observed["error"] = type(error).__name__
    if variant == "new_observed":
        thread = threading.Thread(target=watch)
        thread.start()
    started = time.perf_counter()
    rc, error = 1, None
    try:
        connection.execute("CREATE INDEX items_embedding_hnsw_idx ON hnsw_diag.items "
                           "USING hnsw (embedding vector_l2_ops) WITH (m=16, ef_construction=64)")
        elapsed = time.perf_counter() - started
        rc = 0
    except BaseException as exception:
        elapsed = time.perf_counter() - started
        error = exception
    finally:
        connection.remove_notice_handler(notice)
        stop.set()
        if thread:
            thread.join(timeout=10)
        text = "\n".join(notices) + "\n"
        (path / "build.stderr.txt").write_text(text)
        item = {"variant": variant, "workers": workers, "spill": spill,
                "command_seconds": elapsed, "command_returncode": rc, "observer": observed,
                "internal_timing": timing.parse_build_timing(text, requested=enabled, command_returncode=rc)}
        if error:
            item["error"] = type(error).__name__ + ":" + (getattr(error, "sqlstate", None) or "")
        (path / "measurement.json").write_text(json.dumps(item, indent=2) + "\n")
    if error:
        raise error
    if thread and (thread.is_alive() or "error" in observed or observed["attachment_probes"] == 0):
        raise RuntimeError("observer failed to execute safely")
    if variant == "new_observed" and observed.get("observation", {}).get("status") in ("error", "insufficient_visibility"):
        raise RuntimeError("observer returned an invalid observation")
    actual = re.search(r"using (\d+) parallel workers", text)
    if (int(actual[1]) if actual else 0) != workers or ("graph no longer fits" in text) != spill:
        raise RuntimeError("actual build path differs from protocol")
    if item["internal_timing"]["status"] != ("complete" if enabled else "not_requested"):
        raise RuntimeError("internal timing verification failed")
    item["index_bytes"] = connection.execute("SELECT pg_relation_size('hnsw_diag.items_embedding_hnsw_idx')").fetchone()[0]
    item["image_variant"] = "diagnostics-v2-seed42-arm64" if variant == "old_off" else "timing-v1-seed42-arm64"
    (path / "measurement.json").write_text(json.dumps(item, indent=2) + "\n")
    return item


def render(result):
    lines = ["# 固定预算开销验证", "", f"流程状态：{result['status']}", "",
             "三个来源分开比较。5% 是本轮工程参考线，不是官方标准；不是证明零开销。", "",
             "| worker | spill | 对比来源 | 配对数 | 中位变化 | 中位比值的单侧上界 | 采到进度的观察次数 | 低于5%的证据 |",
             "|---:|---|---|---:|---:|---:|---:|---|"]
    for row in result.get("groups", []):
        upper = row["upper_bound"]["upper_ratio"]
        text = f"{(upper-1)*100:+.2f}%" if upper is not None else "无有限上界"
        lines.append(f"| {row['workers']} | {row['spill']} | {row['effect']} | {row['pairs']} | "
                     f"{row['median_change_percent']:+.2f}% | {text} | {row['observer_runs_with_progress']} | {row['verdict']} |")
    lines += ["", "- dormant_timing：新版关闭/旧版关闭；enabled_timing：新版开启/关闭；observer：开启并观察/仅开启。",
        "- 主计时为客户端等待完整 SQL 调用完成的经过时间，含消息处理与本地往返，不使用内部计时测自身成本。",
        "- 每场景12个独立新环境块，每镜像块预热一次；正式4条件，全部重复与失败保留。",
        "- 单侧上界针对配对比值的总体中位数，假定各块独立；12对的实际覆盖率约98.1%，不是每次运行的最大开销。",
        "- 宿主仍可能存在相关负载，样本与并行拓扑有波动；不把本机结果推广到生产。",
        "- supported_below_reference 仅支持对应场景；not_established 表示不能证明低于门限，不自动认定一定有回归。",
        "- 所有比较是逐场景判定，不给出跨12项比较的联合置信保证。观察器连接准备时间在建索引计时外。",
        "- insufficient_observation_coverage 表示至少一次未采到构建阶段；即便耗时很小，也不支持完整观察的开销结论。",
        "- smoke 仅每场景1块；上述12块统计要求只适用于正式实验。"]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true", help="one block per scenario; cannot establish the 5%% claim")
    args = parser.parse_args()
    from psycopg import sql
    blocks = 1 if args.smoke else 12
    output = run.RESULTS_ROOT / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-bounded-overhead" + ("-smoke" if args.smoke else ""))
    output.mkdir()
    protocol = {"rows": 20000, "dimensions": 32, "m": 16, "ef_construction": 64,
                "blocks_per_scenario": blocks, "smoke": args.smoke, "reference_limit_percent": 5,
                "confidence": "one-sided distribution-free >=95% median ratio bound; per comparison",
                "observer_interval_seconds": 1, "images": local_stack.IMAGES,
                "warmups_per_image_block": 1, "formal_variants_per_block": ["old_off", "new_off", "new_on", "new_observed"],
                "fixed_budget_no_optional_stopping": True}
    protocol["tooling_sha256"] = {name: glove.file_sha256(Path(__file__).with_name(name)) for name in
        ("bounded_overhead.py", "local_stack.py", "observe.py", "run.py", "timing.py")}
    (output / "protocol.json").write_text(json.dumps(protocol, indent=2) + "\n")
    result = {"status": "running", "rows": [], "warmups": []}
    print(output, flush=True)
    try:
        # Rotate scenarios across blocks, not all low-memory runs in one time window.
        scenes = [(0, False), (0, True), (2, False), (2, True)]
        for block in range(blocks):
            order = scenes[block % 4:] + scenes[:block % 4]
            for workers, spill in order:
                group_path = output / f"b{block:02d}-w{workers}-{'low' if spill else 'high'}"
                for old in ((True, False) if block % 2 == 0 else (False, True)):
                    variant = "diagnostics-v2-seed42-arm64" if old else "timing-v1-seed42-arm64"
                    with local_stack.owned_stack(group_path / ("old" if old else "new"), variant) as (stack, connection):
                        fixture_args = SimpleNamespace(rows=20000, dimensions=32, seed=.42, parallel_workers=workers)
                        run.create_dataset(fixture_args)
                        memory = ("4MB" if workers else "1MB") if spill else "128MB"
                        connection.execute("SELECT set_config('maintenance_work_mem', %s, false)", (memory,))
                        connection.execute("SELECT set_config('max_parallel_maintenance_workers', %s, false)", (str(workers),))
                        connection.execute("SET max_parallel_workers=4; SET min_parallel_table_scan_size=0; SET client_min_messages=DEBUG1")
                        password = secrets.token_hex(24)
                        connection.execute(sql.SQL("CREATE ROLE hnsw_watcher LOGIN PASSWORD {}").format(sql.Literal(password)))
                        connection.execute("GRANT pg_read_all_stats TO hnsw_watcher")
                        watcher = stack.connect(user="hnsw_watcher", password=password, readonly=True)
                        root = group_path / ("old" if old else "new")
                        warmup = measure(connection, watcher, root / "warmup", "old_off" if old else "new_off", workers, spill)
                        result["warmups"].append({**warmup, "block": block, "source": str((root / "warmup").relative_to(output))})
                        variants = ["old_off"] if old else ["new_off", "new_on", "new_observed"]
                        if not old:
                            variants = variants[block % 3:] + variants[:block % 3]
                        for name in variants:
                            item = measure(connection, watcher, root / name, name, workers, spill)
                            result["rows"].append({**item, "block": block, "source": str((root / name).relative_to(output))})
                            (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
                print(f"Block {block+1}/{blocks}, workers={workers}, spill={spill} complete", flush=True)
        result["groups"] = summarize(result["rows"], blocks)
        result["status"] = "passed"
    except (Exception, KeyboardInterrupt) as error:
        result["status"] = "failed"
        result["error"] = type(error).__name__ + ":" + (getattr(error, "sqlstate", None) or "")
        result["error_locations"] = [{"file": f.filename.rsplit("/", 1)[-1], "line": f.lineno} for f in traceback.extract_tb(error.__traceback__)]
        print(result["error"], flush=True)
    finally:
        (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
        (output / "report.md").write_text(render(result))
    print(result["status"], flush=True)
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
