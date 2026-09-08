#!/usr/bin/env python3
"""Run isolated end-to-end timing checks, including expected failures."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import signal
import time

ROOT = Path(__file__).resolve().parents[1]
CASES = [
    ("serial-memory", 0, "64MB", 0, "timing-v1-arm64", True, False),
    ("parallel-memory", 2, "64MB", 0, "timing-v1-arm64", True, False),
    ("parallel-spill", 2, "4MB", 0, "timing-v1-arm64", True, True),
    ("parallel-spill-nonempty", 2, "5MB", 0, "timing-v1-arm64", True, True),
    ("serial-timeout", 0, "1MB", 100, "timing-v1-arm64", False, None),
    ("parallel-timeout", 2, "4MB", 100, "timing-v1-arm64", False, None),
    ("missing-summary", 0, "64MB", 0, "diagnostics-v2-arm64", False, None),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interrupt-only", action="store_true")
    parser.add_argument("--case", choices=[case[0] for case in CASES])
    args = parser.parse_args()
    evidence = []
    for label, workers, memory, timeout, image, success, spill in ([] if args.interrupt_only else CASES):
        if args.case and label != args.case:
            continue
        command = [sys.executable, str(ROOT / "experiments/hnsw_build/run.py"),
                   "--isolated", "--build-timing", "--rows", "10000", "--dimensions", "32",
                   "--parallel-workers", str(workers), "--maintenance-work-mem", memory,
                   "--statement-timeout-ms", str(timeout),
                   "--image", "opentenbase-pg18-pgvector:" + image,
                   "--label", "timing-v1-e2e-" + label]
        result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
        if not result.stdout.strip():
            raise RuntimeError(result.stderr)
        output = Path(result.stdout.strip().splitlines()[-1])
        summary = json.loads((output / "summary.json").read_text())
        assert result.returncode == (0 if success else 1), result.stderr
        assert summary["status"] == ("passed" if success else "failed"), summary
        assert summary["internal_timing"]["status"] == ("complete" if success else "incomplete")
        assert summary["cleanup"]["status"] == "complete", summary["cleanup"]
        report = (output / "diagnostic.md").read_text()
        stderr = (output / "build.stderr.txt").read_text()
        if success:
            record = summary["internal_timing"]["records"][0]
            assert record["spill"] == spill
            assert record["parallel_workers"] == workers
            assert (record["durations_us"]["disk_insert"] is None) == (not spill)
            assert "Revalidation:" in report
            if label == "parallel-spill-nonempty":
                assert summary["diagnostics"]["spill_after_tuples"] > 0
                assert record["durations_us"]["memory_build"] > 0
                assert record["durations_us"]["spill_drain"] >= 0
        else:
            assert "No stage bottleneck" in report
            assert "Recommendation:" not in report
            if timeout:
                assert "canceling statement due to statement timeout" in stderr
                assert summary["build_command_returncode"] != 0
            else:
                assert summary["build_command_returncode"] == 0
        evidence.append({"case": label, "expected_success": success,
                         "result": str(output.relative_to(ROOT)), "verified": True})
        print(json.dumps(evidence[-1]), flush=True)
    for workers in (() if args.case else (0, 2)):
        label = f"timing-v1-interrupt-w{workers}-{time.time_ns()}"
        command = [sys.executable, str(ROOT / "experiments/hnsw_build/run.py"),
                   "--isolated", "--build-timing", "--rows", "100000", "--dimensions", "32",
                   "--parallel-workers", str(workers), "--maintenance-work-mem", "4MB" if workers else "1MB",
                   "--image", "opentenbase-pg18-pgvector:timing-v1-arm64", "--label", label]
        process = subprocess.Popen(command, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 60
            while True:
                paths = list((ROOT / "experiments/hnsw_build/results").glob(f"*-{label}"))
                if paths:
                    log = paths[0] / "build.stderr.txt"
                    if log.exists() and "graph no longer fits" in log.read_text():
                        break
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError("build never reached the spill cancellation gate")
                time.sleep(.1)
            process.send_signal(signal.SIGINT)
            stdout, stderr = process.communicate(timeout=30)
            assert process.returncode == 1, (stdout, stderr)
            output = paths[0]
            summary = json.loads((output / "summary.json").read_text())
            assert summary["status"] == "failed"
            assert summary["internal_timing"]["status"] == "incomplete"
            assert summary["cleanup"]["status"] == "complete"
            assert "canceling statement due to user request" in (output / "build.stderr.txt").read_text()
            assert "No stage bottleneck" in (output / "diagnostic.md").read_text()
            evidence.append({"case": f"interrupt-workers-{workers}", "expected_success": False,
                             "result": str(output.relative_to(ROOT)), "verified": True})
            print(json.dumps(evidence[-1]), flush=True)
        finally:
            if process.poll() is None:
                process.send_signal(signal.SIGINT)
                process.wait(timeout=30)
    print(f"All {len(evidence)} end-to-end cases passed", flush=True)


if __name__ == "__main__":
    main()
