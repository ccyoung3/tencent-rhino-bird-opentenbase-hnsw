#!/usr/bin/env python3
"""Offline audit of this dated GloVe evidence; no database, experiment, or Git writes.

Run with the project's optional GloVe environment. This is a snapshot-specific
check, not a general benchmark evaluator. Existing audit.json is regenerated.
"""
import hashlib
import json
import math
import random
import statistics
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path

import h5py
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
RESULTS = ROOT / "experiments/hnsw_build/results"
CASE = RESULTS / "20260909T135759Z-glove-formal-cases"
SNAPSHOT = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_text())


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def close(actual, expected):
    assert math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12), (actual, expected)


def nodes(plan):
    yield plan
    for child in plan.get("Plans", []):
        yield from nodes(child)


def main():
    protocol, comparison = read(CASE / "protocol.json"), read(CASE / "comparison.json")
    assert protocol["status"] == "passed"
    assert [[r["group"], r["repetition"]] for r in protocol["runs"]] == protocol["order"]
    sources = [r["directory"] for r in protocol["runs"]]
    assert len(sources) == len(set(sources)) == 6 and comparison["sources"] == sources
    frozen = read(ROOT / "dev/snapshots/20260906-build-timing/validated-manifest.json")
    core = {name: sha for name, sha in frozen["sha256"].items() if name.startswith("pgvector/")}
    for name, sha in core.items():
        assert digest(ROOT / name) == sha, name
    diff = subprocess.check_output(["git", "-C", str(ROOT / "pgvector"), "diff", "HEAD", "--binary"])
    diff_sha = hashlib.sha256(diff).hexdigest()
    assert diff_sha == frozen["sha256"]["dev/snapshots/20260906-build-timing/pgvector.patch"]
    assert not subprocess.check_output(["git", "-C", str(ROOT / "OpenTenBase"), "status", "--porcelain"])
    with tarfile.open(CASE / "tooling-at-start.tar.gz") as archive:
        archived = {m.name: hashlib.sha256(archive.extractfile(m).read()).hexdigest()
                    for m in archive.getmembers() if m.isfile()}
    for name, sha in protocol["tooling_sha256"].items():
        assert archived[name] == sha, name
    runs, phases = [], []
    for item in protocol["runs"]:
        s = read(RESULTS / item["directory"] / "summary.json")
        assert item["returncode"] == s["build_command_returncode"] == 0
        assert s["status"] == "passed" and s["cleanup"]["status"] == "complete"
        assert s["internal_timing"]["status"] == "complete"
        assert s["metadata"]["uses_hnsw_index"] and s["metadata"]["row_count"] == 1183514
        assert s["provenance"]["container_image_id"] == frozen["images"]["runtime"]
        assert s["provenance"]["pgvector_source"]["tracked_diff_sha256"] == diff_sha
        assert s["container_memory_limit_bytes"] == 6 * 2**30
        assert s["launched_parallel_workers"] == s["parameters"]["parallel_workers"] == 2
        assert s["parameters"]["maintenance_work_mem"] == protocol[item["group"] + "_memory"]
        assert s["parameters"]["m"] == 16 and s["parameters"]["ef_construction"] == 64
        assert s["parameters"]["sample_interval"] == .5 and s["parameters"]["build_timing"]
        assert s["parameters"]["operator_class"] == "vector_cosine_ops"
        if runs:
            for key in ("dataset", "python_dependencies", "glove_tooling_sha256", "provenance"):
                assert s[key] == runs[0][key], key
        hashes = s["provenance"]["experiment_tooling"]["sha256"] | {
            "experiments/hnsw_build/" + name: sha for name, sha in s["glove_tooling_sha256"].items()}
        for name, sha in hashes.items():
            assert digest(ROOT / name) == sha, name
            if Path(name).name in archived:
                assert archived[Path(name).name] == sha, name
        record = s["internal_timing"]["records"][0]
        marker = "hnsw build timing: "
        raw = [json.loads(line.split(marker, 1)[1]) for line in
               (RESULTS / item["directory"] / "build.stderr.txt").read_text().splitlines() if marker in line]
        assert len(raw) == 1
        for key, value in raw[0].items():
            assert record[key] == value, key
        position = 0
        for phase in record["phases"]:
            if phase["start_us"] is None:
                assert phase["end_us"] is None and record["durations_us"][phase["phase"]] is None
                continue
            assert phase["start_us"] == position <= phase["end_us"]
            assert phase["end_us"] - position == record["durations_us"][phase["phase"]]
            position = phase["end_us"]
        assert position == record["total_us"]
        phases.append({"source": item["directory"], "total_us": position,
                       "spill_after_tuples": s["diagnostics"]["spill_after_tuples"],
                       "disk_insert_fraction": (record["durations_us"]["disk_insert"] or 0) / position})
        runs.append(s)
    for memory, group in comparison["groups"].items():
        selected = [s for s in runs if s["parameters"]["maintenance_work_mem"] == memory]
        elapsed = [s["build_elapsed_seconds"] for s in selected]
        assert group["n"] == len(selected) == 3
        close(group["median_seconds"], statistics.median(elapsed))
        close(group["minimum_seconds"], min(elapsed)); close(group["maximum_seconds"], max(elapsed))
        assert group["spill_runs"] == sum(s["diagnostics"]["spill_detected"] for s in selected)
        assert group["median_peak_container_bytes"] == statistics.median(s["peak_container_memory_bytes"] for s in selected)
        assert group["index_bytes_range"] == [min(s["metadata"]["index_bytes"] for s in selected), max(s["metadata"]["index_bytes"] for s in selected)]
    dataset = ROOT / "data/cache/glove-100-angular/glove-100-angular.hdf5"
    assert digest(dataset) == runs[0]["dataset"]["sha256"]
    evaluation = runs[4]["glove_evaluation"]
    assert sum("glove_evaluation" in s for s in runs) == 1
    shuffled = list(range(10000)); random.Random(20260909).shuffle(shuffled)
    ids = {"tuning": shuffled[:200], "validation": shuffled[200:1200]}
    counts, residual = {}, 0.0
    with h5py.File(dataset, "r") as data:
        for split, query_ids in ids.items():
            folder = RESULTS / sources[4] / split
            saved, truth = read(folder / "summary.json"), read(folder / "ground-truth.json")
            assert saved == evaluation[split] and saved["query_ids"] == query_ids
            assert saved["repetitions"] == 3 and saved["k"] == 10 and saved["target"] == .95
            assert len(truth["exact_checks"]) == 10
            assert [c["query_id"] for c in truth["exact_checks"]] == query_ids[:10]
            for check in truth["exact_checks"]:
                assert check["strict_ids_match"]
                assert any(n["Node Type"] == "Seq Scan" for n in nodes(check["plan"]["Plan"]))
            for q in query_ids:
                expected = data["neighbors"][q, :10].astype("int64") + 1
                assert truth["ids"][str(q)] == expected.tolist()
                base = np.stack([data["train"][i - 1] for i in expected]).astype("float64")
                vector = data["test"][q].astype("float64")
                distances = 1 - base @ vector / (np.linalg.norm(base, axis=1) * np.linalg.norm(vector))
                residual = max(residual, float(np.abs(distances - data["distances"][q, :10]).max()))
            rows = [json.loads(line) for line in (folder / "measurements.jsonl").read_text().splitlines()]
            efs = protocol["ef_candidates"] if split == "tuning" else [10, 40, 400]
            tasks = [(rep, ef, q) for rep in range(1, 4) for ef in efs for q in query_ids]
            random.Random(20260909 + (split == "validation")).shuffle(tasks)
            assert [(r["repetition"], r["ef_search"], r["query_id"]) for r in rows] == tasks
            for row in rows:
                assert len(row["neighbors"]) == len(set(row["neighbors"])) == 10
                assert all(1 <= n <= 1183514 for n in row["neighbors"])
                assert math.isfinite(row["execution_ms"]) and row["execution_ms"] >= 0
                close(row["recall_at_k"], len(set(row["neighbors"]) & set(truth["ids"][str(row["query_id"])])) / 10)
            for aggregate in saved["by_ef_search"]:
                ef = aggregate["ef_search"]
                group = [r for r in rows if r["ef_search"] == ef]
                times = sorted(r["execution_ms"] for r in group)
                assert aggregate["measurements"] == len(group) == len(query_ids) * 3
                assert aggregate["unique_queries"] == len({r["query_id"] for r in group}) == len(query_ids)
                close(aggregate["mean_recall"], statistics.mean(r["recall_at_k"] for r in group))
                close(aggregate["minimum_recall"], min(r["recall_at_k"] for r in group))
                close(aggregate["p50_execution_ms"], statistics.median(times))
                pos = (len(times) - 1) * .95; lo, hi = math.floor(pos), math.ceil(pos)
                close(aggregate["p95_execution_ms"], times[lo] + (times[hi] - times[lo]) * (pos - lo))
                assert aggregate["below_target"] == (aggregate["mean_recall"] < .95)
                assert any(n.get("Index Name") == "items_embedding_hnsw_idx" for n in nodes(saved["plans"][str(ef)]["Plan"]))
            counts[split] = {"unique_queries": len(query_ids), "measurements": len(rows), "sql_exact_checks": 10}
    assert residual <= 2e-6 and not set(ids["tuning"]) & set(ids["validation"])
    assert evaluation["selected_ef_search"] is None and runs[4]["selection"]["selected_ef_search"] is None
    assert all(row["below_target"] for row in evaluation["tuning"]["by_ef_search"])
    e2e = read(RESULTS / "20260910T014813Z-glove-e2e-verification/summary.json")
    assert e2e["status"] == "passed" and len(e2e["cases"]) == 3
    paths = list((ROOT / "experiments/hnsw_build").glob("*.py"))
    paths += list((ROOT / "experiments/hnsw_build").glob("*glove*.txt"))
    paths += [p for d in RESULTS.glob("*-glove-*") for p in d.rglob("*") if p.is_file()]
    paths += [p for p in SNAPSHOT.iterdir() if p.is_file() and p.name != "audit.json"]
    paths += [ROOT / p for p in ("README.md", ".gitignore", "experiments/hnsw_build/.gitignore",
        "experiments/hnsw_build/README.md", "experiments/hnsw_build/results/README.md",
        "docs/2026-09-09-glove-validation.md", "docs/2026-09-04-frozen-snapshot-review.md")]
    result = {"status": "passed", "audited_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "offline identity/raw-measurement/aggregate checks, not independent human review or new C regression",
        "formal_sources": sources, "groups": comparison["groups"], "phases": phases,
        "query_checks": counts, "maximum_ground_truth_distance_residual": residual,
        "selected_ef_search": None, "recall_target_met": False, "e2e": e2e,
        "pgvector_tracked_diff_sha256": diff_sha, "unchanged_core_sha256": core,
        "sha256": {str(p.relative_to(ROOT)): digest(p) for p in sorted(set(paths))}}
    (SNAPSHOT / "audit.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k not in ("sha256", "unchanged_core_sha256", "e2e")}, indent=2))


if __name__ == "__main__":
    main()
