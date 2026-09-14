#!/usr/bin/env python3
"""Instrument an isolated pgvector v0.8.6/baseline or candidate source copy.

This is a mechanism experiment, not product code or an overhead acceptance
measurement. The generator changes no random-number calls and adds no shared
counters, per-call clocks, or per-call atomics. Only parallel scan participants
activate the process-local counters. A completed participant reports its own
scan_and_insert interval; a worker completion is not whole-command success.

All anchors in all three files are validated before any file is written. A
second invocation, an unexpected source shape, symlink, or checkout is refused.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


MARKER = "HNSW_MECHANISM_TEST_ONLY_V1"
SOURCE_NAMES = ("src/hnsw.h", "src/hnswutils.c", "src/hnswbuild.c")
PRODUCT_ROOT = Path(__file__).resolve().parents[2] / "pgvector"

COUNTER_DECLARATIONS = r'''
/* HNSW_MECHANISM_TEST_ONLY_V1: process-local diagnostic state, never DSM. */
typedef struct HnswMechanismCounters
{
	uint64		distanceCalls;
	uint64		elementsInitialized;
	uint64		callbacksSeen;
	uint64		successfulInserts;
	uint64		levelHistogram[64];
} HnswMechanismCounters;

extern bool hnsw_mechanism_active;
extern HnswMechanismCounters hnsw_mechanism_counters;
'''

COUNTER_DEFINITIONS = r'''
/* HNSW_MECHANISM_TEST_ONLY_V1: each backend owns its own copy. */
bool hnsw_mechanism_active = false;
HnswMechanismCounters hnsw_mechanism_counters;
'''

REPORT_HELPERS = r'''
/* HNSW_MECHANISM_TEST_ONLY_V1: boundary measurements and one local summary. */
static void
HnswMechanismReadUsage(struct rusage *usage)
{
	if (getrusage(RUSAGE_SELF, usage) != 0)
		ereport(ERROR, (errmsg("HNSW mechanism getrusage failed: %m")));
}

static int64
HnswMechanismCPUTime(const struct timeval *start, const struct timeval *end)
{
	return ((int64) end->tv_sec - (int64) start->tv_sec) * INT64CONST(1000000)
		+ (int64) end->tv_usec - (int64) start->tv_usec;
}

static void
HnswMechanismReport(Relation index, const HnswMechanismCounters *counters,
					const struct rusage *cpuStart, const struct rusage *cpuEnd,
					instr_time wallStart, instr_time wallEnd)
{
	StringInfoData buf;
	int64		userCPU = HnswMechanismCPUTime(&cpuStart->ru_utime, &cpuEnd->ru_utime);
	int64		systemCPU = HnswMechanismCPUTime(&cpuStart->ru_stime, &cpuEnd->ru_stime);
	int64		elapsed;
	bool		worker = IsParallelWorker();

	INSTR_TIME_SUBTRACT(wallEnd, wallStart);
	elapsed = (int64) INSTR_TIME_GET_MICROSEC(wallEnd);
	if (userCPU < 0 || systemCPU < 0 || elapsed < 0)
		ereport(ERROR, (errmsg("HNSW mechanism counter clock moved backwards")));

	initStringInfo(&buf);
	appendStringInfo(&buf,
		"{\"schema\":1,\"test_only\":true,\"scope\":\"scan_and_insert\","
		"\"mode\":\"native\",\"role\":\"%s\",\"worker_number\":%d,\"pid\":%d,\"index_oid\":%u,"
		"\"callbacks_seen\":" UINT64_FORMAT ",\"successful_inserts\":" UINT64_FORMAT ","
		"\"distance_calls\":" UINT64_FORMAT ",\"elements_initialized\":" UINT64_FORMAT ","
		"\"user_cpu_us\":" INT64_FORMAT ",\"system_cpu_us\":" INT64_FORMAT ","
		"\"elapsed_us\":" INT64_FORMAT ",\"level_hist\":[",
		worker ? "worker" : "leader", worker ? ParallelWorkerNumber : -1,
		MyProcPid, RelationGetRelid(index), counters->callbacksSeen,
		counters->successfulInserts, counters->distanceCalls,
		counters->elementsInitialized, userCPU, systemCPU, elapsed);
	for (int level = 0; level < 64; level++)
		appendStringInfo(&buf, "%s" UINT64_FORMAT,
						 level == 0 ? "" : ",", counters->levelHistogram[level]);
	appendStringInfoString(&buf, "]}");
	ereport(NOTICE, (errmsg_internal("HNSW_MECHANISM %s", buf.data)));
	pfree(buf.data);
}

'''

SCAN_DECLARATIONS = r'''	struct rusage mechanismCPUStart;
	struct rusage mechanismCPUEnd;
	instr_time	mechanismWallStart;
	instr_time	mechanismWallEnd;
	HnswMechanismCounters mechanismCaptured;
'''

SCAN_ANCHOR = '''\treltuples = table_index_build_scan(heapRel, indexRel, indexInfo,
\t\t\t\t\t\t\t\t\t   true, progress, BuildCallback,
\t\t\t\t\t\t\t\t\t   (void *) &buildstate, scan);
'''

SCAN_REPLACEMENT = r'''	/* Only this participant's scan is counted; final leader flush is outside. */
	if (hnsw_mechanism_active)
		ereport(ERROR, (errmsg("nested HNSW mechanism diagnostic scan")));
	MemSet(&hnsw_mechanism_counters, 0, sizeof(hnsw_mechanism_counters));
	HnswMechanismReadUsage(&mechanismCPUStart);
	INSTR_TIME_SET_CURRENT(mechanismWallStart);
	hnsw_mechanism_active = true;
	PG_TRY();
	{
		reltuples = table_index_build_scan(heapRel, indexRel, indexInfo,
										   true, progress, BuildCallback,
										   (void *) &buildstate, scan);
	}
	PG_FINALLY();
	{
		/* Cancellation/error must not leave a reused backend counting. */
		hnsw_mechanism_active = false;
	}
	PG_END_TRY();
	INSTR_TIME_SET_CURRENT(mechanismWallEnd);
	HnswMechanismReadUsage(&mechanismCPUEnd);
	mechanismCaptured = hnsw_mechanism_counters;
	HnswMechanismReport(indexRel, &mechanismCaptured,
						&mechanismCPUStart, &mechanismCPUEnd,
						mechanismWallStart, mechanismWallEnd);
'''


class InstrumentationError(ValueError):
    """The isolated input did not match the reviewed source contract."""


def replace_once(source: str, anchor: str, replacement: str, label: str) -> str:
    count = source.count(anchor)
    if count != 1:
        raise InstrumentationError(f"{label}: expected one anchor, found {count}")
    return source.replace(anchor, replacement, 1)


def transform(sources: dict[str, str]) -> dict[str, str]:
    """Validate and transform all inputs in memory; do not write any files."""
    if set(sources) != set(SOURCE_NAMES):
        raise InstrumentationError("expected exactly hnsw.h, hnswutils.c and hnswbuild.c")
    for name, source in sources.items():
        if MARKER in source or "hnsw_mechanism_" in source or "HnswMechanism" in source:
            raise InstrumentationError(f"{name}: already instrumented or reserved symbol present")

    result = dict(sources)
    name = "src/hnsw.h"
    anchor = '#include "postgres.h"\n'
    result[name] = replace_once(result[name], anchor, anchor + COUNTER_DECLARATIONS, name + ": declarations")

    name = "src/hnswutils.c"
    source = result[name]
    anchor = '#include "vector.h"\n'
    source = replace_once(source, anchor, anchor + COUNTER_DEFINITIONS, name + ": definitions")
    anchor = '\tif (level > maxLevel)\n\t\tlevel = maxLevel;\n'
    source = replace_once(source, anchor, anchor + r'''
	if (hnsw_mechanism_active)
	{
		Assert(level >= 0 && level < 64);
		hnsw_mechanism_counters.elementsInitialized++;
		hnsw_mechanism_counters.levelHistogram[level]++;
	}
''', name + ": initialized levels")
    anchor = 'HnswGetDistance(Datum a, Datum b, HnswSupport * support)\n{\n'
    source = replace_once(source, anchor, anchor + '''\tif (hnsw_mechanism_active)
\t\thnsw_mechanism_counters.distanceCalls++;
''', name + ": distance calls")
    result[name] = source

    name = "src/hnswbuild.c"
    source = result[name]
    anchor = '#include <limits.h>\n'
    source = replace_once(source, anchor, anchor + '#include <sys/resource.h>\n#include "lib/stringinfo.h"\n#include "portability/instr_time.h"\n', name + ": includes")
    anchor = '''BuildCallback(Relation index, ItemPointer tid, Datum *values,
\t\t\t  bool *isnull, bool tupleIsAlive, void *state)
{
\tHnswBuildState *buildstate = (HnswBuildState *) state;
\tHnswGraph  *graph = buildstate->graph;
\tMemoryContext oldCtx;
'''
    source = replace_once(source, anchor, anchor + '''
\tif (hnsw_mechanism_active)
\t\thnsw_mechanism_counters.callbacksSeen++;
''', name + ": callback count")
    anchor = '\tif (InsertTuple(index, values, isnull, tid, buildstate))\n\t{\n'
    source = replace_once(source, anchor, anchor + '''\t\tif (hnsw_mechanism_active)
\t\t\thnsw_mechanism_counters.successfulInserts++;
''', name + ": successful insert count")
    anchor = "/*\n * Perform a worker's portion of a parallel insert\n */\n"
    source = replace_once(source, anchor, REPORT_HELPERS + anchor, name + ": report helpers")
    anchor = '''HnswParallelScanAndInsert(Relation heapRel, Relation indexRel, HnswShared * hnswshared, char *hnswarea, bool progress)
{
\tHnswBuildState buildstate;
\tTableScanDesc scan;
\tdouble\t\treltuples;
\tIndexInfo  *indexInfo;
'''
    source = replace_once(source, anchor, anchor + SCAN_DECLARATIONS, name + ": boundary locals")
    source = replace_once(source, SCAN_ANCHOR, SCAN_REPLACEMENT, name + ": scan boundary")
    result[name] = source
    return result


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def instrument(source_dir: Path) -> dict:
    source_dir = source_dir.resolve(strict=True)
    if source_dir == PRODUCT_ROOT.resolve() or (source_dir / ".git").exists():
        raise InstrumentationError("refusing a product checkout; provide an isolated source archive copy")
    paths = {name: source_dir / name for name in SOURCE_NAMES}
    for name, path in paths.items():
        if path.is_symlink() or not path.is_file() or path.resolve().parent != source_dir / "src":
            raise InstrumentationError(f"{name}: expected a regular file in the isolated src directory")
    original = {name: path.read_text() for name, path in paths.items()}
    changed = transform(original)
    # Validate every input first, including later files, before applying changes.
    for name, path in paths.items():
        if path.read_text() != original[name]:
            raise InstrumentationError(f"{name}: source changed during generation")
    for name, path in paths.items():
        path.write_text(changed[name])
    return {"schema": 1, "test_only": True, "status": "instrumented", "mode": "native",
            "files": {name: {"before": sha256(original[name]), "after": sha256(changed[name])}
                      for name in SOURCE_NAMES}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_dir", type=Path, help="isolated unpacked pgvector source directory")
    args = parser.parse_args()
    try:
        result = instrument(args.source_dir)
    except (OSError, InstrumentationError) as error:
        parser.exit(2, f"instrumentation refused: {error}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
