"""Owned local fixture for the new validation round; never used by observe.py."""
import json
import os
import secrets
import socket
import subprocess
import time
from contextlib import contextmanager

import glove_run
import run

IMAGES = {
    "timing-v1-arm64": glove_run.IMAGE_ID,
    "timing-v1-seed42-arm64": "sha256:a8b091b6ff87fb8c35037cabd00fb4cd5b0a111ced58371310cc620a05e4b969",
    "diagnostics-v2-seed42-arm64": "sha256:bac4bb4f7c4b0e183882b6cf653f9ef5af2c046dcd073a25a20f6c97cc76160c",
}


class Stack:
    def __init__(self, output, variant):
        self.output, self.variant = output, variant
        self.connections = []
        self.password = None
        self.provenance = None
        self.cleanup = None

    def connect(self, *, user="postgres", password=None, readonly=False):
        import psycopg
        import observe
        connection = psycopg.connect(host="127.0.0.1", port=55432, dbname="postgres", user=user,
            password=password or self.password, connect_timeout=5, autocommit=True, prepare_threshold=None,
            client_encoding="UTF8",
            application_name="hnsw_readonly_observer" if readonly else "hnsw_owned_validation",
            options=observe.OPTIONS if readonly else "-c statement_timeout=1800000")
        self.connections.append(connection)
        return connection


@contextmanager
def owned_stack(output, variant="timing-v1-arm64"):
    if variant not in IMAGES:
        raise ValueError("unapproved local runtime")
    output.mkdir(parents=True, exist_ok=False)
    try:
        with socket.create_connection(("127.0.0.1", 55432), timeout=1):
            raise RuntimeError("port 55432 occupied; refusing to touch existing database")
    except ConnectionRefusedError:
        pass
    stack = Stack(output, variant)
    previous = {key: os.environ.get(key) for key in ("HNSW_IMAGE", "COMPOSE_PROJECT_NAME")}
    os.environ["HNSW_IMAGE"] = "opentenbase-pg18-pgvector:" + variant
    os.environ["COMPOSE_PROJECT_NAME"] = f"hnsw-local-{os.getpid()}-{time.time_ns()}"
    try:
        run.run_command(run.compose_command("up", "-d", "--wait", "--wait-timeout", "60"))
        stack.provenance = run.collect_provenance()
        if stack.provenance["container_image_id"] != IMAGES[variant]:
            raise RuntimeError("local image identity mismatch")
        container = run.run_command(run.compose_command("ps", "-q", "db")).stdout.strip()
        run.run_command(["docker", "update", "--memory", "6g", "--memory-swap", "6g", container])
        stack.password, gateway = glove_run.configure_local_connection(output)
        # Only this fixture's database and gateway. Allows limited test roles,
        # not external hosts. Passwords are never serialized.
        hba = output / "pg_hba.conf"
        hba.write_text("local all all trust\nhost all all 127.0.0.1/32 trust\nhost all all ::1/128 trust\n"
                       f"host postgres all {gateway}/32 scram-sha-256\n")
        run.run_command(["docker", "cp", str(hba), f"{container}:/var/lib/postgresql/data/pg_hba.conf"])
        run.psql("SELECT pg_reload_conf()")
        connection = stack.connect()
        actual = str(connection.execute("SELECT system_identifier FROM pg_control_system()").fetchone()[0])
        if actual != run.psql("SELECT system_identifier FROM pg_control_system()").stdout.strip():
            raise RuntimeError("connection does not belong to owned fixture")
        (output / "provenance.json").write_text(json.dumps(stack.provenance, indent=2) + "\n")
        yield stack, connection
    finally:
        for connection in stack.connections:
            connection.close()
        try:
            result = subprocess.run(run.compose_command("down", "--volumes"), cwd=run.PROJECT_ROOT,
                                    capture_output=True, text=True, timeout=60)
            stack.cleanup = {"status": "complete" if result.returncode == 0 else "incomplete",
                             "returncode": result.returncode, "stderr": result.stderr}
        except Exception as error:
            stack.cleanup = {"status": "incomplete", "error": type(error).__name__}
        (output / "cleanup.json").write_text(json.dumps(stack.cleanup, indent=2) + "\n")
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        if stack.cleanup["status"] != "complete":
            raise RuntimeError("owned fixture cleanup incomplete")
