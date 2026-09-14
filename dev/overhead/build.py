#!/usr/bin/env python3
"""Build baseline/candidate extensions with one pinned compiler/runtime, no Git writes."""
import argparse
import hashlib
import io
import json
import shutil
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SNAPSHOT = ROOT / "dev/snapshots/20260911-overhead-acceptance"
BASES = {"timing-v1-test-arm64": "sha256:583632f8a2ba73f694ffed52fcd8e9a9a385da94c2602bfd65de1086a92148c6",
         "timing-v1-arm64": "sha256:af1ee2f012f452048c080b591c5456e8a5a83fea77fb4df6e53f4d28ba395fc7"}
CORE = "99da7d1050501be3d8060989511f26c39f0571e0a14c1d09a809c4a1fbf2bcc2"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def command(args):
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt", type=int, default=2)
    args = parser.parse_args()
    SNAPSHOT.mkdir(exist_ok=True)
    attempt = SNAPSHOT / f"build-attempt-{args.attempt}"
    attempt.mkdir(exist_ok=False)
    manifest = SNAPSHOT / "build-manifest.json"
    assert not manifest.exists(), "build once; preserve finished inputs"
    previous = ROOT / "dev/snapshots/20260910-default-off-triage/audit.json"
    prior = json.loads(previous.read_text())
    assert all(sha(ROOT / n) == h for n, h in prior["sha256"].items())
    repository = ROOT / "pgvector"
    assert command(["git", "-C", str(repository), "rev-parse", "HEAD"]) == "8ee86c96f0fd72390f890aa8a336fda6d3ab4c6c"
    diff = subprocess.check_output(["git", "-C", str(repository), "diff", "HEAD", "--binary"])
    assert hashlib.sha256(diff).hexdigest() == CORE
    for tag, digest in BASES.items():
        assert command(["docker", "image", "inspect", "--format", "{{.Id}}", "opentenbase-pg18-pgvector:" + tag]) == digest
    context = Path(tempfile.mkdtemp(prefix="hnsw-acceptance-build-"))
    archive = subprocess.check_output(["git", "-C", str(repository), "archive", "--format=tar", "HEAD"])
    for variant in ("baseline", "candidate"):
        (context / variant).mkdir()
        with tarfile.open(fileobj=io.BytesIO(archive)) as source:
            source.extractall(context / variant, filter="data")
    changes = command(["git", "-C", str(repository), "diff", "--name-only", "HEAD"]).splitlines()
    assert set(changes) == {"src/hnsw.c", "src/hnsw.h", "src/hnswbuild.c", "test/t/045_hnsw_low_memory_build.pl"}
    changes.append("test/t/049_hnsw_build_timing.pl")
    for name in changes:
        shutil.copyfile(repository / name, context / "candidate" / name)
    dockerfile = (HERE / "Dockerfile").read_text()
    # Local image IDs are not registry manifest digests and cannot be used as
    # FROM sha256:... . Verify the local tag IDs before and after the builds,
    # and verify every runtime retains the exact common base layer prefix.
    (context / "Dockerfile").write_text(dockerfile)
    shutil.copyfile(HERE / "compile.sh", context / "compile.sh")
    result = dict(status="building", started_at_utc=datetime.now(timezone.utc).isoformat(),
        previous_audit_sha256=sha(previous), previous_files_verified=len(prior["sha256"]),
        baseline_commit=command(["git", "-C", str(repository), "rev-parse", "HEAD"]),
        baseline_archive_sha256=hashlib.sha256(archive).hexdigest(), candidate_tracked_diff_sha256=CORE,
        candidate_changes={n: sha(repository / n) for n in changes}, bases=BASES, build_context=str(context),
        attempt_directory=str(attempt.relative_to(ROOT)),
        inputs={str(p.relative_to(ROOT)): sha(p) for p in (Path(__file__), HERE / "Dockerfile", HERE / "compile.sh")}, images={})
    (attempt / "build-start.json").write_text(json.dumps(result, indent=2) + "\n")
    # Scratch full upstream sources remain outside the repository, not in its delivery assets.
    for variant in ("baseline", "candidate"):
        for mode in ("seed42", "normal"):
            tag = f"opentenbase-pg18-pgvector:acceptance-20260911-{variant}-{mode}-arm64"
            log = attempt / f"build-{variant}-{mode}.log"
            with log.open("w") as stream:
                process = subprocess.run(["docker", "build", "--pull=false", "--network=none", "--progress=plain",
                    "--build-arg", "VARIANT=" + variant, "--build-arg", "MODE=" + mode,
                    "-t", tag, str(context)], cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
            if process.returncode:
                raise RuntimeError("common build failed; see " + log.name)
            digest = command(["docker", "image", "inspect", "--format", "{{.Id}}", tag])
            identity = command(["docker", "run", "--rm", "--network", "none", "--read-only", "--entrypoint", "/bin/cat",
                                digest, "/opt/hnsw-acceptance-identity.txt"])
            (attempt / f"identity-{variant}-{mode}.txt").write_text(identity + "\n")
            for name in changes:
                if name.startswith("src/"):
                    expected = sha(context / variant / name)
                    assert f"{expected}  {name}" in identity
            result["images"][f"{variant}-{mode}"] = dict(tag=tag, id=digest, identity_sha256=hashlib.sha256((identity+"\n").encode()).hexdigest())
            parent = json.loads(command(["docker", "image", "inspect", BASES["timing-v1-arm64"]]))[0]
            built = json.loads(command(["docker", "image", "inspect", digest]))[0]
            assert built["RootFS"]["Layers"][:len(parent["RootFS"]["Layers"])] == parent["RootFS"]["Layers"]
            print(variant, mode, digest, flush=True)
    for tag, digest in BASES.items():
        assert command(["docker", "image", "inspect", "--format", "{{.Id}}", "opentenbase-pg18-pgvector:" + tag]) == digest
    result["status"] = "passed"
    result["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    manifest.write_text(json.dumps(result, indent=2) + "\n")
    print("Common-environment source-attested builds complete", flush=True)


if __name__ == "__main__":
    main()
