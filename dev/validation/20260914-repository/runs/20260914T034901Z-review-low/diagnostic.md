# HNSW build diagnostic report

- Status: `passed`
- Rows / dimensions: `10000` / `32`
- `maintenance_work_mem`: `1MB`
- `m` / `ef_construction`: `16` / `64`
- Requested parallel workers: `0`
- Container image: `opentenbase-pg18-pgvector:review-arm64`
- Launched parallel workers: `0`
- Build time: `3.458s`
- Index size: `4358144` bytes
- Approximate peak container-memory delta: `13.55 MiB`
- Verification query used HNSW: `true`

## Sampled phase timeline

| Phase | First seen | Last seen | Sampled span | Tuple progress | Samples |
|---|---:|---:|---:|---:|---:|
| building index: loading tuples in memory | 0.002s | 0.002s | 0.000s | 0.350%–0.350% | 1 |
| building index: loading tuples on disk | 0.586s | 2.913s | 2.327s | 27.370%–89.590% | 5 |

## Internal build timing

- Timing status: `complete`.
- Internal HNSW elapsed wall time: `3.329737s`.
- One leader timeline; not summed worker CPU time, full CREATE INDEX time, or commit latency.

| Internal phase | Elapsed |
|---|---:|
| setup | 0.000016s |
| memory_build | 0.108647s |
| spill_drain | 0.000016s |
| flush | 0.000751s |
| disk_insert | 3.219562s |
| finalize | 0.000000s |
| wal | 0.000725s |
| cleanup | 0.000020s |

### Evidence → judgment → recommendation → revalidation

- Evidence: `disk_insert` has the largest measured interval (96.7% of internal elapsed time); spill=`True`.
- Judgment: this locates elapsed time, not a causal CPU/I/O attribution. The memory interval includes scan and worker startup; spill drain includes outstanding memory inserts and coordination; disk insertion includes scan/waits until scans finish. Flush measures page materialization, not storage-device fsync latency.
- Recommendation: if memory headroom permits, raise maintenance_work_mem; keep the same data, image, workers, m and ef_construction.
- Revalidation: compare repeated low/high-memory runs; verify spill/disk becomes N/A, then compare internal and command elapsed time and peak memory. Do not claim a speedup from this single run.

## Diagnosis

- The graph spilled after `1242` tuples.
- Spill context: `2097024` bytes used, `1048576` bytes nominal limit, dimensions `32`, `m=16`, `ef_construction=64`.
- Recommendation: if the host has enough headroom, increase `maintenance_work_mem` and rerun the same workload; accept the change only if spill disappears or build time improves without unsafe memory use.
- Observed phase order monotonic: `true`.

## Interpretation limits

- The sampled timeline contains sampled spans, not exact instrumentation; a short phase may be missed. Internal timing, when enabled, is reported separately.
- Tuple percentage is `tuples_done / requested rows`; the input must contain only indexable, non-null vectors.
- Container memory includes the database process and supporting state, not only HNSW.
- Mac ARM64 results support local functional and relative claims, not production sizing.
