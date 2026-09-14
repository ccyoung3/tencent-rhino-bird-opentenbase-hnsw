#!/usr/bin/env python3
"""A new preregistered, bounded GloVe tuning round; previous evidence is immutable."""
import argparse
import json
import random
import re
import traceback
from datetime import datetime, timezone
from pathlib import Path

import glove
import glove_report
import glove_run
import local_stack
import run
import timing

CONFIGS = [(16, 64), (16, 128), (32, 128)]
EFS = [40, 100, 200, 400, 800, 1000]


def splits(smoke=False):
    if smoke:
        # Smoke uses already-exposed queries, not the new formal holdout.
        return glove.query_split(10000, 10, 20)
    shuffled = list(range(10000))
    random.Random(glove.SPLIT_SEED).shuffle(shuffled)
    return {"tuning": shuffled[:200], "validation": shuffled[1200:2200]}


def save(output, summary):
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")


def build(stack, connection, path, dataset, rows, m, efc):
    path.mkdir()
    args = glove_run.parse_args(["--label", "glove-bounded", "--rows", str(rows),
                               "--maintenance-work-mem", "1792MB"])
    args.m, args.ef_construction = m, efc
    run.validate_args(args)
    summary = {"status": "failed", "parameters": {k: v for k, v in vars(args).items() if k != "dataset"},
               "provenance": stack.provenance, "dataset": dataset, "container_memory_limit_bytes": 6 * 2**30}
    samples, rc = [], None
    try:
        summary["load"] = glove.load_dataset(connection, args.dataset, rows, 2)
        initial = run.read_container_memory()
        print(f"Building {rows} rows, m={m}, efc={efc}", flush=True)
        rc, elapsed = run.execute_build(args, path, samples)
        stderr = (path / "build.stderr.txt").read_text()
        summary["build_elapsed_seconds"] = elapsed
        summary["internal_timing"] = timing.parse_build_timing(stderr, requested=True, command_returncode=rc)
        if rc or summary["internal_timing"]["status"] != "complete":
            raise RuntimeError("build did not finish with complete timing")
        match = re.search(r"using (\d+) parallel workers", stderr)
        workers = int(match[1]) if match else 0
        if workers != 2:
            raise RuntimeError("actual workers differ from preregistered two")
        memories = [s["container_memory_bytes"] for s in samples]
        memories += [v for v in (initial, run.read_container_memory()) if v is not None]
        summary.update(launched_parallel_workers=workers, metadata=run.collect_metadata("<=>"),
            initial_container_memory_bytes=initial, peak_container_memory_bytes=max(memories),
            peak_memory_delta_bytes=max(memories) - initial if initial is not None else None,
            diagnostics=run.diagnose_build(stderr, samples, parallel_memory_safety_margin_bytes=1048576),
            phase_observations=run.summarize_phase_observations(samples))
        if summary["metadata"]["row_count"] != rows or not summary["metadata"]["uses_hnsw_index"]:
            raise RuntimeError("index metadata check failed")
        summary["status"] = "passed"
        return summary
    finally:
        summary["build_command_returncode"] = rc
        (path / "build.stderr.txt").touch(exist_ok=True)
        summary["internal_timing"] = timing.parse_build_timing((path / "build.stderr.txt").read_text(), requested=True, command_returncode=rc)
        run.write_progress(path / "progress.csv", samples)
        save(path, summary)
        (path / "diagnostic.md").write_text(run.render_diagnostic_report(summary))


def render(result):
    lines = ["# GloVe 有限召回改进：独立的新一轮", "", f"- 流程状态：{result['status']}",
             f"- 选中配置：`{result.get('selected')}`", f"- 独立验证达到目标：`{result.get('validation_target_met')}`", "",
             "旧轮次没有被改写；新图拓扑与旧索引不同。本轮按调参选择，不按验证集继续搜索。", "",
             "| m / ef_construction | 构建 s | 索引 MiB | 容器峰值 MiB | spill | 调参最高平均 Recall@10 |",
             "|---|---:|---:|---:|---|---:|"]
    for entry in result["candidates"]:
        b = entry["build"]
        lines.append(f"| {entry['m']} / {entry['ef_construction']} | {b['build_elapsed_seconds']:.3f} | "
                     f"{b['metadata']['index_bytes']/2**20:.1f} | {b['peak_container_memory_bytes']/2**20:.1f} | "
                     f"{b['diagnostics']['spill_detected']} | {max(r['mean_recall'] for r in entry['tuning']['by_ef_search']):.4f} |")
    if result.get("evaluation"):
        lines += [glove_run.render_recall(result["evaluation"]), "![召回与延迟](recall-latency.svg)"]
    lines += ["", "- 构建成本每配置仅一次，不据此声称稳定的构建加速或普适最佳参数。",
              "- 查询三次重复不增加独立样本数；暖缓存服务器执行时间不是端到端延迟或 QPS。",
              "- 参数调整收益不是 C 补丁算法加速；达到平均目标不意味着每个查询都达标。",
              "- 未给出业务延迟预算，因此结果只展示代价，不认定满足真实业务 SLA。",
              "- 所有被采用构建、调参与验证的原始记录保存在本目录；预检单独保存。"]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    output = run.RESULTS_ROOT / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-bounded-recall" + ("-smoke" if args.smoke else ""))
    output.mkdir()
    query_ids = splits(args.smoke)
    protocol = {"rows": 10000 if args.smoke else 1183514, "smoke": args.smoke,
        "configs": CONFIGS, "ef_candidates": EFS, "target": .95, "query_ids": query_ids,
        "query_repetitions": 1 if args.smoke else 3, "selection": "first construction with any tuning ef meeting target; smallest qualifying ef",
        "fallback": "if none pass, no selection; validate last construction at ef1000 alongside40/400; do not retune",
        "memory": "1792MB", "workers": 2, "build_timeout_ms": 1800000,
        "resource_limit_bytes": 6 * 2**30, "index_seed": "normal runtime; not fixed"}
    protocol["tooling_sha256"] = {name: glove.file_sha256(Path(__file__).with_name(name)) for name in
        ("bounded_recall.py", "local_stack.py", "glove.py", "glove_run.py", "glove_report.py", "run.py", "timing.py", "recall.py")}
    (output / "protocol.json").write_text(json.dumps(protocol, indent=2) + "\n")
    result = {"status": "running", "candidates": [], "selected": None, "validation_target_met": None}
    print(output, flush=True)
    save(output, result)
    try:
        dataset = glove.inspect_dataset(run.PROJECT_ROOT / "data/cache/glove-100-angular/glove-100-angular.hdf5")
        for position, (m, efc) in enumerate(CONFIGS):
            if position and not args.smoke:
                pilot = output / f"preflight-m{m}-efc{efc}"
                with local_stack.owned_stack(pilot / "fixture") as (stack, connection):
                    b = build(stack, connection, pilot / "build", dataset, 100000, m, efc)
                    if b["diagnostics"]["spill_detected"] or b["peak_container_memory_bytes"] > 4 * 2**30:
                        raise RuntimeError("preflight exceeded the fixed local resource gate")
            folder = output / f"m{m}-efc{efc}"
            with local_stack.owned_stack(folder / "fixture") as (stack, connection):
                b = build(stack, connection, folder / "build", dataset, protocol["rows"], m, efc)
                connection.execute("SET statement_timeout='60s'; SET max_parallel_workers_per_gather=0")
                common = (connection, run.PROJECT_ROOT / "data/cache/glove-100-angular/glove-100-angular.hdf5", protocol["rows"])
                print(f"Tuning m={m}, efc={efc}", flush=True)
                tuning = glove.evaluate(*common, query_ids["tuning"], EFS, 10, protocol["query_repetitions"], .95,
                                        folder / "tuning", split_name="tuning")
                selected = glove.select_ef(tuning["by_ef_search"], .95)
                result["candidates"].append({"m": m, "ef_construction": efc, "build": b, "tuning": tuning,
                                             "source": folder.name})
                if selected is not None:
                    result["selected"] = {"m": m, "ef_construction": efc, "ef_search": selected, "source": folder.name}
                save(output, result)
                if selected is not None or position == len(CONFIGS) - 1:
                    efs = sorted({40, 400, selected or 1000})
                    (output / "selection-before-validation.json").write_text(json.dumps({
                        "selected": result["selected"], "validation_efs": efs, "source": folder.name}, indent=2) + "\n")
                    print(f"Held-out validation at {efs}; no subsequent tuning", flush=True)
                    validation = glove.evaluate(*common, query_ids["validation"], efs, 10, protocol["query_repetitions"], .95,
                        folder / "validation", split_name="validation", order_seed=20260910)
                    row = next(r for r in validation["by_ef_search"] if r["ef_search"] == (selected or 1000))
                    result["validation_target_met"] = not row["below_target"]
                    result["evaluation"] = {"selected_ef_search": selected, "tuning": tuning, "validation": validation}
                    glove_report.recall_figure(result["evaluation"], output / "recall-latency.svg")
            if result.get("evaluation"):
                break
        result["status"] = "passed"
    except (Exception, KeyboardInterrupt) as error:
        result["status"] = "failed"
        result["error"] = type(error).__name__ + ":" + (getattr(error, "sqlstate", None) or "")
        result["error_locations"] = [{"file": f.filename.rsplit("/", 1)[-1], "line": f.lineno} for f in traceback.extract_tb(error.__traceback__)]
        print(result["error"], flush=True)
    finally:
        save(output, result)
        (output / "report.md").write_text(render(result))
    print(result["status"], flush=True)
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
