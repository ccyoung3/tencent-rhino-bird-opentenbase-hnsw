#!/usr/bin/env python3
"""Snapshot-specific offline verification. Does not start databases or write Git.

--freeze records executable inputs and unit tests before formal measurements.
Without --freeze, independently recomputes raw evidence and writes audit.json.
"""
import argparse
import hashlib
import json
import math
import platform
import random
import statistics
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
TOOLS = ROOT / "experiments/hnsw_build"
RESULTS = TOOLS / "results"


def read(p):
    return json.loads(p.read_text())


def sha(p):
    with p.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def near(a, b):
    assert math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12), (a, b)


def source_identity():
    old = read(ROOT / "dev/snapshots/20260906-build-timing/validated-manifest.json")
    for n, s in old["sha256"].items():
        if n.startswith("pgvector/"):
            assert sha(ROOT / n) == s, n
    diff = subprocess.check_output(["git", "-C", str(ROOT / "pgvector"), "diff", "HEAD", "--binary"])
    assert hashlib.sha256(diff).hexdigest() == "99da7d1050501be3d8060989511f26c39f0571e0a14c1d09a809c4a1fbf2bcc2"
    assert not subprocess.check_output(["git", "-C", str(ROOT / "OpenTenBase"), "status", "--porcelain"])
    previous = read(ROOT / "dev/snapshots/20260910-glove/audit.json")
    permitted_docs = {"README.md", "experiments/hnsw_build/README.md", "experiments/hnsw_build/results/README.md",
                      "docs/2026-09-04-frozen-snapshot-review.md", "experiments/hnsw_build/.gitignore"}
    changed = [n for n, s in previous["sha256"].items() if sha(ROOT / n) != s]
    assert set(changed) <= permitted_docs, changed
    return {"core_unchanged": True, "previous_evidence_and_tooling_unchanged": True,
            "intentionally_updated_old_document_paths": changed}


def freeze():
    assert not (HERE / "start-manifest.json").exists(), "do not overwrite frozen start"
    identity = source_identity()
    paths = sorted(TOOLS.glob("*.py")) + [TOOLS / "requirements-glove.txt", ROOT / "dev/compose.yml",
             ROOT / "docs/2026-09-10-observer-recall-overhead.md"]
    with tarfile.open(HERE / "tooling-at-start.tar.gz", "x:gz") as archive:
        for p in paths:
            archive.add(p, arcname=str(p.relative_to(ROOT)))
    test = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", str(TOOLS), "-p", "test_*.py", "-v"],
                          capture_output=True, text=True)
    (HERE / "python-tests.log").write_text(test.stdout + test.stderr)
    assert test.returncode == 0 and "skipped=" not in test.stderr
    result = {"frozen_at_utc": datetime.now(timezone.utc).isoformat(), "identity": identity,
              "unit_test_returncode": test.returncode,
              "sha256": {str(p.relative_to(ROOT)): sha(p) for p in paths},
              "archive_sha256": sha(HERE / "tooling-at-start.tar.gz")}
    (HERE / "start-manifest.json").write_text(json.dumps(result, indent=2) + "\n")
    print("Inputs frozen; unit tests passed without skips")


def nodes(plan):
    yield plan
    for child in plan.get("Plans", []):
        yield from nodes(child)


def query_audit(folder, ids, efs, data, seed):
    s, truth = read(folder / "summary.json"), read(folder / "ground-truth.json")
    assert s["query_ids"] == ids and s["repetitions"] == 3 and s["k"] == 10 and s["target"] == .95
    assert [r["query_id"] for r in truth["exact_checks"]] == ids[:10]
    for check in truth["exact_checks"]:
        assert check["strict_ids_match"] or check["boundary_equivalent_ids"]
        assert any(n["Node Type"] == "Seq Scan" for n in nodes(check["plan"]["Plan"]))
    for q in ids:
        assert truth["ids"][str(q)] == (data["neighbors"][q, :10].astype("int64") + 1).tolist()
    rows = [json.loads(line) for line in (folder / "measurements.jsonl").read_text().splitlines()]
    tasks = [(rep, ef, q) for rep in range(1, 4) for ef in efs for q in ids]
    random.Random(seed).shuffle(tasks)
    assert [(r["repetition"], r["ef_search"], r["query_id"]) for r in rows] == tasks
    for r in rows:
        assert len(r["neighbors"]) == len(set(r["neighbors"])) == 10
        assert all(1 <= n <= 1183514 for n in r["neighbors"])
        assert math.isfinite(r["execution_ms"]) and r["execution_ms"] >= 0
        near(r["recall_at_k"], len(set(r["neighbors"]) & set(truth["ids"][str(r["query_id"])])) / 10)
    for aggregate in s["by_ef_search"]:
        ef = aggregate["ef_search"]
        group = [r for r in rows if r["ef_search"] == ef]
        assert aggregate["measurements"] == len(group) == len(ids) * 3
        assert aggregate["unique_queries"] == len(ids)
        near(aggregate["mean_recall"], statistics.mean(r["recall_at_k"] for r in group))
        near(aggregate["minimum_recall"], min(r["recall_at_k"] for r in group))
        times = sorted(r["execution_ms"] for r in group)
        near(aggregate["p50_execution_ms"], statistics.median(times))
        pos = (len(times) - 1) * .95; lo, hi = math.floor(pos), math.ceil(pos)
        near(aggregate["p95_execution_ms"], times[lo] + (times[hi] - times[lo]) * (pos - lo))
        assert aggregate["below_target"] == (aggregate["mean_recall"] < .95)
        assert any(n.get("Index Name") == "items_embedding_hnsw_idx" for n in nodes(s["plans"][str(ef)]["Plan"]))
    return len(rows)


def recall_audit(folder):
    import h5py
    s, p = read(folder / "summary.json"), read(folder / "protocol.json")
    assert s["status"] == "passed" and not p["smoke"]
    shuffled = list(range(10000)); random.Random(20260909).shuffle(shuffled)
    ids = {"tuning": shuffled[:200], "validation": shuffled[1200:2200]}
    assert p["query_ids"] == ids and not set(ids["validation"]) & set(shuffled[:1200])
    assert p["configs"] == [[16, 64], [16, 128], [32, 128]] and p["ef_candidates"] == [40, 100, 200, 400, 800, 1000]
    dataset = ROOT / "data/cache/glove-100-angular/glove-100-angular.hdf5"
    assert sha(dataset) == "544af1d5e84e112cd4749571dcfd8ca109818a572f850af75a3a09e093a953c4"
    count, selected = 0, None
    with h5py.File(dataset, "r") as data:
        for i, c in enumerate(s["candidates"]):
            assert [c["m"], c["ef_construction"]] == p["configs"][i] and selected is None
            b = c["build"]
            assert b == read(folder / c["source"] / "build/summary.json")
            assert b["status"] == "passed" and b["build_command_returncode"] == 0
            assert b["internal_timing"]["status"] == "complete" and b["launched_parallel_workers"] == 2
            assert b["metadata"]["row_count"] == 1183514 and b["metadata"]["uses_hnsw_index"]
            assert b["parameters"]["maintenance_work_mem"] == "1792MB"
            assert b["provenance"]["container_image_id"] == "sha256:af1ee2f012f452048c080b591c5456e8a5a83fea77fb4df6e53f4d28ba395fc7"
            assert b["container_memory_limit_bytes"] == 6 * 2**30
            assert c["tuning"] == read(folder / c["source"] / "tuning/summary.json")
            if i:
                pre = read(folder / f"preflight-m{c['m']}-efc{c['ef_construction']}/build/summary.json")
                assert pre["status"] == "passed" and not pre["diagnostics"]["spill_detected"]
                assert pre["peak_container_memory_bytes"] <= 4 * 2**30
            count += query_audit(folder / c["source"] / "tuning", ids["tuning"], p["ef_candidates"], data, 20260909)
            passing = [r["ef_search"] for r in c["tuning"]["by_ef_search"] if r["mean_recall"] >= .95]
            if passing:
                selected = dict(m=c["m"], ef_construction=c["ef_construction"], ef_search=min(passing), source=c["source"])
        assert s["selected"] == selected
        choice = read(folder / "selection-before-validation.json")
        assert choice["selected"] == selected and choice["source"] == s["candidates"][-1]["source"]
        efs = sorted({40, 400, selected["ef_search"] if selected else 1000})
        assert choice["validation_efs"] == efs
        validation = folder / choice["source"] / "validation"
        assert list(folder.glob("m*/validation")) == [validation]
        count += query_audit(validation, ids["validation"], efs, data, 20260910)
        v = read(validation / "summary.json")
        assert v == s["evaluation"]["validation"]
        target = next(r for r in v["by_ef_search"] if r["ef_search"] == (selected["ef_search"] if selected else 1000))
        assert s["validation_target_met"] == (target["mean_recall"] >= .95)
    return dict(measurements_recomputed=count, independent_validation_queries=1000, selected=selected,
                validation_target_met=s["validation_target_met"], validation=v["by_ef_search"])


def overhead_audit(folder):
    s, p = read(folder / "summary.json"), read(folder / "protocol.json")
    assert s["status"] == "passed" and p["blocks_per_scenario"] == 12 and not p["smoke"]
    assert len(s["rows"]) == 192 and len(s["warmups"]) == 96
    expected = []
    scenes = [(0, False), (0, True), (2, False), (2, True)]
    for block in range(12):
        for workers, spill in scenes[block % 4:] + scenes[:block % 4]:
            new = ["new_off", "new_on", "new_observed"]
            new = new[block % 3:] + new[:block % 3]
            variants = ["old_off"] + new if block % 2 == 0 else new + ["old_off"]
            expected.extend((block, workers, spill, v) for v in variants)
    assert [(r["block"], r["workers"], r["spill"], r["variant"]) for r in s["rows"]] == expected
    assert len({r["source"] for r in s["rows"] + s["warmups"]}) == 288
    for row in s["rows"] + s["warmups"]:
        raw = read(folder / row["source"] / "measurement.json")
        assert raw == {k: v for k, v in row.items() if k not in ("block", "source")}
        assert row["command_returncode"] == 0 and math.isfinite(row["command_seconds"]) and row["command_seconds"] > 0
        text = (folder / row["source"] / "build.stderr.txt").read_text()
        assert ("graph no longer fits" in text) == row["spill"]
        assert ("using 2 parallel workers" in text) == (row["workers"] == 2)
        assert ("hnsw build timing:" in text) == (row["variant"] in ("new_on", "new_observed"))
        provenance = read((folder / row["source"]).parent / "provenance.json")
        assert provenance["container_image_id"] == p["images"][row["image_variant"]]
    assert len(s["groups"]) == 12
    for group in s["groups"]:
        rows = [r for r in s["rows"] if (r["workers"], r["spill"]) == (group["workers"], group["spill"])]
        by = {(r["block"], r["variant"]): r for r in rows}
        assert len(by) == len(rows) == 48
        numerator, denominator = {"dormant_timing": ("new_off", "old_off"), "enabled_timing": ("new_on", "new_off"),
                                  "observer": ("new_observed", "new_on")}[group["effect"]]
        ratios = [by[b, numerator]["command_seconds"] / by[b, denominator]["command_seconds"] for b in range(12)]
        assert ratios == group["paired_ratios"]
        near(group["median_change_percent"], (statistics.median(ratios) - 1) * 100)
        near(group["upper_bound"]["upper_ratio"], sorted(ratios)[9])
        assert group["upper_bound"]["rank"] == 10
        near(group["upper_bound"]["coverage"], sum(math.comb(12, k) for k in range(10)) / 4096)
        verdict = "supported_below_reference" if sorted(ratios)[9] < 1.05 else "not_established"
        if group["effect"] == "observer":
            coverage = 0
            for r in rows:
                if r["variant"] != "new_observed":
                    continue
                observed = r["observer"].get("observation", {})
                if observed:
                    assert observed == read(folder / r["source"] / "observer/summary.json")
                    assert observed["build_outcome"] == "unknown"
                coverage += bool(observed.get("phases")) and observed.get("samples", 0) > 0
            assert coverage == group["observer_runs_with_progress"]
            if coverage != 12:
                verdict = "insufficient_observation_coverage"
        assert group["verdict"] == verdict
    return dict(formal_measurements=192, warmups=96, groups=s["groups"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--record-help-amendment", action="store_true")
    for n in ("recall", "overhead", "observer"):
        parser.add_argument("--" + n)
    args = parser.parse_args()
    if args.freeze:
        freeze(); return
    if args.record_help_amendment:
        start = read(HERE / "start-manifest.json")
        name = "experiments/hnsw_build/bounded_overhead.py"
        assert not (HERE / "help-amendment.json").exists()
        with tarfile.open(HERE / "tooling-at-start.tar.gz") as archive:
            original = archive.extractfile(name).read().decode()
        expected = original.replace("def main():\n    from psycopg import sql\n", "def main():\n")
        expected = expected.replace("    args = parser.parse_args()\n", "    args = parser.parse_args()\n    from psycopg import sql\n")
        assert (ROOT / name).read_text() == expected, "only lazy optional import is permitted"
        with tarfile.open(HERE / "overhead-help-amendment.tar.gz", "x:gz") as archive:
            archive.add(ROOT / name, arcname=name)
        amendment = dict(recorded_at_utc=datetime.now(timezone.utc).isoformat(),
            reason="Move psycopg import after argument parsing so --help works without optional dependencies; no measurement changes. Recorded before formal overhead starts.",
            before_sha256={name: start["sha256"][name]}, sha256={name: sha(ROOT / name)},
            archive_sha256=sha(HERE / "overhead-help-amendment.tar.gz"))
        (HERE / "help-amendment.json").write_text(json.dumps(amendment, indent=2) + "\n")
        print("Exact import-only amendment archived"); return
    assert all((args.recall, args.overhead, args.observer)), "three evidence directory names required"
    folders = [RESULTS / name for name in (args.recall, args.overhead, args.observer)]
    assert all(f.parent == RESULTS and f.is_dir() for f in folders)
    start = read(HERE / "start-manifest.json")
    assert sha(HERE / "tooling-at-start.tar.gz") == start["archive_sha256"]
    amendment = read(HERE / "help-amendment.json")
    assert sha(HERE / "overhead-help-amendment.tar.gz") == amendment["archive_sha256"]
    overhead_started = datetime.strptime(args.overhead.split("-bounded-")[0], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    assert datetime.fromisoformat(amendment["recorded_at_utc"]) < overhead_started
    for n, s in (start["sha256"] | amendment["sha256"]).items():
        if n.endswith(".py") or n.endswith(".txt") or n.endswith(".yml"):
            assert sha(ROOT / n) == s, n
    for f in folders:
        p = read(f / ("summary.json" if f == folders[2] else "protocol.json"))
        for n, s in p["tooling_sha256"].items():
            assert sha(TOOLS / n) == s, n
        for cleanup in f.rglob("cleanup.json"):
            assert read(cleanup)["status"] == "complete", cleanup
    observer = read(folders[2] / "summary.json")
    assert observer["status"] == "passed" and len(observer["checks"]) == 11
    result = dict(status="passed", audited_at_utc=datetime.now(timezone.utc).isoformat(),
        scope="offline source/raw/aggregate verification; not human Review or rerun of C tests",
        identity=source_identity(), sources=[f.name for f in folders], observer_checks=observer["checks"],
        recall=recall_audit(folders[0]), overhead=overhead_audit(folders[1]))
    tests = {}
    for label, executable in (("venv", sys.executable), ("system", "python3")):
        test = subprocess.run([executable, "-m", "unittest", "discover", "-s", str(TOOLS), "-p", "test_*.py", "-v"],
                              capture_output=True, text=True)
        (HERE / f"python-tests-{label}.log").write_text(test.stdout + test.stderr)
        assert test.returncode == 0
        if label == "venv":
            assert "skipped=" not in test.stderr
        tests[label] = dict(returncode=test.returncode, summary=test.stderr.splitlines()[-4:])
    result["unit_tests"] = tests
    import h5py
    import numpy
    import psycopg
    result["audit_environment"] = {"scope": "observed at offline audit, not retroactive per-run attestation",
        "python": platform.python_version(), "machine": platform.machine(),
        "h5py": h5py.__version__, "numpy": numpy.__version__, "psycopg": psycopg.__version__}
    files = [p for f in folders for p in f.rglob("*") if p.is_file()]
    files += [p for p in HERE.iterdir() if p.is_file() and p.name != "audit.json"]
    files += [ROOT / n for n in start["sha256"] if n.endswith((".py", ".txt", ".yml"))]
    files += [ROOT / n for n in ("README.md", "docs/2026-09-02-project-brief.md",
        "docs/2026-09-04-frozen-snapshot-review.md", "docs/2026-09-10-observer-recall-overhead.md",
        "experiments/hnsw_build/README.md", "experiments/hnsw_build/results/README.md",
        "experiments/hnsw_build/.gitignore")]
    result["sha256"] = {str(p.relative_to(ROOT)): sha(p) for p in sorted(files)}
    (HERE / "audit.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "sha256"}, indent=2))


if __name__ == "__main__":
    main()
