#!/usr/bin/env python3
"""Real restricted-role observer tests in a newly owned local fixture only."""
import json
import os
import secrets
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import glove
import local_stack
import observe
import run


def main():
    from psycopg import sql
    output = run.RESULTS_ROOT / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-observe-e2e")
    output.mkdir()
    result = {"status": "running", "checks": []}
    print(output, flush=True)
    try:
        with local_stack.owned_stack(output / "fixture") as (stack, admin):
            password = secrets.token_hex(24)
            for role in ("hnsw_watcher", "hnsw_blind"):
                admin.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(sql.Identifier(role), sql.Literal(password)))
            admin.execute("GRANT pg_read_all_stats TO hnsw_watcher")
            watcher = stack.connect(user="hnsw_watcher", password=password, readonly=True)
            blind = stack.connect(user="hnsw_blind", password=password, readonly=True)
            assert watcher.execute("SHOW transaction_read_only").fetchone()[0] == "on"
            # The fixture admin loads data; the observer has no table access.
            admin.execute("CREATE EXTENSION vector; CREATE TABLE public.observer_items (id bigint, embedding vector(8))")
            admin.execute("INSERT INTO public.observer_items SELECT i, ARRAY[i*.001,1,2,3,4,5,6,7]::vector FROM generate_series(1,30000) i")
            try:
                watcher.execute("SELECT * FROM public.observer_items LIMIT 1")
                raise AssertionError("observer unexpectedly has business-table read access")
            except Exception as error:
                assert getattr(error, "sqlstate", None) == "42501", "payload read must be privilege-denied"
            try:
                watcher.execute("CREATE TABLE public.must_not_exist (id int)")
                raise AssertionError("observer write unexpectedly succeeded")
            except Exception as error:
                # Privilege checking can reject CREATE before the read-only check.
                assert getattr(error, "sqlstate", None) in ("25006", "42501"), "DDL must be rejected"
            assert admin.execute("SELECT to_regclass('public.must_not_exist')").fetchone()[0] is None
            result["checks"].append("read_only_and_no_payload_privileges")
            builder = stack.connect()
            pid = builder.info.backend_pid
            r = observe.observe(watcher, pid, output / "idle", duration=.5)
            assert r["status"] == "not_building"
            r = observe.observe(blind, pid, output / "no-permission", duration=.5)
            assert r["status"] == "insufficient_visibility"
            r = observe.observe(watcher, 2147483647, output / "no-task", duration=.5)
            assert r["status"] == "not_found"
            result["checks"] += ["idle", "insufficient_visibility", "missing_pid"]
            # Test the user-facing service/CLI route too. Credentials live only
            # in a private temporary file, never in argv or the evidence tree.
            with tempfile.TemporaryDirectory(prefix="hnsw-observer-service-") as temporary:
                service = Path(temporary) / "pg_service.conf"
                service.write_text("[hnsw_fixture]\nhost=127.0.0.1\nport=55432\ndbname=postgres\n"
                                   f"user=hnsw_watcher\npassword={password}\n")
                service.chmod(0o600)
                cli = subprocess.run([sys.executable, str(Path(observe.__file__)), "--service", "hnsw_fixture",
                    "--pid", str(pid), "--output", str(output / "service-cli"), "--duration", ".5"],
                    env={**os.environ, "PGSERVICEFILE": str(service)}, capture_output=True, text=True, timeout=15)
                assert cli.returncode == 0 and cli.stdout.strip() == "not_building"
                assert json.loads((output / "service-cli/summary.json").read_text())["server"]["read_only"] == "on"
            result["checks"].append("service_cli_read_only_connection")
            # Hold a conflicting lock so observation is deterministic, not based
            # on hoping to sample a millisecond phase.
            locker = stack.connect()
            locker.execute("BEGIN; LOCK TABLE public.observer_items IN ACCESS EXCLUSIVE MODE")
            build = {"status": "running"}
            def work():
                try:
                    builder.execute("SET maintenance_work_mem='1MB'; SET max_parallel_maintenance_workers=0; SET hnsw.build_timing=on")
                    builder.execute("CREATE INDEX observer_hnsw ON public.observer_items USING hnsw (embedding vector_l2_ops)")
                    build["status"] = "complete"
                except Exception as error:
                    build["status"] = "failed"
                    build["sqlstate"] = getattr(error, "sqlstate", None)
            thread = threading.Thread(target=work)
            thread.start()
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                state = observe.sample(watcher, pid)
                if state and state["wait_event_type"] == "Lock":
                    break
                time.sleep(.05)
            else:
                raise RuntimeError("builder never reached controlled lock wait")
            # Some lock acquisition precedes publication of CREATE INDEX progress.
            # Retain raw wait evidence even if the progress view is not populated.
            (output / "lock-wait.json").write_text(json.dumps(state, default=str, indent=2) + "\n")
            waited = observe.observe(watcher, pid, output / "lock-wait", interval=.25, duration=.5)
            assert waited["status"] == "duration_reached" and waited["build_outcome"] == "unknown"
            assert any(w["type"] == "Lock" for w in waited["wait_observations"])
            locker.execute("COMMIT")
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                if (observe.sample(watcher, pid) or {}).get("phase"):
                    break
                time.sleep(.01)
            else:
                raise RuntimeError("builder did not publish progress")
            r = observe.observe(watcher, pid, output / "mid-build", interval=.25, duration=.5)
            assert r["samples"] > 0 and r["phases"]
            assert build["status"] == "running", "fixture must still build after observer stops"
            watcher.close()
            assert (admin.execute("SELECT state FROM pg_stat_activity WHERE pid=%s", (pid,)).fetchone() or [None])[0] == "active"
            result["checks"] += ["lock_wait_visible", "mid_build_attach", "observer_exit_does_not_cancel_builder"]
            # Only the fixture admin, never the observer, cancels the owned task.
            observer2 = stack.connect(user="hnsw_watcher", password=password, readonly=True)
            stopped = {}
            obs_thread = threading.Thread(target=lambda: stopped.update(observe.observe(
                observer2, pid, output / "builder-cancel", interval=.25, duration=10)))
            obs_thread.start()
            time.sleep(.3)
            admin.execute("SELECT pg_cancel_backend(%s)", (pid,))
            thread.join(timeout=15); obs_thread.join(timeout=15)
            assert not thread.is_alive() and not obs_thread.is_alive()
            assert build == {"status": "failed", "sqlstate": "57014"}
            assert stopped["status"] == "ended_unconfirmed" and stopped["build_outcome"] == "unknown"
            result["checks"].append("cancelled_build_not_reported_success")
            notices = []
            builder.add_notice_handler(lambda d: notices.append(d.message_primary or ""))
            build.clear(); build["status"] = "running"
            thread = threading.Thread(target=work)
            thread.start()
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                if (observe.sample(observer2, pid) or {}).get("phase"):
                    break
                time.sleep(.01)
            else:
                raise RuntimeError("successful build did not publish progress")
            completed = observe.observe(observer2, pid, output / "builder-success", interval=.25, duration=60)
            thread.join(timeout=15)
            assert not thread.is_alive() and build["status"] == "complete"
            assert completed["status"] == "ended_unconfirmed" and completed["build_outcome"] == "unknown"
            log = output / "explicit-build.log"
            log.write_text("\n".join(notices) + "\n")
            imported = observe.inspect_timing_log(log, pid)
            assert imported["command_outcome"] == "unknown" and not imported["merged_into_observed_timeline"]
            (output / "imported-timing.json").write_text(json.dumps(imported, indent=2) + "\n")
            result["checks"] += ["successful_build_remains_unconfirmed_to_observer", "explicit_log_import_not_merged"]
        result["cleanup"] = stack.cleanup
        result["status"] = "passed"
    except (Exception, KeyboardInterrupt) as error:
        result["status"] = "failed"
        result["error"] = type(error).__name__ + ":" + (getattr(error, "sqlstate", None) or "")
        result["error_locations"] = [{"file": frame.filename.rsplit("/", 1)[-1], "line": frame.lineno}
                                     for frame in traceback.extract_tb(error.__traceback__)]
        print(result["error"], flush=True)
    finally:
        result["tooling_sha256"] = {name: glove.file_sha256(run.PROJECT_ROOT / "experiments/hnsw_build" / name)
                                     for name in ("observe.py", "local_stack.py", "verify_observe.py")}
        (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(result["status"], flush=True)
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
