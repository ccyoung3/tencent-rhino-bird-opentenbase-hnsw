#!/usr/bin/env python3
"""Source-attested A/A stability gate and randomized total-diagnostic overhead acceptance."""
import argparse
import hashlib
import itertools
import json
import math
import random
import re
import statistics
import tarfile
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import acceptance_stack
import observe
import run
import timing

SCENES = [(0, False), (0, True), (2, False), (2, True)]
CONDITIONS = ["baseline", "off", "on", "observed"]
SNAPSHOT = run.PROJECT_ROOT / "dev/snapshots/20260911-overhead-acceptance"


def read(path):
    return json.loads(path.read_text())


def dump(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validate_host(before, after, elapsed, wall_elapsed, require_ac):
    if not all(math.isfinite(v) and v > 0 for v in (elapsed, wall_elapsed)) or abs(wall_elapsed-elapsed) > 1:
        raise RuntimeError('host suspension or clock discontinuity invalidated measurement')
    if require_ac and (before['power_source'], after['power_source']) != ('AC', 'AC'):
        raise RuntimeError('power source changed during performance measurement')


def upper(values, confidence):
    if not values or not all(math.isfinite(v) and v > 0 for v in values):
        raise ValueError("positive finite ratios required")
    cumulative = 0
    for rank in range(1, len(values)+1):
        cumulative += math.comb(len(values), rank-1) / 2**len(values)
        if cumulative >= confidence:
            return dict(ratio=sorted(values)[rank-1], rank=rank, coverage=cumulative)
    return dict(ratio=None, rank=None, coverage=None)


def schedule(panels, aa):
    if panels != (8 if aa else 24):
        raise ValueError("fixed panel count required")
    labels = ["aa_a", "aa_b"] if aa else CONDITIONS
    rng = random.Random(20260911 + int(aa))
    orders = {}
    for scene in SCENES:
        pool = list(itertools.permutations(labels)) * (4 if aa else 1)
        rng.shuffle(pool)
        orders[scene] = pool
    scenes = list(itertools.permutations(SCENES))
    rng.shuffle(scenes)
    return [dict(panel=p, scenes=[dict(workers=w, spill=s, order=orders[w, s][p]) for w, s in scenes[p]])
            for p in range(panels)]


def summarize(rows, panels, aa):
    labels = ["aa_a", "aa_b"] if aa else CONDITIONS
    expected = {(p, w, s, label) for p in range(panels) for w, s in SCENES for label in labels}
    keyed = {(r["panel"], r["workers"], r["spill"], r["condition"]): r for r in rows}
    if len(rows) != len(expected) or set(keyed) != expected:
        raise ValueError("missing or duplicate formal measurements")
    if any(not math.isfinite(r["command_seconds"]) or r["command_seconds"] <= 0 for r in rows):
        raise ValueError("positive finite command times required")
    groups = []
    for w, s in SCENES:
        for label in labels[1:]:
            baseline = labels[0]
            ratios = [keyed[p, w, s, label]["command_seconds"] / keyed[p, w, s, baseline]["command_seconds"]
                      for p in range(panels)]
            bound = upper(ratios, .95 if aa else 1-.05/12)
            lo = upper([1/r for r in ratios], .95)
            lower_ratio = 1/lo["ratio"] if lo["ratio"] is not None else None
            deviations = sorted(abs(r-1) for r in ratios)
            p90 = deviations[math.ceil(.9*len(deviations))-1]
            passing = bound["ratio"] is not None and bound["ratio"] < 1.05
            if aa:
                passing = passing and lower_ratio is not None and lower_ratio > .95 and p90 <= .10
            observed = [keyed[p,w,s,label].get("observer", {}).get("observation", {}) for p in range(panels)]
            coverage = sum(bool(o.get("phases")) and o.get("samples", 0) > 0 for o in observed)
            if label == "observed":
                passing = passing and coverage == panels
            groups.append(dict(workers=w, spill=s, condition=label, reference=baseline, panels=panels,
                ratios=ratios, median_change_percent=100*(statistics.median(ratios)-1), upper=bound,
                aa_lower_ratio=lower_ratio if aa else None, aa_p90_absolute_change=p90 if aa else None,
                observed_with_progress=coverage if label == "observed" else None,
                verdict="supported" if passing else "not_established"))
    return dict(groups=groups, all_supported=all(g["verdict"] == "supported" for g in groups))


def measure(replica, output, condition, workers, spill, warmup, *, require_ac=True):
    output.mkdir()
    enabled = condition in ("on", "observed")
    watched = condition == "observed" and not warmup
    table = "small" if spill else "large"
    conn = replica.connect()
    watcher = replica.connect(watcher=True) if watched else None
    notices, observation = [], {"attachment_probes": 0}
    stop = threading.Event()
    thread = None
    conn.execute("SET client_min_messages=DEBUG1; SET min_parallel_table_scan_size=0")
    conn.execute("SELECT set_config('maintenance_work_mem', %s, false)", (("4MB" if workers else "1MB") if spill else "256MB",))
    conn.execute("SELECT set_config('max_parallel_maintenance_workers', %s, false)", (str(workers),))
    if condition != "baseline":
        conn.execute("SELECT set_config('hnsw.build_timing', %s, false)", ("on" if enabled else "off",))
    conn.execute(f"ALTER TABLE hnsw_accept.{table} SET (parallel_workers={workers})")
    conn.execute("DROP INDEX IF EXISTS hnsw_accept.items_hnsw")
    conn.execute("CHECKPOINT")
    before = replica.counters()
    if require_ac and before['power_source'] != 'AC':
        raise RuntimeError('AC power required for performance measurement')
    def notice(diag):
        notices.append((diag.severity_nonlocalized or "NOTICE") + ": " + (diag.message_primary or "") +
                       ("\nDETAIL: " + diag.message_detail if diag.message_detail else ""))
    conn.add_notice_handler(notice)
    def watch():
        try:
            while not stop.is_set():
                state = observe.sample(watcher, conn.info.backend_pid)
                observation["attachment_probes"] += 1
                if state and state.get("phase"):
                    observation["observation"] = observe.observe(watcher, conn.info.backend_pid,
                        output / "observer", interval=1., duration=180., stop=stop)
                    break
                stop.wait(1.)
        except Exception as error:
            observation["error"] = type(error).__name__
    if watched:
        thread = threading.Thread(target=watch)
        thread.start()
    started = time.perf_counter()
    started_epoch = time.time()
    error, rc = None, 1
    try:
        conn.execute(f"CREATE INDEX items_hnsw ON hnsw_accept.{table} USING hnsw (embedding vector_l2_ops) WITH (m=16,ef_construction=64)")
        elapsed = time.perf_counter()-started
        wall_elapsed = time.time()-started_epoch
        rc = 0
    except BaseException as caught:
        elapsed = time.perf_counter()-started
        wall_elapsed = time.time()-started_epoch
        error = caught
    finally:
        stop.set()
        if thread:
            thread.join(timeout=5)
        conn.remove_notice_handler(notice)
        text = "\n".join(notices) + "\n"
        (output / "build.stderr.txt").write_text(text)
        item = dict(condition=condition, workers=workers, spill=spill, warmup=warmup, command_seconds=elapsed,
            started_epoch=started_epoch, civil_wall_seconds=wall_elapsed, require_ac=require_ac,
            command_returncode=rc, internal_timing=timing.parse_build_timing(text, requested=enabled, command_returncode=rc),
            observer=observation, resources_before=before, resources_after=replica.counters(), image=replica.image)
        if error:
            item["error"] = type(error).__name__ + ":" + (getattr(error, "sqlstate", None) or "")
        if rc == 0:
            item["index_bytes"] = conn.execute("SELECT pg_relation_size('hnsw_accept.items_hnsw')").fetchone()[0]
        dump(output / "measurement.json", item)
        conn.close()
        if watcher:
            watcher.close()
    if error:
        raise error
    validate_host(before, item['resources_after'], elapsed, wall_elapsed, require_ac)
    actual = re.search(r"using (\d+) parallel workers", text)
    assert (int(actual[1]) if actual else 0) == workers
    assert ("graph no longer fits" in text) == spill
    assert item["internal_timing"]["status"] == ("complete" if enabled else "not_requested")
    if watched:
        assert not thread.is_alive() and "error" not in observation
        assert observation.get('observation', {}).get('status') in ('stopped', 'ended_unconfirmed')
        assert observation.get("observation", {}).get("phases"), "observer must actually sample progress"
    return item


def render(result):
    lines = ["# 诊断开销验收", "", "流程状态：" + result["status"], "",
        "正式协议比较整套诊断相对原版pgvector；A/A只检查测量稳定性。", "",
        "| workers | spill | 条件 | 配对中位变化 | 单侧上界变化 | 判断 |",
        "|---:|---|---|---:|---:|---|"]
    for g in result.get("analysis", {}).get("groups", []):
        u = g["upper"]["ratio"]
        lines.append(f"| {g['workers']} | {g['spill']} | {g['condition']} | {g['median_change_percent']:+.2f}% | " +
                     (f"{100*(u-1):+.2f}%" if u is not None else "无有限上界") + f" | {g['verdict']} |")
    lines += ["", "- 正式12项采用Bonferroni控制单侧家族误差率≤5%，假定各配对面板独立；参考线5%。",
        "- 置信上界针对配对比值总体中位数，不是最坏单次开销或生产SLA。A/A不属于这项正式保证。",
        "- seed42为受控测试编译，固定串行随机数；并行拓扑仍可能变化。常规编译另外验功能。",
        "- 每个面板新建实例，每个条件相同次数预热/正式构建，每次构建新连接且先CHECKPOINT。",
        "- 仅使用本地测试实例，Linux客体CPU亲和性不是Mac物理核心独占；不保证所有宿主负载条件。",
        "- 原始异常和失败保留，not_established不能改写为通过。"]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("smoke", "aa", "formal"))
    parser.add_argument("--gate", type=Path)
    parser.add_argument("--affinity", choices=("0-3", "4-7", "0-9"), default="0-3")
    parser.add_argument("--scale", type=int, choices=(1, 2), default=1)
    args = parser.parse_args()
    aa = args.mode != "formal"
    panels = 8 if aa else 24
    build = read(SNAPSHOT / "build-manifest.json")
    assert build["status"] == "passed"
    images = {k: v["id"] for k,v in build["images"].items()}
    paths = [Path(__file__), Path(acceptance_stack.__file__), Path(observe.__file__), Path(timing.__file__), Path(run.__file__)]
    if not aa:
        if args.gate is None:
            parser.error("formal requires a completed A/A gate")
        gate = read(args.gate / "summary.json")
        prior = read(args.gate / "protocol.json")
        assert gate["status"] == "completed" and gate["analysis"]["all_supported"] and prior["mode"] == "aa"
        assert (prior["scale"], prior["affinity"], prior["images"]) == (args.scale, args.affinity, images)
        assert prior["sources"] == {p.name: sha(p) for p in paths}
        assert prior["common_build_manifest_sha256"] == sha(SNAPSHOT / "build-manifest.json")
        assert summarize(gate["rows"], 8, True) == gate["analysis"]
        for row in gate["rows"] + gate["warmups"]:
            raw = read(args.gate / row["source"] / "measurement.json")
            assert raw["command_seconds"] == row["command_seconds"] and raw["image"] == row["image"]
    output = run.RESULTS_ROOT / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-bounded-acceptance-" + args.mode)
    output.mkdir()
    ordered = schedule(panels, aa)
    if args.mode == "smoke":
        ordered = ordered[:1]
    protocol = dict(mode=args.mode, panels=len(ordered), scale=args.scale, affinity=args.affinity,
        large_rows=100000*args.scale, small_rows=30000*args.scale, dimensions=32, m=16, ef_construction=64,
        images=images, common_build_manifest_sha256=sha(SNAPSHOT / "build-manifest.json"),
        warmups_per_condition=1, formal_per_condition=1, schedule=ordered,
        gate_sha256=sha(args.gate / "summary.json") if args.gate else None,
        gate_directory=str(args.gate) if args.gate else None,
        acceptance="12 total-cost comparisons to unmodified pgvector, 5% median-ratio upper bound; Bonferroni FWER<=.05",
        aa_gate="per-scene upper95<1.05 and lower95>.95; empirical p90 absolute paired change <=10%",
        host_controls='AC required before/after every build; idle-sleep assertion; reject civil/monotonic gap >1s',
        sources={p.name: sha(p) for p in paths}, no_optional_stopping=True)
    dump(output / "protocol.json", protocol)
    with tarfile.open(output / "tooling-at-start.tar.gz", "x:gz") as archive:
        for path in paths:
            archive.add(path, arcname=path.name)
    result = dict(status="running", rows=[], warmups=[])
    print(output, flush=True)
    awake = acceptance_stack.keep_awake()
    awake.__enter__()
    try:
        if acceptance_stack.power_source() != 'AC':
            raise RuntimeError('AC power required before calibration or formal performance measurement')
        for step in ordered:
            number = step["panel"]
            selected = {label: images["candidate-seed42" if aa or label != "baseline" else "baseline-seed42"]
                        for label in (["aa_a", "aa_b"] if aa else CONDITIONS)}
            with acceptance_stack.panel(output / f"p{number:02d}", selected, large_rows=protocol["large_rows"],
                    small_rows=protocol["small_rows"], affinity=args.affinity) as replicas:
                for scene in step["scenes"]:
                    w, s = scene["workers"], scene["spill"]
                    for label in scene["order"]:
                        for warmup in (True, False):
                            path = replicas[label].folder / f"w{w}-s{int(s)}-{'warmup' if warmup else 'formal'}"
                            item = measure(replicas[label], path, "off" if aa else label, w, s, warmup)
                            row = {**item, "effective_condition": item["condition"], "condition": label, "panel": number, "source": str(path.relative_to(output))}
                            result["warmups" if warmup else "rows"].append(row)
                            dump(output / "summary.json", result)
                    print(f"Panel {number+1}/{len(ordered)}, workers={w}, spill={s} complete", flush=True)
        if args.mode != "smoke":
            result["analysis"] = summarize(result["rows"], panels, aa)
        result["status"] = "completed"
    except (Exception, KeyboardInterrupt) as error:
        result["status"] = "failed"
        result["error"] = type(error).__name__ + ":" + (getattr(error, "sqlstate", None) or "")
        result["error_locations"] = [{"file": f.filename.rsplit("/",1)[-1], "line": f.lineno} for f in traceback.extract_tb(error.__traceback__)]
    finally:
        awake.__exit__(None, None, None)
        dump(output / "summary.json", result)
        (output / "report.md").write_text(render(result))
    print(result["status"], flush=True)
    return 0 if result["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
