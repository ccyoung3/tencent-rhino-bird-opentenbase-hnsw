#!/usr/bin/env python3
"""Freeze the follow-up inputs; never overwrite an earlier manifest."""
import hashlib
import json
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    assert not (HERE / "start-manifest.json").exists()
    prior = ROOT / "dev/snapshots/20260910-observer-bounded/audit.json"
    recorded = json.loads(prior.read_text())["sha256"]
    changed = [name for name, digest in recorded.items() if sha(ROOT / name) != digest]
    assert not changed, changed
    core = json.loads((ROOT / "dev/snapshots/20260906-build-timing/validated-manifest.json").read_text())
    for name, digest in core["sha256"].items():
        if name.startswith("pgvector/"):
            assert sha(ROOT / name) == digest, name
    diff = subprocess.check_output(["git", "-C", str(ROOT / "pgvector"), "diff", "HEAD", "--binary"])
    assert hashlib.sha256(diff).hexdigest() == "99da7d1050501be3d8060989511f26c39f0571e0a14c1d09a809c4a1fbf2bcc2"
    assert not subprocess.check_output(["git", "-C", str(ROOT / "OpenTenBase"), "status", "--porcelain"])
    tests = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", str(ROOT / "experiments/hnsw_build"),
                            "-p", "test_*.py", "-v"], capture_output=True, text=True)
    (HERE / "python-tests-at-start.log").write_text(tests.stdout + tests.stderr)
    assert tests.returncode == 0 and "skipped=" not in tests.stderr
    files = sorted((ROOT / "experiments/hnsw_build").glob("*.py")) + [Path(__file__),
             ROOT / "dev/compose.yml", ROOT / "docs/2026-09-10-default-off-triage.md"]
    with tarfile.open(HERE / "tooling-at-start.tar.gz", "x:gz") as archive:
        for path in files:
            archive.add(path, arcname=str(path.relative_to(ROOT)))
    result = dict(frozen_at_utc=datetime.now(timezone.utc).isoformat(),
        repository_head=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        previous_manifest=str(prior.relative_to(ROOT)), previous_manifest_sha256=sha(prior),
        previous_files_verified=len(recorded), core_diff_sha256=hashlib.sha256(diff).hexdigest(),
        test_returncode=tests.returncode, sha256={str(p.relative_to(ROOT)): sha(p) for p in files},
        archive_sha256=sha(HERE / "tooling-at-start.tar.gz"))
    (HERE / "start-manifest.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "sha256"}, indent=2))


if __name__ == "__main__":
    main()
