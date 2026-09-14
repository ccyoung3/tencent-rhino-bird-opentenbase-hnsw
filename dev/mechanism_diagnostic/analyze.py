#!/usr/bin/env python3
"""Independent, descriptive-only analysis of a completed mechanism diagnosis.

Reads frozen evidence; imports no runner, parser, or statistical implementation.
Requires the independent audit to bind the same summary and protocol. Writes
only a new output directory outside the input run. No Docker or database calls.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import itertools
import json
import math
from pathlib import Path
import statistics


CONDITIONS = ("baseline", "off", "on")
SCENES = {
    "no-spill": {"table": "large", "rows": 100000, "memory": "256MB", "spill": "none"},
    "immediate-spill": {"table": "small", "rows": 30000, "memory": "4MB", "spill": "zero"},
    "partial-spill": {"table": "small", "rows": 30000, "memory": "8MB", "spill": "partial"},
}
METRICS = ("sql_seconds", "scan_cpu_seconds", "distance_calls",
           "cpu_nanoseconds_per_distance", "distances_per_row", "index_bytes",
           "mean_initialized_level", "upper_level_fraction")
LIMITATIONS = [
    "仅描述全部 36 次测量；18 次预热只作覆盖核对，未混入统计。",
    "每组 4 次测量来自 2 个面板，每面板重复 2 次；不能当作 4 个独立实验。",
    "18 个 repeat1/repeat0 配对是同一条件的重复变化，不是候选/原版效果。",
    "scan CPU 是三个参与进程的 user+system CPU 之和；各进程 elapsed 不相加。",
    "scan_and_insert 包含扫描期间的 spill，排除 leader 扫描后的最终 flush、WAL、清理；SQL 时间覆盖完整命令。",
    "distance_calls 覆盖 HNSW 距离函数调用，不等于全部指令、内存访问或等量计算成本；不包含归一化和相等比较。",
    "层数直方图描述初始化候选元素；本合成数据计数等于行数，不代表任意业务数据的最终图节点数。",
    "每场景 12 点相关系数混合条件、面板和重复，样本小且可能存在时序相关；只作描述，不证明因果或 CPU 频率变化。",
    "插桩增加本地计数、分支和一次日志，并可能改变调度；native worker 随机层数和并行图拓扑仍会变化。",
    "CPU/距离调用仅为机制描述，不能据此校正总体时间或宣称候选成本通过；本分析不产生性能验收、显著性检验或 p 值。",
]


class AnalysisError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise AnalysisError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_json(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "duplicate JSON key")
            result[key] = value
        return result

    def reject(value):
        raise AnalysisError("nonfinite JSON number: " + value)

    return json.loads(data, object_pairs_hook=unique, parse_constant=reject)


def integer(value, label, positive=False):
    require(type(value) is int and value >= (1 if positive else 0), label + ": invalid integer")
    return value


def number(value, label, positive=True):
    require(type(value) in (int, float) and math.isfinite(value)
            and value >= 0 and (not positive or value > 0), label + ": invalid number")
    return value


def distribution(values):
    return {"n": len(values), "values": list(values), "minimum": min(values),
            "median": statistics.median(values), "maximum": max(values)}


def logarithmic_correlation(xs, ys):
    require(len(xs) == len(ys) == 12, "correlations require all 12 scene measurements")
    x, y = [math.log(v) for v in xs], [math.log(v) for v in ys]
    mx, my = statistics.mean(x), statistics.mean(y)
    dx, dy = [v-mx for v in x], [v-my for v in y]
    xx, yy = math.fsum(v*v for v in dx), math.fsum(v*v for v in dy)
    if xx == 0 or yy == 0:
        return {"n": 12, "pearson_r": None, "reason": "zero variance in at least one log series"}
    coefficient = math.fsum(a*b for a, b in zip(dx, dy)) / math.sqrt(xx*yy)
    return {"n": 12, "pearson_r": max(-1., min(1., coefficient)), "reason": None}


def validate_protocol(protocol):
    require(protocol.get("schema") == 1 and type(protocol.get("schema")) is int,
            "unsupported protocol schema")
    require(protocol.get("mode") == "diagnosis" and protocol.get("exploratory") is True,
            "completed diagnosis required; smoke is not an analysis input")
    require(protocol.get("formal_count") == 36 and protocol.get("warmup_count") == 18,
            "fixed 36/18 budget required")
    require(protocol.get("workers") == 2 and protocol.get("scenes") == SCENES,
            "unexpected scenes or worker count")
    require(protocol.get("no_acceptance_inference") is True
            and protocol.get("no_effect_based_sample_addition") is True,
            "descriptive fixed-budget protocol flags required")
    require(set(protocol.get("images", {})) == set(CONDITIONS), "three image conditions required")
    require(isinstance(protocol.get("sources"), dict) and protocol["sources"], "source digests required")
    for digest in [*protocol["sources"].values(), protocol.get("build_manifest_sha256"),
                   protocol.get("method_sha256")]:
        require(isinstance(digest, str) and len(digest) == 64
                and all(c in "0123456789abcdef" for c in digest), "invalid source digest")
    plan = protocol.get("schedule", [])
    require(len(plan) == 2 and [p["panel"] for p in plan] == [0, 1], "two ordered panels required")
    expected = {False: [], True: []}
    permutations = []
    for panel in plan:
        require(sorted(panel["slots"]) == sorted(CONDITIONS), "invalid instance slots")
        require(len(panel["scenes"]) == 3 and {s["scene"] for s in panel["scenes"]} == set(SCENES),
                "each panel must cover every scene once")
        for scene in panel["scenes"]:
            order = scene["warmup_order"]
            require(sorted(order) == sorted(CONDITIONS), "invalid warmup order")
            require(scene["order"] == order + list(reversed(order)), "formal order must be mirrored")
            permutations.append(tuple(order))
            events = [(c, True, 0) for c in order]
            events += [(c, False, int(i >= 3)) for i, c in enumerate(scene["order"])]
            for position, (condition, warmup, repeat) in enumerate(events):
                source = f"p{panel['panel']:02d}/{condition}/{scene['scene']}-{'warmup' if warmup else 'measure'}-{repeat}"
                expected[warmup].append((panel["panel"], scene["scene"], condition, repeat,
                                         warmup, position, source))
    require(set(permutations) == set(itertools.permutations(CONDITIONS)), "all six orders required")
    require(plan[0]["slots"] == list(reversed(plan[1]["slots"])), "instance order must reverse")
    require([s["scene"] for s in plan[0]["scenes"]] ==
            [s["scene"] for s in reversed(plan[1]["scenes"])], "scene order must reverse")
    return expected


def normalize_row(row, protocol):
    scene, condition = row["scene"], row["condition"]
    config = SCENES[scene]
    require(row.get("validation") == "passed" and row.get("command_returncode") == 0,
            "all measurements must have succeeded")
    require(row.get("config") == config and row.get("workers") == 2,
            "measurement configuration differs from protocol")
    require(row.get("image") == protocol["images"][condition], "measurement image mismatch")
    sql = number(row["command_seconds"], "SQL seconds")
    civil = number(row["civil_wall_seconds"], "civil seconds")
    require(abs(sql-civil) <= 1, "dual clock discrepancy")
    for key in ("resources_before", "resources_after"):
        require(row[key].get("power_source") == "AC", "AC boundary required")
    require(row["internal_timing"].get("status") == ("complete" if condition == "on" else "not_requested"),
            "timing mode mismatch")
    index_bytes = integer(row["index_bytes"], "index bytes", True)
    index_oid = integer(row["index_oid"], "index oid", True)
    spill = row["spill_after_tuples"]
    if scene == "no-spill":
        require(spill is None, "unexpected spill")
    else:
        integer(spill, "spill tuple count")
        require(spill == 0 if scene == "immediate-spill" else 0 < spill < config["rows"],
                "wrong spill regime")
    work = row["work"]
    require(work["scope"] == "scan_and_insert", "wrong work scope")
    records = work["records"]
    require(len(records) == 3 and {r["worker_number"] for r in records} == {-1, 0, 1}
            and len({r["pid"] for r in records}) == 3, "three distinct participants required")
    fields = ("callbacks_seen", "successful_inserts", "distance_calls", "elements_initialized",
              "user_cpu_us", "system_cpu_us")
    totals = {key: 0 for key in fields}
    hist = [0]*64
    elapsed_values = []
    for record in records:
        require(record["schema"] == 1 and type(record["schema"]) is int
                and record["test_only"] is True and record["scope"] == "scan_and_insert"
                and record["mode"] == "native", "invalid participant schema")
        integer(record["pid"], "participant PID", True)
        require(type(record["worker_number"]) is int and record["index_oid"] == index_oid
                and record["role"] == ("leader" if record["worker_number"] == -1 else "worker"),
                "wrong participant identity")
        for key in fields:
            totals[key] += integer(record[key], key)
        require(record["callbacks_seen"] == record["successful_inserts"] == record["elements_initialized"] > 0,
                "fixture tuple counts disagree")
        require(record["distance_calls"] > 0 and record["user_cpu_us"] + record["system_cpu_us"] > 0,
                "positive work and CPU required")
        buckets = record["level_hist"]
        require(len(buckets) == 64, "64 histogram buckets required")
        for level, count in enumerate(buckets):
            hist[level] += integer(count, "level count")
        require(sum(buckets) == record["elements_initialized"], "incomplete participant histogram")
        elapsed_values.append(integer(record["elapsed_us"], "participant elapsed", True)/1e6)
    require(totals["callbacks_seen"] == config["rows"], "incomplete heap coverage")
    cpu = (totals["user_cpu_us"] + totals["system_cpu_us"])/1e6
    for key, value in {**totals, "cpu_seconds": cpu, "level_hist": hist,
                       "max_participant_elapsed_seconds": max(elapsed_values)}.items():
        require(work["totals"].get(key) == value, "stored work total differs from independent sum: " + key)
    distance = totals["distance_calls"]
    return {"panel": row["panel"], "scene": scene, "condition": condition, "repeat": row["repeat"],
            "position": row["position"], "source": row["source"],
            "started_epoch": number(row["started_epoch"], "start time"),
            "rows": config["rows"], "sql_seconds": sql, "scan_cpu_seconds": cpu,
            "distance_calls": distance, "cpu_nanoseconds_per_distance": cpu*1e9/distance,
            "distances_per_row": distance/config["rows"], "level_hist": hist,
            "mean_initialized_level": sum(i*n for i, n in enumerate(hist))/config["rows"],
            "upper_level_fraction": sum(hist[1:])/config["rows"],
            "spill_after_tuples": spill, "index_bytes": index_bytes,
            "participant_elapsed_seconds": elapsed_values,
            "max_participant_elapsed_seconds": max(elapsed_values)}


def compute(summary, protocol, audit, summary_sha256, protocol_sha256):
    require(summary.get("status") == "completed", "completed summary required")
    require(audit.get("audit_status") == "verified", "independent verified audit required")
    require(audit.get("summary_sha256") == summary_sha256
            and audit.get("protocol_sha256") == protocol_sha256, "independent audit digest mismatch")
    require(audit.get("formal_count") == 36 and audit.get("warmup_count") == 18,
            "independent audit must cover 36/18 measurements")
    expected = validate_protocol(protocol)
    require(len(summary["rows"]) == 36 and len(summary["warmups"]) == 18, "exact 36/18 records required")
    normalized = {False: [], True: []}
    for warmup, name in ((False, "rows"), (True, "warmups")):
        actual = []
        for row in summary[name]:
            require(type(row["warmup"]) is bool and row["warmup"] == warmup,
                    "measurement/warmup label mismatch")
            for key in ("panel", "repeat", "position"):
                integer(row[key], key)
            actual.append(tuple(row[key] for key in
                                ("panel", "scene", "condition", "repeat", "warmup", "position", "source")))
            normalized[warmup].append(normalize_row(row, protocol))
        require(actual == expected[warmup], "actual record order or identity differs from full schedule")
    rows = normalized[False]
    groups = []
    pairs = []
    for scene, condition in itertools.product(SCENES, CONDITIONS):
        selected = sorted((r for r in rows if (r["scene"], r["condition"]) == (scene, condition)),
                          key=lambda r: (r["panel"], r["repeat"]))
        require(len(selected) == 4, "each group must retain four measurements")
        groups.append({"scene": scene, "condition": condition, "n": 4, "panels": 2,
                       "measurement_order": [r["source"] for r in selected],
                       "metrics": {key: distribution([r[key] for r in selected]) for key in METRICS},
                       "spill_after_tuples": {"values": [r["spill_after_tuples"] for r in selected],
                           "applicable": scene != "no-spill"},
                       "level_histograms": [r["level_hist"] for r in selected],
                       "summed_level_histogram": [sum(r["level_hist"][i] for r in selected) for i in range(64)]})
        for panel in (0, 1):
            before, after = [r for r in selected if r["panel"] == panel]
            require((before["repeat"], after["repeat"]) == (0, 1), "one pair per panel/group required")
            changes = {}
            for key in METRICS:
                denominator = before[key]
                ratio = after[key]/denominator if denominator else None
                changes[key] = {"repeat0": before[key], "repeat1": after[key],
                                "ratio": ratio, "change_percent": 100*(ratio-1) if ratio is not None else None,
                                "undefined_reason": "zero repeat0" if ratio is None else None}
            pairs.append({"panel": panel, "scene": scene, "condition": condition,
                          "sources": [before["source"], after["source"]], "changes": changes,
                          "spill_after_tuples": [before["spill_after_tuples"], after["spill_after_tuples"]],
                          "level_histograms": [before["level_hist"], after["level_hist"]]})
    correlations = []
    for scene in SCENES:
        selected = [r for r in rows if r["scene"] == scene]
        correlations.append({"scene": scene, "n": len(selected),
                             "measurement_order": [r["source"] for r in selected],
                             "log_sql_log_scan_cpu": logarithmic_correlation(
                                 [r["sql_seconds"] for r in selected], [r["scan_cpu_seconds"] for r in selected]),
                             "log_sql_log_distance": logarithmic_correlation(
                                 [r["sql_seconds"] for r in selected], [r["distance_calls"] for r in selected])})
    coverage = Counter((r["scene"], r["condition"]) for r in normalized[True])
    require(set(coverage.values()) == {2}, "two warmups per group required")
    return {"schema": 1, "status": "descriptive_complete", "inference": "descriptive_only",
            "formal_count": 36, "warmup_count": 18, "group_count": 9, "repeat_pair_count": 18,
            "limitations": LIMITATIONS, "rows": rows, "groups": groups, "repeat_pairs": pairs,
            "mixed_condition_scene_correlations": correlations,
            "warmup_coverage_only": [{"scene": s, "condition": c, "n": coverage[s, c]}
                                     for s, c in itertools.product(SCENES, CONDITIONS)]}


def render(result):
    lines = ["# 并行机制诊断：完整描述性分析", "", "36 次测量、18 次预热覆盖、9 组及 18 个重复配对均已核对；本报告不形成性能验收。", ""]
    lines += ["- " + line for line in result["limitations"]]
    lines += ["", "## 同条件重复变化（全部 18 对）", "",
              "比值方向均为 repeat1/repeat0；完整起止值和层数数组见 analysis.json。", "",
              "| scene | condition | panel | SQL ratio | scan CPU ratio | distance ratio | CPU/distance ratio |",
              "|---|---|---:|---:|---:|---:|---:|"]
    for pair in result["repeat_pairs"]:
        changes = pair["changes"]
        lines.append(f"| {pair['scene']} | {pair['condition']} | {pair['panel']} | " +
                     " | ".join(str(changes[k]["ratio"]) for k in
                                ("sql_seconds", "scan_cpu_seconds", "distance_calls", "cpu_nanoseconds_per_distance")) + " |")
    lines += ["", "## 场景与条件分布（全部 9 组）", "",
              "每格按 min / median / max 显示；每组保留 4 个原值，顺序为 p0r0、p0r1、p1r0、p1r1。", "",
              "| scene | condition | SQL seconds | scan CPU seconds | distance calls | CPU ns/distance | distance/row |",
              "|---|---|---|---|---|---|---|"]
    for group in result["groups"]:
        cells = [" / ".join(str(group["metrics"][key][stat]) for stat in ("minimum", "median", "maximum"))
                 for key in METRICS[:5]]
        lines.append(f"| {group['scene']} | {group['condition']} | " + " | ".join(cells) + " |")
    lines += ["", "## 层数、spill 与索引尺寸", "",
              "层数列展示每个非零桶的 4 个原始计数；未列桶均为 0。JSON 保留每次完整 64 桶。", "",
              "| scene | condition | spill after tuples (4 values) | index bytes (4 values) | level → 4 counts |",
              "|---|---|---|---|---|"]
    for group in result["groups"]:
        levels = {i: [h[i] for h in group["level_histograms"]]
                  for i, total in enumerate(group["summed_level_histogram"]) if total}
        lines.append(f"| {group['scene']} | {group['condition']} | {group['spill_after_tuples']['values']} | "
                     f"{group['metrics']['index_bytes']['values']} | {levels} |")
    lines += ["", "## 全部 36 次测量", "",
              "| source | SQL seconds | scan CPU seconds | distance calls | CPU ns/distance | distance/row | spill tuples | index bytes |",
              "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for row in result["rows"]:
        lines.append(f"| {row['source']} | " + " | ".join(str(row[k]) for k in
                     (*METRICS[:5], "spill_after_tuples", "index_bytes")) + " |")
    lines += ["", "## 混合条件的场景相关（描述性）", "",
              "每场景使用全部 12 次正式测量，包含相关重复及不同条件；不能据此作因果判断。", "",
              "| scene | n | corr(log SQL, log scan CPU) | corr(log SQL, log distance) |",
              "|---|---:|---:|---:|"]
    for corr in result["mixed_condition_scene_correlations"]:
        lines.append(f"| {corr['scene']} | {corr['n']} | {corr['log_sql_log_scan_cpu']['pearson_r']} | "
                     f"{corr['log_sql_log_distance']['pearson_r']} |")
    lines += ["", "## 输入与分析源码摘要", "", "```json",
              json.dumps(result["provenance"], ensure_ascii=False, indent=2), "```", ""]
    return "\n".join(lines)


def analyze(input_dir, output_dir):
    input_dir, output_dir = Path(input_dir).resolve(strict=True), Path(output_dir).resolve()
    require(not output_dir.exists(), "output directory already exists; refusing overwrite")
    require(output_dir != input_dir and input_dir not in output_dir.parents,
            "analysis output must be outside the original run")
    paths = {name: input_dir / name for name in ("summary.json", "protocol.json", "independent-audit.json")}
    raw = {name: path.read_bytes() for name, path in paths.items()}
    summary, protocol, audit = [read_json(raw[name]) for name in paths]
    result = compute(summary, protocol, audit, sha(raw["summary.json"]), sha(raw["protocol.json"]))
    source = Path(__file__).read_bytes()
    result["provenance"] = {"input_directory": str(input_dir), "summary_sha256": sha(raw["summary.json"]),
        "protocol_sha256": sha(raw["protocol.json"]), "independent_audit_sha256": sha(raw["independent-audit.json"]),
        "analysis_tool_sha256": sha(source), "measurement_sources": protocol["sources"],
        "build_manifest_sha256": protocol["build_manifest_sha256"], "method_sha256": protocol["method_sha256"],
        "created_at_utc": datetime.now(timezone.utc).isoformat()}
    report = render(result)
    for name, path in paths.items():
        require(path.read_bytes() == raw[name], "input changed during analysis")
    output_dir.mkdir(parents=True, exist_ok=False)
    with (output_dir / "analysis.json").open("x") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    with (output_dir / "report.md").open("x") as stream:
        stream.write(report)
    with (output_dir / "analyzer-source.py").open("xb") as stream:
        stream.write(source)
    return result


def selftest():
    """Synthetic checks have known ratios and never become diagnostic evidence."""
    import copy
    import tempfile

    protocol = {"schema": 1, "mode": "diagnosis", "exploratory": True,
                "formal_count": 36, "warmup_count": 18, "workers": 2, "scenes": SCENES,
                "no_acceptance_inference": True, "no_effect_based_sample_addition": True,
                "images": {c: c for c in CONDITIONS}, "sources": {"synthetic": "0"*64},
                "build_manifest_sha256": "1"*64, "method_sha256": "2"*64, "schedule": []}
    orders = list(itertools.permutations(CONDITIONS))
    for panel in (0, 1):
        names = list(SCENES) if panel == 0 else list(reversed(SCENES))
        protocol["schedule"].append({"panel": panel, "slots": list(CONDITIONS if panel == 0 else reversed(CONDITIONS)),
            "scenes": [{"scene": name, "warmup_order": list(orders[3*panel+i]),
                        "order": list(orders[3*panel+i]) + list(reversed(orders[3*panel+i]))}
                       for i, name in enumerate(names)]})
    expected = validate_protocol(protocol)
    summary = {"status": "completed", "rows": [], "warmups": []}
    for warmup, events in expected.items():
        for panel, scene, condition, repeat, _, position, source in events:
            config = SCENES[scene]
            counts = [config["rows"]//3, config["rows"]//3, config["rows"]-2*(config["rows"]//3)]
            scale = (repeat+1)*(panel+1)*(CONDITIONS.index(condition)+1)
            records = []
            for i, count in enumerate(counts):
                records.append({"schema": 1, "test_only": True, "scope": "scan_and_insert", "mode": "native",
                    "role": "leader" if i == 0 else "worker", "worker_number": i-1, "pid": 100+i, "index_oid": 123,
                    "callbacks_seen": count, "successful_inserts": count, "elements_initialized": count,
                    "distance_calls": count*scale, "user_cpu_us": count*scale, "system_cpu_us": 0,
                    "elapsed_us": count*scale, "level_hist": [count]+[0]*63})
            totals = {key: sum(r[key] for r in records) for key in
                      ("callbacks_seen", "successful_inserts", "elements_initialized", "distance_calls", "user_cpu_us", "system_cpu_us")}
            totals.update(cpu_seconds=config["rows"]*scale/1e6, level_hist=[config["rows"]]+[0]*63,
                          max_participant_elapsed_seconds=max(counts)*scale/1e6)
            summary["warmups" if warmup else "rows"].append({"panel": panel, "scene": scene, "condition": condition,
                "repeat": repeat, "warmup": warmup, "position": position, "source": source,
                "config": config, "validation": "passed", "command_returncode": 0, "workers": 2,
                "image": condition, "command_seconds": float(scale), "civil_wall_seconds": float(scale),
                "started_epoch": float(1000+position), "resources_before": {"power_source": "AC"},
                "resources_after": {"power_source": "AC"}, "index_oid": 123, "index_bytes": 8192*scale,
                "spill_after_tuples": None if scene == "no-spill" else (0 if scene == "immediate-spill" else 100),
                "internal_timing": {"status": "complete" if condition == "on" else "not_requested"},
                "work": {"scope": "scan_and_insert", "records": records, "totals": totals}})
    audit = {"audit_status": "verified", "summary_sha256": "s", "protocol_sha256": "p", "formal_count": 36, "warmup_count": 18}
    result = compute(summary, protocol, audit, "s", "p")
    require(len(result["groups"]) == 9 and len(result["repeat_pairs"]) == 18, "selftest coverage")
    for pair in result["repeat_pairs"]:
        for key in ("sql_seconds", "scan_cpu_seconds", "distance_calls"):
            require(pair["changes"][key]["ratio"] == 2, "selftest known doubled work ratio")
        require(pair["changes"]["cpu_nanoseconds_per_distance"]["ratio"] == 1, "selftest constant CPU/distance")
    for corr in result["mixed_condition_scene_correlations"]:
        require(math.isclose(corr["log_sql_log_scan_cpu"]["pearson_r"], 1), "selftest exact log relation")
    changed = copy.deepcopy(summary)
    changed["warmups"][0]["command_seconds"] = changed["warmups"][0]["civil_wall_seconds"] = 1e8
    require(compute(changed, protocol, audit, "s", "p")["groups"] == result["groups"], "warmups leaked into stats")
    for field, value in (("status", "running"), ("rows", summary["rows"][:-1]),
                         ("rows", [summary["rows"][0]]+summary["rows"][:-1])):
        bad = {**summary, field: value}
        try:
            compute(bad, protocol, audit, "s", "p")
        except AnalysisError:
            pass
        else:
            raise AssertionError("invalid input accepted")
    with tempfile.TemporaryDirectory(prefix="mechanism-analysis-selftest-") as temp:
        input_dir, output_dir = Path(temp)/"input", Path(temp)/"output"
        input_dir.mkdir()
        raw_summary, raw_protocol = json.dumps(summary).encode(), json.dumps(protocol).encode()
        audit.update(summary_sha256=sha(raw_summary), protocol_sha256=sha(raw_protocol))
        for name, data in (("summary.json", raw_summary), ("protocol.json", raw_protocol),
                           ("independent-audit.json", json.dumps(audit).encode())):
            (input_dir/name).write_bytes(data)
        analyze(input_dir, output_dir)
        require((output_dir/"analysis.json").exists() and (output_dir/"report.md").exists(), "selftest output")
        for target in (output_dir, input_dir/"forbidden"):
            try:
                analyze(input_dir, target)
            except AnalysisError:
                pass
            else:
                raise AssertionError("unsafe output accepted")
        audit["summary_sha256"] = "wrong"
        (input_dir/"independent-audit.json").write_text(json.dumps(audit))
        try:
            analyze(input_dir, Path(temp)/"bad-audit-output")
        except AnalysisError:
            require(not (Path(temp)/"bad-audit-output").exists(), "failed validation created output")
        else:
            raise AssertionError("unbound audit accepted")
    print("Synthetic selftest passed: all groups/pairs, exact ratios, correlation, warmup exclusion, rejection and output guards.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_dir", type=Path, nargs="?")
    parser.add_argument("output_dir", type=Path, nargs="?")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        require(args.input_dir is None and args.output_dir is None, "self-test takes no evidence paths")
        selftest()
        return
    require(args.input_dir is not None and args.output_dir is not None, "input_dir and new output_dir required")
    result = analyze(args.input_dir, args.output_dir)
    print(json.dumps({"status": result["status"], "groups": result["group_count"],
                      "repeat_pairs": result["repeat_pair_count"], "output": str(args.output_dir.resolve())}))


if __name__ == "__main__":
    main()
