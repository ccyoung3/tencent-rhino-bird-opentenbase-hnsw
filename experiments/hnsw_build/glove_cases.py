#!/usr/bin/env python3
"""Preregister and run six isolated GloVe builds, plus one same-index recall case."""
import argparse
import json
import os
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import glove_report
import glove
import run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=1183514)
    parser.add_argument("--low-memory", required=True)
    parser.add_argument("--high-memory", required=True)
    args = parser.parse_args()
    if args.low_memory == args.high_memory:
        parser.error("two distinct memory settings required")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = run.RESULTS_ROOT / f"{stamp}-glove-formal-cases"
    output.mkdir(exist_ok=False)
    order = [("high", 1), ("low", 1), ("low", 2), ("high", 2), ("high", 3), ("low", 3)]
    protocol = {"status": "running", "rows": args.rows, "low_memory": args.low_memory,
                "high_memory": args.high_memory, "order": order, "runs": [],
                "recall_on": "high repetition 3 only; no rebuilding within recall case",
                "workers": 2, "sample_interval_seconds": .5, "build_timeout_ms": 1800000,
                "tuning_queries": 200, "validation_queries": 1000, "query_repetitions": 3,
                "ef_candidates": [10, 40, 100, 200, 400], "target": .95}
    protocol["tooling_sha256"] = {p.name: glove.file_sha256(p) for p in (
        Path(__file__), Path(glove_report.__file__))}
    def save():
        (output / "protocol.json").write_text(json.dumps(protocol, indent=2) + "\n")
    save()
    print(output, flush=True)
    try:
        for group, rep in order:
            memory = args.low_memory if group == "low" else args.high_memory
            command = [sys.executable, str(Path(__file__).with_name("glove_run.py")), "--rows", str(args.rows),
                       "--maintenance-work-mem", memory, "--label", f"glove-formal-{group}-r{rep}"]
            if group == "high" and rep == 3:
                command.append("--evaluate")
            print(f"Starting {group} repetition {rep} ({memory})", flush=True)
            log = output / f"{group}-r{rep}.log"
            with log.open("w") as stream:
                child = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT,
                                         cwd=run.PROJECT_ROOT, start_new_session=True)
                try:
                    returncode = child.wait()
                except KeyboardInterrupt:
                    # Signal Python only: it cancels its named backend and cleans
                    # its volume without first interrupting its Docker client.
                    os.kill(child.pid, signal.SIGINT)
                    child.wait(timeout=180)
                    raise
            first_line = log.read_text().splitlines()[0]
            run_path = Path(first_line)
            protocol["runs"].append({"group": group, "repetition": rep, "directory": run_path.name,
                                     "returncode": returncode, "command": command})
            save()
            if returncode != 0:
                raise RuntimeError(f"{group} r{rep} failed; inspect {log}")
            print(f"Finished {group} repetition {rep}", flush=True)
        paths = [run.RESULTS_ROOT / item["directory"] for item in protocol["runs"]]
        glove_report.write_report(paths, output)
        protocol["status"] = "passed"
    except (Exception, KeyboardInterrupt) as error:
        protocol["status"] = "failed"
        protocol["error"] = f"{type(error).__name__}: {error}"
        print(protocol["error"], file=sys.stderr)
    finally:
        save()
    return 0 if protocol["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
