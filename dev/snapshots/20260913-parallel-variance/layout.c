#include "postgres.h"
#include "portability/instr_time.h"
#include "access/relscan.h"
#include "src/hnsw.h"
#include <stddef.h>
#include <stdio.h>
#undef printf

#define FIELD(T, F) printf(#T "." #F " offset=%zu size=%zu\n", \
                            offsetof(T, F), sizeof(((T *) 0)->F))
int main(void)
{
    size_t line, base;
    printf("PG_VERSION_NUM=%d ALIGNOF_BUFFER=%d PG_CACHE_LINE_SIZE=%d\n",
           PG_VERSION_NUM, ALIGNOF_BUFFER, PG_CACHE_LINE_SIZE);
    printf("slock=%zu LWLock=%zu CV=%zu instr_time=%zu graph=%zu shared=%zu scan=%zu blockscan=%zu\n",
           sizeof(slock_t), sizeof(LWLock), sizeof(ConditionVariable), sizeof(instr_time),
           sizeof(HnswGraph), sizeof(HnswShared), sizeof(ParallelTableScanDescData),
           sizeof(ParallelBlockTableScanDescData));
    FIELD(HnswGraph, lock); FIELD(HnswGraph, head); FIELD(HnswGraph, indtuples);
    FIELD(HnswGraph, entryLock); FIELD(HnswGraph, entryWaitLock);
    FIELD(HnswGraph, allocatorLock); FIELD(HnswGraph, memoryUsed);
    FIELD(HnswGraph, memoryTotal); FIELD(HnswGraph, flushLock); FIELD(HnswGraph, flushed);
    FIELD(HnswShared, workersdonecv); FIELD(HnswShared, mutex);
    FIELD(HnswShared, nparticipantsdone); FIELD(HnswShared, reltuples);
    FIELD(HnswShared, graphData);
    FIELD(ParallelBlockTableScanDescData, phs_mutex);
    FIELD(ParallelBlockTableScanDescData, phs_nallocated);
    printf("parallel_scan_offset=%zu nallocated_from_shared=%zu\n",
           (size_t) BUFFERALIGN(sizeof(HnswShared)),
           (size_t) BUFFERALIGN(sizeof(HnswShared)) +
           offsetof(ParallelBlockTableScanDescData, phs_nallocated));
#ifdef PROGRESS_HNSW_PHASE_LOAD_DISK
    FIELD(HnswGraph, buildPhase); FIELD(HnswGraph, timing);
    FIELD(HnswGraphTiming, enabled); FIELD(HnswGraphTiming, spillRequested);
    FIELD(HnswGraphTiming, flushStarted); FIELD(HnswGraphTiming, flushFinished);
    for (line = 64; line <= 128; line *= 2)
        for (base = 0; base < line; base += ALIGNOF_BUFFER)
        {
            size_t graph = base + offsetof(HnswShared, graphData);
            size_t phase = graph + offsetof(HnswGraph, buildPhase);
            printf("line=%zu assumed_shared_base_mod_line=%zu phase_with_graph_lock=%d phase_with_indtuples=%d phase_with_flushLock=%d\n",
                   line, base,
                   phase / line == (graph + offsetof(HnswGraph, lock)) / line,
                   phase / line == (graph + offsetof(HnswGraph, indtuples)) / line,
                   phase / line == (graph + offsetof(HnswGraph, flushLock)) / line);
        }
#else
    (void) line; (void) base;
#endif
    return 0;
}
