#!/usr/bin/env python3
"""Supplement cold-start runs with counterbalanced same-backend on/off pairs."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments/hnsw_build"))
import run as experiment
import timing


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = ROOT / "experiments/hnsw_build/results" / f"{stamp}-timing-switch-paired"
    output.mkdir()
    os.environ["HNSW_IMAGE"] = "opentenbase-pg18-pgvector:timing-v1-seed42-arm64"
    os.environ["COMPOSE_PROJECT_NAME"] = f"hnswswitch-{stamp.lower()}-{os.getpid()}"
    args = SimpleNamespace(rows=20000, dimensions=32, seed=.42, parallel_workers=0,
                           keep_data=False, isolated=True, stop_after=False)
    result_summary = {"status": "failed", "protocol": "same backend per group; reused data; no polling; psql timing",
                      "rows": args.rows, "dimensions": args.dimensions, "runs": []}
    try:
        experiment.run_command(experiment.compose_command("up", "-d", "--wait", "--wait-timeout", "60"))
        result_summary["provenance"] = experiment.collect_provenance()
        experiment.create_dataset(args)
        for workers in (0, 2):
            for spill in (False, True):
                name = f"w{workers}-{'low' if spill else 'high'}"
                memory = ("4MB" if workers else "1MB") if spill else "128MB"
                setup = f"""SET client_min_messages = DEBUG1;
SET maintenance_work_mem = '{memory}';
SET max_parallel_maintenance_workers = {workers};
SET max_parallel_workers = 4;
SET min_parallel_table_scan_size = 0;
ALTER TABLE {experiment.TABLE} SET (parallel_workers = {workers});
"""
                script = [setup]
                cases = []
                # Pair zero is explicitly warmup, retained but not summarized.
                for pair in range(6):
                    for enabled in ((False, True) if pair % 2 == 0 else (True, False)):
                        label = f"{name}-p{pair}-{'on' if enabled else 'off'}"
                        cases.append((label, pair, enabled))
                        script.append(f"""\\echo BEGIN_{label}
\\warn BEGIN_{label}
SET hnsw.build_timing = {'on' if enabled else 'off'};
DROP INDEX IF EXISTS {experiment.INDEX};
\\timing on
CREATE INDEX items_embedding_hnsw_idx ON {experiment.TABLE}
USING hnsw (embedding vector_l2_ops) WITH (m = 16, ef_construction = 64);
\\timing off
\\echo END_{label}
\\warn END_{label}
""")
                sql = "\n".join(script)
                (output / f"{name}.psql").write_text(sql)
                command = experiment.psql_command("")[:-2] + ["-f", "-"]
                proc = subprocess.run(command, cwd=ROOT, text=True, input=sql, capture_output=True)
                (output / f"{name}.stdout.txt").write_text(proc.stdout)
                (output / f"{name}.stderr.txt").write_text(proc.stderr)
                if proc.returncode:
                    raise RuntimeError(proc.stderr)
                for label, pair, enabled in cases:
                    stdout = proc.stdout.split(f"BEGIN_{label}\n", 1)[1].split(f"END_{label}", 1)[0]
                    stderr = proc.stderr.split(f"BEGIN_{label}\n", 1)[1].split(f"END_{label}", 1)[0]
                    values = re.findall(r"^Time: ([0-9.]+) ms", stdout, re.MULTILINE)
                    assert len(values) == 1, stdout
                    assert ("graph no longer fits" in stderr) == spill
                    actual = re.search(r"using (\d+) parallel workers", stderr)
                    assert (int(actual[1]) if actual else 0) == workers
                    internal = timing.parse_build_timing(stderr, requested=enabled, command_returncode=0)
                    assert internal["status"] == ("complete" if enabled else "not_requested")
                    result_summary["runs"].append({"label": label, "workers": workers, "spill": spill,
                        "pair": pair, "warmup": pair == 0, "enabled": enabled,
                        "command_ms": float(values[0]), "internal_timing": internal})
                print(f"{name}: warmup + five on/off pairs complete", flush=True)
                (output / "partial.json").write_text(json.dumps(result_summary, indent=2) + "\n")
        groups = []
        for workers in (0, 2):
            for spill in (False, True):
                rows = [r for r in result_summary["runs"] if r["workers"] == workers and r["spill"] == spill and not r["warmup"]]
                pairs = []
                for pair in range(1, 6):
                    off = next(r["command_ms"] for r in rows if r["pair"] == pair and not r["enabled"])
                    on = next(r["command_ms"] for r in rows if r["pair"] == pair and r["enabled"])
                    pairs.append((on / off - 1) * 100)
                group = {"workers": workers, "spill": spill,
                         "paired_change_percent": pairs, "median_paired_change_percent": statistics.median(pairs)}
                for enabled in (False, True):
                    values = [r["command_ms"] for r in rows if r["enabled"] == enabled]
                    group["on" if enabled else "off"] = {
                        "n": len(values), "median_ms": statistics.median(values),
                        "min_ms": min(values), "max_ms": max(values)}
                groups.append(group)
        result_summary.update(status="complete", groups=groups)
    except Exception as error:
        result_summary["error"] = str(error)
        raise
    finally:
        result_summary["cleanup"] = experiment.cleanup_experiment(args)
        (output / "summary.json").write_text(json.dumps(result_summary, indent=2) + "\n")
        print(output, flush=True)


if __name__ == "__main__":
    main()
