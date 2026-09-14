#!/usr/bin/env python3
"""Independent offline audit of the fixed default-off follow-up; no DB or Git writes."""
import argparse
import hashlib
import itertools
import json
import math
import socket
import statistics
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
TOOLS = ROOT / "experiments/hnsw_build"
RESULTS = TOOLS / "results"
SCENES = [(0, True), (2, False)]
CONDITIONS = ["new_off", "new_on", "new_observed"]
DOCS = ["README.md", "docs/2026-09-02-project-brief.md", "docs/2026-09-04-frozen-snapshot-review.md",
        "docs/2026-09-10-default-off-triage.md", "experiments/hnsw_build/README.md",
        "experiments/hnsw_build/results/README.md", "docs/2026-09-10-observer-recall-overhead.md"]
IMAGES = {"diagnostics-v2-seed42-arm64": "sha256:bac4bb4f7c4b0e183882b6cf653f9ef5af2c046dcd073a25a20f6c97cc76160c",
          "timing-v1-seed42-arm64": "sha256:a8b091b6ff87fb8c35037cabd00fb4cd5b0a111ced58371310cc620a05e4b969"}


def read(path):
    return json.loads(path.read_text())


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def near(actual, expected):
    assert math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12), (actual, expected)


def identities():
    start = read(HERE / "start-manifest.json")
    prior = ROOT / start["previous_manifest"]
    assert sha(prior) == start["previous_manifest_sha256"]
    old = read(prior)["sha256"]
    changed = [name for name, digest in old.items() if sha(ROOT / name) != digest]
    assert set(changed) <= set(DOCS), changed
    assert sha(HERE / "tooling-at-start.tar.gz") == start["archive_sha256"]
    for name, digest in start["sha256"].items():
        if name.endswith((".py", ".yml")):
            assert sha(ROOT / name) == digest, name
    core = read(ROOT / "dev/snapshots/20260906-build-timing/validated-manifest.json")["sha256"]
    for name, digest in core.items():
        if name.startswith("pgvector/"):
            assert sha(ROOT / name) == digest, name
    diff = subprocess.check_output(["git", "-C", str(ROOT / "pgvector"), "diff", "HEAD", "--binary"])
    assert hashlib.sha256(diff).hexdigest() == start["core_diff_sha256"]
    assert not subprocess.check_output(["git", "-C", str(ROOT / "OpenTenBase"), "status", "--porcelain"])
    assert subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip() == start["repository_head"]
    return dict(previous_files_checked=len(old), previous_evidence_and_code_unchanged=True,
                intentional_document_updates=changed, core_unchanged=True, head_unchanged=True)


def verify(folder, *, smoke=False):
    s, p = read(folder / "summary.json"), read(folder / "protocol.json")
    assert s["status"] == "passed" and p["smoke"] == smoke
    blocks, orders = (1, 1) if smoke else (6, 6)
    assert (p["blocks"], p["orders"], p["warmups"], p["formal_per_fixture"]) == (blocks, orders, 2, 3)
    assert (p["rows"], p["dimensions"], p["m"], p["ef_construction"]) == (20000, 32, 16, 64)
    assert p["scenes"] == [[0, True], [2, False]] and p["no_optional_stopping"]
    assert p["prior_source"] == "20260910T075739Z-bounded-overhead"
    prior = read(RESULTS / p["prior_source"] / "summary.json")
    exploratory = read(folder / "prior-position-analysis.json")
    assert exploratory["source"] == p["prior_source"]
    for group in exploratory["groups"]:
        indexed = {(r["block"], r["variant"]): r for r in prior["rows"]
                   if (r["workers"], r["spill"]) == (group["workers"], group["spill"])}
        for position in group["positions"]:
            blocks_at_position = [b for b in range(12) if [1, 3, 2][b % 3] == position["position"]]
            assert position["blocks"] == blocks_at_position
            ratios = [indexed[b, "new_off"]["command_seconds"] / indexed[b, "old_off"]["command_seconds"]
                      for b in blocks_at_position]
            assert ratios == position["paired_ratios"]
            near(position["median_ratio"], statistics.median(ratios))
    if not smoke:
        started = datetime.strptime(folder.name.split("-bounded-")[0], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        assert datetime.fromisoformat(read(HERE / "start-manifest.json")["frozen_at_utc"]) < started
        with tarfile.open(folder / "tooling-at-start.tar.gz") as archive:
            for name, digest in p["tooling_sha256"].items():
                assert sha(TOOLS / name) == digest
                assert hashlib.sha256(archive.extractfile(name).read()).hexdigest() == digest
    images = read(folder / "image-inspection.json")
    assert images == s["images"]
    for variant, digest in IMAGES.items():
        assert images[variant]["id"] == digest
    a, b = [images[name]["runtime_inspection"].splitlines() for name in IMAGES]
    assert len(a) == len(b) == 6
    assert a[0].endswith("  /opt/opentenbase/bin/postgres") and a[1].endswith("  /opt/opentenbase/lib/postgresql/vector.so")
    assert a[0] == b[0] and a[2:] == b[2:] and a[1] != b[1]
    expected = {"rows": [], "warmups": []}
    permutations = list(itertools.permutations(CONDITIONS))[:orders]
    fixtures = []
    for study, repetitions in (("A", blocks), ("B", orders)):
        for block in range(repetitions):
            for workers, spill in (SCENES if block % 2 == 0 else SCENES[::-1]):
                versions = (["old", "new"] if block % 2 == 0 else ["new", "old"]) if study == "A" else ["new"]
                for version in versions:
                    base = f"{study}-b{block:02d}-w{workers}/{version}"
                    fixtures.append(base)
                    conditions = [version + "_off"] * 3 if study == "A" else permutations[block]
                    for field, sequence in (("warmups", [version + "_off"] * 2), ("rows", conditions)):
                        for position, variant in enumerate(sequence, 1):
                            previous = None if field == "warmups" or position == 1 else sequence[position - 2]
                            source = base + f"/{'warmup' if field == 'warmups' else 'formal'}-{position}-{variant}"
                            expected[field].append((study, block, workers, spill, variant, position, previous, source))
    observed = 0
    enabled_details = []
    for field in expected:
        assert [(r["study"], r["block"], r["workers"], r["spill"], r["variant"], r["position"],
                 r["previous_condition"], r["source"]) for r in s[field]] == expected[field]
        for row in s[field]:
            raw = read(folder / row["source"] / "measurement.json")
            assert raw == {k: v for k, v in row.items() if k not in ("study", "block", "position", "previous_condition", "source")}
            assert row["command_returncode"] == 0 and math.isfinite(row["command_seconds"]) and row["command_seconds"] > 0
            text = (folder / row["source"] / "build.stderr.txt").read_text()
            assert ("graph no longer fits" in text) == row["spill"]
            assert ("using 2 parallel workers" in text) == (row["workers"] == 2)
            enabled = row["variant"] in ("new_on", "new_observed")
            assert ("hnsw build timing:" in text) == enabled
            assert row["internal_timing"]["status"] == ("complete" if enabled else "not_requested")
            if enabled:
                payloads = [json.loads(line.split("hnsw build timing: ", 1)[1]) for line in text.splitlines()
                            if line.startswith("NOTICE: hnsw build timing: ")]
                parsed = row["internal_timing"]["records"]
                assert len(payloads) == len(parsed) == 1
                payload, record = payloads[0], parsed[0]
                assert payload == {k: v for k, v in record.items() if k != "durations_us"}
                durations = {r["phase"]: None if r["start_us"] is None else r["end_us"] - r["start_us"]
                             for r in payload["phases"]}
                assert durations == record["durations_us"]
                assert sum(v for v in durations.values() if v is not None) == payload["total_us"]
                largest = max((v, k) for k, v in durations.items() if v is not None)[1]
                assert largest == row["internal_timing"]["dominant_phase"]
                near(row["internal_timing"]["dominant_fraction"], durations[largest] / payload["total_us"])
                enabled_details.append(dict(workers=row["workers"], source=row["source"], phase=largest,
                    fraction=durations[largest] / payload["total_us"], internal_seconds=payload["total_us"] / 1e6,
                    command_minus_internal_seconds=row["command_seconds"] - payload["total_us"] / 1e6))
            assert row["index_bytes"] > 0
            provenance = read((folder / row["source"]).parent / "provenance.json")
            assert provenance["container_image_id"] == IMAGES[row["image_variant"]]
            if row["variant"] == "new_observed":
                o = row["observer"].get("observation", {})
                if o:
                    assert o == read(folder / row["source"] / "observer/summary.json")
                    assert o["build_outcome"] == "unknown"
                observed += bool(o.get("phases")) and o.get("samples", 0) > 0
    assert len({r["source"] for f in expected for r in s[f]}) == sum(len(e) for e in expected.values())
    assert {str(f.parent.relative_to(folder)) for f in folder.rglob("cleanup.json")} == set(fixtures)
    for fixture in fixtures:
        cleanup = read(folder / fixture / "cleanup.json")
        assert cleanup["status"] == "complete" and cleanup["returncode"] == 0
    # Independently recompute the per-block paired statistic and order-statistic bound.
    matched = []
    for workers, spill in SCENES:
        by = {(r["block"], r["variant"], r["position"]): r for r in s["rows"]
              if r["study"] == "A" and r["workers"] == workers and r["spill"] == spill}
        triples = [[by[block, "new_off", position]["command_seconds"] / by[block, "old_off", position]["command_seconds"]
                    for position in (1, 2, 3)] for block in range(blocks)]
        ratios = [statistics.median(values) for values in triples]
        group = next(g for g in s["analysis"]["matched"] if g["workers"] == workers and g["spill"] == spill)
        assert [g["position_ratios"] for g in group["blocks"]] == triples
        assert [g["median_ratio"] for g in group["blocks"]] == ratios
        near(group["median_change_percent"], (statistics.median(ratios)-1)*100)
        if smoke:
            assert group["upper_bound"]["upper_ratio"] is None
        else:
            assert group["upper_bound"]["rank"] == 6
            near(group["upper_bound"]["coverage"], 63/64)
            near(group["upper_bound"]["upper_ratio"], max(ratios))
        for pos in range(3):
            near(group["position_changes_percent"][pos], (statistics.median(t[pos] for t in triples)-1)*100)
        matched.append(group)
    ordering = []
    for group in s["analysis"]["ordering"]:
        for position in group["positions"]:
            rows = [r for r in s["rows"] if r["study"] == "B" and (r["workers"], r["spill"], r["variant"], r["position"]) ==
                    (group["workers"], group["spill"], group["condition"], position["position"])]
            assert len(rows) == position["n"] == (1 if smoke else 2)
            near(position["median_seconds"], statistics.median(r["command_seconds"] for r in rows))
        ordering.append(group)
    descriptive = []
    for workers, spill in SCENES:
        rows = [r for r in s["rows"] if r["study"] == "B" and (r["workers"], r["spill"]) == (workers, spill)]
        first = {r["block"]: r["command_seconds"] for r in rows if r["position"] == 1}
        position_ratios = {str(pos): [r["command_seconds"] / first[r["block"]] for r in rows if r["position"] == pos]
                           for pos in (2, 3)}
        predecessors = []
        for condition in CONDITIONS:
            for previous in (None, *[c for c in CONDITIONS if c != condition]):
                values = [r["command_seconds"] for r in rows if r["variant"] == condition and r["previous_condition"] == previous]
                if values:
                    predecessors.append(dict(condition=condition, previous=previous, n=len(values),
                                             median_seconds=statistics.median(values)))
        descriptive.append(dict(workers=workers, spill=spill, scope="descriptive, not causal; condition and order effects may coexist",
            later_to_first_ratios=position_ratios,
            median_later_to_first={p: statistics.median(v) for p, v in position_ratios.items()}, predecessors=predecessors))
    return dict(formal=len(s["rows"]), warmups=len(s["warmups"]), cleaned_fixtures=len(fixtures),
                observed_with_progress=observed, expected_observed=orders*2, matched=matched, ordering=ordering,
                descriptive_order_diagnostics=descriptive, enabled_phase_diagnostics=enabled_details)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder")
    parser.add_argument("--final", action="store_true", help="write audit.json once, after documents are finalized")
    args = parser.parse_args()
    folder = RESULTS / args.folder
    assert folder.parent == RESULTS and folder.is_dir()
    result = dict(status="passed", audited_at_utc=datetime.now(timezone.utc).isoformat(),
        scope="offline reproducibility and raw-record audit; not a C test rerun, human Review, or performance pass",
        source=folder.name, identity=identities(), formal=verify(folder),
        smoke=verify(RESULTS / "20260910T084218Z-bounded-triage-smoke", smoke=True))
    tests = {}
    for label, executable in (("venv", sys.executable), ("system", "python3")):
        test = subprocess.run([executable, "-m", "unittest", "discover", "-s", str(TOOLS), "-p", "test_*.py", "-v"],
                              capture_output=True, text=True)
        assert test.returncode == 0
        if label == "venv":
            assert "skipped=" not in test.stderr
        tests[label] = dict(returncode=test.returncode, summary=test.stderr.splitlines()[-4:])
        if args.final:
            (HERE / f"python-tests-{label}.log").write_text(test.stdout + test.stderr)
    result["tests"] = tests
    for command in (["docker", "ps", "-a", "--format", "{{.Names}}"],
                    ["docker", "volume", "ls", "--format", "{{.Name}}"],
                    ["docker", "network", "ls", "--format", "{{.Name}}"]):
        assert not any(name.startswith("hnsw-local-") for name in subprocess.check_output(command, text=True).splitlines())
    try:
        with socket.create_connection(("127.0.0.1", 55432), timeout=1):
            raise AssertionError("local fixture port still occupied")
    except ConnectionRefusedError:
        pass
    result["local_fixture_resources_absent"] = True
    if args.final:
        assert not (HERE / "audit.json").exists(), "do not overwrite finished audit"
        paths = [p for f in (folder, RESULTS / "20260910T084218Z-bounded-triage-smoke", HERE) for p in f.rglob("*")
                 if p.is_file() and "__pycache__" not in p.parts and p.name != "audit.json"]
        paths += [ROOT / p for p in DOCS] + list(TOOLS.glob("*.py"))
        result["sha256"] = {str(p.relative_to(ROOT)): sha(p) for p in sorted(set(paths))}
        (HERE / "audit.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "sha256"}, indent=2))


if __name__ == "__main__":
    main()
