#!/usr/bin/env python3
"""Reconstruct the frozen candidate in a fresh checkout; never overwrite sources."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "dev/snapshots/20260906-build-timing"
MANIFEST = SNAPSHOT / "validated-manifest.json"
UPSTREAMS = {
    "OpenTenBase": ("https://github.com/OpenTenBase/OpenTenBase.git", "opentenbase_base"),
    "pgvector": ("https://github.com/pgvector/pgvector.git", "pgvector_base"),
}


def command(*args: str, capture: bool = False) -> str:
    result = subprocess.run(args, check=True, text=True,
                            stdout=subprocess.PIPE if capture else None)
    return result.stdout.strip() if capture else ""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_inputs(manifest: dict) -> None:
    files = {
        SNAPSHOT / "pgvector.patch": "dev/snapshots/20260906-build-timing/pgvector.patch",
        SNAPSHOT / "049_hnsw_build_timing.pl": "pgvector/test/t/049_hnsw_build_timing.pl",
    }
    for path, key in files.items():
        if sha256(path) != manifest["sha256"][key]:
            raise ValueError(f"Frozen input hash mismatch: {path.name}")


def verify_sources(destination: Path, manifest: dict) -> dict:
    commits = {}
    for name, (_, key) in UPSTREAMS.items():
        repo = destination / name
        # Require the actual nested repository, not an ancestor Git worktree.
        if not (repo / ".git").exists():
            raise ValueError(f"Missing source checkout: {repo}")
        commit = command("git", "-C", str(repo), "rev-parse", "HEAD", capture=True)
        if commit != manifest[key]:
            raise ValueError(f"Unexpected upstream commit: {name}")
        commits[name] = commit
    hashes = {}
    for name, expected in manifest["sha256"].items():
        if name.startswith("pgvector/"):
            actual = sha256(destination / name)
            if actual != expected:
                raise ValueError(f"Candidate source hash mismatch: {name}")
            hashes[name] = actual
    patch = command("git", "-C", str(destination / "pgvector"), "diff", "--binary", "HEAD", capture=True)
    expected_patch = (SNAPSHOT / "pgvector.patch").read_text().strip()
    if patch != expected_patch:
        raise ValueError("Candidate tracked diff differs from the frozen patch")
    if command("git", "-C", str(destination / "OpenTenBase"), "status", "--porcelain", capture=True):
        raise ValueError("OpenTenBase checkout has unexpected changes")
    untracked = command("git", "-C", str(destination / "pgvector"), "ls-files", "--others",
                        "--exclude-standard", capture=True).splitlines()
    if untracked != ["test/t/049_hnsw_build_timing.pl"]:
        raise ValueError("Unexpected untracked files in the pgvector checkout")
    return {"upstream_commits": commits, "candidate_sha256": hashes,
            "frozen_manifest_sha256": sha256(MANIFEST), "source_check": "passed"}


def prepare(destination: Path, manifest: dict) -> dict:
    # Refuse even partial or empty existing checkouts: this also protects the
    # author's active working trees and makes a failed retry explicit.
    for name in UPSTREAMS:
        if (destination / name).exists() or (destination / name).is_symlink():
            raise ValueError(f"Refusing to overwrite {destination / name}; use a fresh clone or --check")
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".hnsw-sources-", dir=destination) as work:
        staging = Path(work)
        for name, (url, key) in UPSTREAMS.items():
            repo = staging / name
            command("git", "init", "--quiet", str(repo))
            command("git", "-C", str(repo), "remote", "add", "origin", url)
            command("git", "-C", str(repo), "-c", "core.autocrlf=false",
                    "fetch", "--quiet", "--depth=1", "origin", manifest[key])
            command("git", "-C", str(repo), "-c", "core.autocrlf=false",
                    "checkout", "--quiet", "--detach", "FETCH_HEAD")
        patch = str(SNAPSHOT / "pgvector.patch")
        command("git", "-C", str(staging / "pgvector"), "apply", "--check", patch)
        command("git", "-C", str(staging / "pgvector"), "apply", patch)
        shutil.copyfile(SNAPSHOT / "049_hnsw_build_timing.pl",
                        staging / "pgvector/test/t/049_hnsw_build_timing.pl")
        result = verify_sources(staging, manifest)
        # Move only after both upstreams and the full candidate pass verification.
        for name in UPSTREAMS:
            if (destination / name).exists() or (destination / name).is_symlink():
                raise ValueError(f"Destination appeared during preparation: {destination / name}")
            (staging / name).rename(destination / name)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, default=ROOT,
                        help="repository root that will contain OpenTenBase/ and pgvector/")
    parser.add_argument("--check", action="store_true", help="verify existing prepared sources without changing them")
    args = parser.parse_args()
    try:
        manifest = json.loads(MANIFEST.read_text())
        verify_inputs(manifest)
        destination = args.destination.resolve()
        result = verify_sources(destination, manifest) if args.check else prepare(destination, manifest)
        if not args.check:
            (destination / ".hnsw-source-provenance.json").write_text(
                json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"source preparation failed: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
