#!/usr/bin/env python3
"""Paired three-way timing overhead checks; run with no other heavy jobs."""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
VARIANTS = {
    "previous_off": ("diagnostics-v2-seed42-arm64", False),
    "candidate_off": ("timing-v1-seed42-arm64", False),
    "candidate_on": ("timing-v1-seed42-arm64", True),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=20000)
    parser.add_argument("--dimensions", type=int, default=32)
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = ROOT / "experiments/hnsw_build/results" / f"{stamp}-timing-overhead"
    output.mkdir()
    runs = []
    groups = defaultdict(list)
    # Rotate order to reduce systematic position effects. Each run has a fresh
    # database volume; SQL data seed is fixed. HNSW_MEMORY fixes serial topology,
    # but parallel topology remains scheduling-dependent.
    variants = list(VARIANTS)
    for repeat in range(3):
        order = variants[repeat:] + variants[:repeat]
        for workers in (0, 2):
            for spill in (False, True):
                memory = ("4MB" if workers else "1MB") if spill else "128MB"
                for variant in order:
                    image, enabled = VARIANTS[variant]
                    label = f"timing-overhead-w{workers}-{'low' if spill else 'high'}-{variant}-r{repeat+1}"
                    command = [sys.executable, str(ROOT / "experiments/hnsw_build/run.py"),
                               "--isolated", "--image", "opentenbase-pg18-pgvector:" + image,
                               "--rows", str(args.rows), "--dimensions", str(args.dimensions),
                               "--parallel-workers", str(workers), "--maintenance-work-mem", memory,
                               "--sample-interval", "0.2", "--label", label]
                    if enabled:
                        command.append("--build-timing")
                    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
                    if result.returncode:
                        raise RuntimeError(result.stdout + result.stderr)
                    path = Path(result.stdout.strip().splitlines()[-1])
                    summary = json.loads((path / "summary.json").read_text())
                    assert summary["status"] == "passed"
                    assert summary["cleanup"]["status"] == "complete"
                    assert summary["diagnostics"]["spill_detected"] == spill
                    assert summary["launched_parallel_workers"] == workers
                    if enabled:
                        assert summary["internal_timing"]["status"] == "complete"
                        assert summary["internal_timing"]["records"][0]["spill"] == spill
                    row = {"path": str(path.relative_to(ROOT)), "variant": variant,
                           "workers": workers, "spill": spill, "repeat": repeat + 1,
                           "seconds": summary["build_elapsed_seconds"],
                           "index_bytes": summary["metadata"]["index_bytes"],
                           "peak_memory_delta_bytes": summary["peak_memory_delta_bytes"],
                           "internal_timing": summary["internal_timing"],
                           "image_id": summary["provenance"]["container_image_id"]}
                    runs.append(row)
                    groups[(workers, spill, variant)].append(row)
                    # Keep a resumable evidence index, even if a later run fails.
                    (output / "runs.json").write_text(json.dumps(runs, indent=2) + "\n")
                    print(json.dumps({k: v for k, v in row.items() if k != "internal_timing"}), flush=True)
    aggregate = []
    for (workers, spill, variant), values in groups.items():
        times = [v["seconds"] for v in values]
        aggregate.append({"workers": workers, "spill": spill, "variant": variant,
                          "n": len(times), "median_seconds": statistics.median(times),
                          "min_seconds": min(times), "max_seconds": max(times),
                          "index_sizes": sorted(set(v["index_bytes"] for v in values))})
    (output / "summary.json").write_text(json.dumps({
        "status": "complete", "rows": args.rows, "dimensions": args.dimensions,
        "groups": aggregate, "runs": runs,
        "limits": ["Three repeats are a small local screen, not a statistical equivalence test.",
                   "HNSW_MEMORY fixes serial topology only; parallel scheduling remains variable.",
                   "Do not mix this Docker benchmark with CentOS compatibility timings."]}, indent=2) + "\n")
    print(output, flush=True)


if __name__ == "__main__":
    main()
