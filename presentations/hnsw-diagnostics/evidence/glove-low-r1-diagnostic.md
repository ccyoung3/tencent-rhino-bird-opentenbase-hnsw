# HNSW build diagnostic report

- Status: `passed`
- Rows / dimensions: `1183514` / `100`
- `maintenance_work_mem`: `1024MB`
- `m` / `ef_construction`: `16` / `64`
- Requested parallel workers: `2`
- Container image: `opentenbase-pg18-pgvector:timing-v1-arm64`
- Launched parallel workers: `2`
- Build time: `1414.649s`
- Index size: `881410048` bytes
- Approximate peak container-memory delta: `1.01 GiB`
- Verification query used HNSW: `true`

## Sampled phase timeline

| Phase | First seen | Last seen | Sampled span | Tuple progress | Samples |
|---|---:|---:|---:|---:|---:|
| building index: loading tuples in memory | 0.007s | 421.091s | 421.084s | 0.000%–83.469% | 542 |
| building index: flushing in-memory graph | 421.846s | 427.348s | 5.502s | 83.515%–83.515% | 8 |
| building index: loading tuples on disk | 428.081s | 1409.327s | 981.246s | 83.516%–99.992% | 1297 |
| building index: writing index pages to WAL | 1409.949s | 1413.689s | 3.740s | 100.000%–100.000% | 6 |

## Internal build timing

- Timing status: `complete`.
- Internal HNSW elapsed wall time: `1414.450097s`.
- One leader timeline; not summed worker CPU time, full CREATE INDEX time, or commit latency.

| Internal phase | Elapsed |
|---|---:|
| setup | 0.000116s |
| memory_build | 421.454772s |
| spill_drain | 0.001356s |
| flush | 6.367296s |
| disk_insert | 982.004717s |
| finalize | 0.066267s |
| wal | 4.555544s |
| cleanup | 0.000029s |

### Evidence → judgment → recommendation → revalidation

- Evidence: `disk_insert` has the largest measured interval (69.4% of internal elapsed time); spill=`True`.
- Judgment: this locates elapsed time, not a causal CPU/I/O attribution. The memory interval includes scan and worker startup; spill drain includes outstanding memory inserts and coordination; disk insertion includes scan/waits until scans finish. Flush measures page materialization, not storage-device fsync latency.
- Recommendation: if memory headroom permits, raise maintenance_work_mem; keep the same data, image, workers, m and ef_construction.
- Revalidation: compare repeated low/high-memory runs; verify spill/disk becomes N/A, then compare internal and command elapsed time and peak memory. Do not claim a speedup from this single run.

## Diagnosis

- The graph spilled after `988413` tuples.
- Spill context: `1069548088` bytes used, `1070596096` bytes nominal limit, dimensions `100`, `m=16`, `ef_construction=64`.
- Parallel builds reserve an allocation safety margin of `1.00 MiB` and trigger when graph memory plus that margin reaches the nominal limit. For this run the effective trigger threshold was `1069547520` bytes, so reported memory used may be below the nominal limit.
- Recommendation: if the host has enough headroom, increase `maintenance_work_mem` and rerun the same workload; accept the change only if spill disappears or build time improves without unsafe memory use.
- Observed phase order monotonic: `true`.

## Interpretation limits

- The sampled timeline contains sampled spans, not exact instrumentation; a short phase may be missed. Internal timing, when enabled, is reported separately.
- Tuple percentage is `tuples_done / requested rows`; the input must contain only indexable, non-null vectors.
- Container memory includes the database process and supporting state, not only HNSW.
- Mac ARM64 results support local functional and relative claims, not production sizing.
