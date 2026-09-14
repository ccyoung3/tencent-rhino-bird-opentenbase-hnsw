"""Offline tests: no database, compiler, image build, or measured workload."""

from pathlib import Path
import re
import subprocess
import tempfile
import unittest

import instrument


ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = ROOT / "pgvector"


def source_text(variant):
    if variant == "candidate":
        return {name: (REPOSITORY / name).read_text() for name in instrument.SOURCE_NAMES}
    return {name: subprocess.check_output(
        ["git", "-C", str(REPOSITORY), "show", "v0.8.6:" + name], text=True)
        for name in instrument.SOURCE_NAMES}


def write_source(directory, sources):
    (directory / "src").mkdir()
    for name, text in sources.items():
        (directory / name).write_text(text)


class InstrumentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = {variant: source_text(variant) for variant in ("baseline", "candidate")}

    def test_both_source_variants_preserve_rng_and_shared_layout(self):
        for variant, sources in self.inputs.items():
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as temp:
                directory = Path(temp)
                write_source(directory, sources)
                report = instrument.instrument(directory)
                self.assertEqual(report["status"], "instrumented")
                for name, original in sources.items():
                    generated = (directory / name).read_text()
                    self.assertEqual(report["files"][name]["before"], instrument.sha256(original))
                    self.assertEqual(report["files"][name]["after"], instrument.sha256(generated))
                    for symbol in ("RandomDouble", "SeedRandom"):
                        old = [line for line in original.splitlines() if symbol in line]
                        new = [line for line in generated.splitlines() if symbol in line]
                        self.assertEqual(old, new)
                old_header = sources["src/hnsw.h"]
                new_header = (directory / "src/hnsw.h").read_text()
                for structure in ("HnswGraph", "HnswShared", "HnswSupport", "HnswBuildState"):
                    pattern = rf"typedef struct {structure}\n\{{.*?\}}\s*{structure};"
                    self.assertEqual(re.search(pattern, old_header, re.S)[0],
                                     re.search(pattern, new_header, re.S)[0])
                generated_build = (directory / "src/hnswbuild.c").read_text()
                self.assertEqual(generated_build.count('errmsg_internal("HNSW_MECHANISM %s"'), 1)
                self.assertIn("PG_FINALLY();", generated_build)
                self.assertLess(generated_build.index("hnsw_mechanism_active = false;"),
                                generated_build.index("mechanismCaptured = hnsw_mechanism_counters;"))
                self.assertEqual(generated_build.count("HnswMechanismReadUsage(&mechanismCPU"), 2)

    def test_second_application_fails_without_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            write_source(directory, self.inputs["candidate"])
            instrument.instrument(directory)
            before = {name: (directory / name).read_bytes() for name in instrument.SOURCE_NAMES}
            with self.assertRaisesRegex(instrument.InstrumentationError, "already instrumented"):
                instrument.instrument(directory)
            self.assertEqual(before, {name: (directory / name).read_bytes() for name in before})

    def test_missing_late_anchor_leaves_every_file_unchanged(self):
        sources = dict(self.inputs["candidate"])
        sources["src/hnswbuild.c"] = sources["src/hnswbuild.c"].replace(
            instrument.SCAN_ANCHOR, instrument.SCAN_ANCHOR.replace("true, progress", "false, progress"))
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            write_source(directory, sources)
            with self.assertRaisesRegex(instrument.InstrumentationError, "scan boundary"):
                instrument.instrument(directory)
            self.assertEqual(sources, {name: (directory / name).read_text() for name in sources})

    def test_duplicate_anchor_is_refused(self):
        sources = dict(self.inputs["baseline"])
        sources["src/hnswutils.c"] += '\n#include "vector.h"\n'
        with self.assertRaisesRegex(instrument.InstrumentationError, "found 2"):
            instrument.transform(sources)

    def test_product_checkout_is_refused(self):
        with self.assertRaisesRegex(instrument.InstrumentationError, "product checkout"):
            instrument.instrument(REPOSITORY)
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            write_source(directory, self.inputs["baseline"])
            (directory / ".git").write_text("gitdir: elsewhere\n")
            with self.assertRaisesRegex(instrument.InstrumentationError, "product checkout"):
                instrument.instrument(directory)

    def test_symlink_to_product_file_is_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            write_source(directory, self.inputs["baseline"])
            target = directory / "src/hnswutils.c"
            target.unlink()
            target.symlink_to(REPOSITORY / "src/hnswutils.c")
            with self.assertRaisesRegex(instrument.InstrumentationError, "regular file"):
                instrument.instrument(directory)


if __name__ == "__main__":
    unittest.main()
