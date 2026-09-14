#!/usr/bin/env python3
"""Small real-stack success, timeout, and cancellation checks; run without other experiments."""
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import run


def main():
    output = run.RESULTS_ROOT / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-glove-e2e-verification")
    output.mkdir(exist_ok=False)
    cases = [("success", ["--rows", "10000", "--maintenance-work-mem", "64MB", "--evaluate",
                           "--tuning-queries", "10", "--validation-queries", "20", "--query-repetitions", "1"]),
             ("timeout", ["--rows", "10000", "--maintenance-work-mem", "64MB", "--statement-timeout-ms", "1"]),
             ("interrupt", ["--rows", "100000", "--maintenance-work-mem", "4MB"])]
    result = {"status": "running", "cases": []}
    try:
        for name, options in cases:
            log = output / f"{name}.log"
            command = [sys.executable, str(Path(__file__).with_name("glove_run.py")),
                       "--label", f"glove-e2e-{name}", *options]
            print(name, flush=True)
            with log.open("w") as stream:
                child = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT,
                                         cwd=run.PROJECT_ROOT, start_new_session=True)
                try:
                    if name == "interrupt":
                        deadline = time.monotonic() + 90
                        while child.poll() is None and "Building with" not in log.read_text():
                            if time.monotonic() > deadline:
                                raise RuntimeError("interrupt test never reached build")
                            time.sleep(.1)
                        time.sleep(1)
                        # Signal Python only; it must cancel its named SQL backend itself.
                        os.kill(child.pid, signal.SIGINT)
                    returncode = child.wait(timeout=180)
                finally:
                    if child.poll() is None:
                        os.kill(child.pid, signal.SIGINT)
                        child.wait(timeout=180)
            source = Path(log.read_text().splitlines()[0])
            if source.parent.resolve() != run.RESULTS_ROOT.resolve():
                raise RuntimeError("unexpected evidence path")
            summary = json.loads((source / "summary.json").read_text())
            if summary["cleanup"]["status"] != "complete":
                raise AssertionError("temporary stack cleanup failed")
            expected = "passed" if name == "success" else "failed"
            if summary["status"] != expected or (returncode == 0) != (name == "success"):
                raise AssertionError(f"unexpected {name} result")
            if name != "success":
                if summary["internal_timing"]["status"] != "incomplete":
                    raise AssertionError("failed build incorrectly marked complete")
                if "Recommendation:" in (source / "diagnostic.md").read_text():
                    raise AssertionError("failed report generated bottleneck advice")
            else:
                evaluation = summary["glove_evaluation"]
                if set(evaluation["tuning"]["query_ids"]) & set(evaluation["validation"]["query_ids"]):
                    raise AssertionError("query split overlap")
            result["cases"].append({"case": name, "status": "passed", "source": source.name})
            (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
        result["status"] = "passed"
    except (Exception, KeyboardInterrupt) as error:
        result["status"] = "failed"
        result["error"] = f"{type(error).__name__}: {error}"
        print(result["error"], file=sys.stderr)
    finally:
        (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(output, flush=True)
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
