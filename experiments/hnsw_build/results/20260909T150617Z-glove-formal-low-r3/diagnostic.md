# HNSW build diagnostic report

- Status: `passed`
- Rows / dimensions: `1183514` / `100`
- `maintenance_work_mem`: `1024MB`
- `m` / `ef_construction`: `16` / `64`
- Requested parallel workers: `2`
- Container image: `opentenbase-pg18-pgvector:timing-v1-arm64`
- Launched parallel workers: `2`
- Build time: `1730.185s`
- Index size: `881418240` bytes
- Approximate peak container-memory delta: `1.00 GiB`
- Verification query used HNSW: `true`

## Sampled phase timeline

| Phase | First seen | Last seen | Sampled span | Tuple progress | Samples |
|---|---:|---:|---:|---:|---:|
| building index: loading tuples in memory | 0.004s | 332.884s | 332.880s | 0.000%–83.491% | 436 |
| building index: flushing in-memory graph | 333.651s | 345.223s | 11.572s | 83.512%–83.512% | 13 |
| building index: loading tuples on disk | 345.967s | 1724.863s | 1378.896s | 83.514%–99.999% | 1591 |
| building index: writing index pages to WAL | 1725.588s | 1729.420s | 3.832s | 100.000%–100.000% | 6 |

## Internal build timing

- Timing status: `complete`.
- Internal HNSW elapsed wall time: `1729.963229s`.
- One leader timeline; not summed worker CPU time, full CREATE INDEX time, or commit latency.

| Internal phase | Elapsed |
|---|---:|
| setup | 0.000042s |
| memory_build | 333.151620s |
| spill_drain | 0.000088s |
| flush | 12.575805s |
| disk_insert | 1379.303045s |
| finalize | 0.105244s |
| wal | 4.827364s |
| cleanup | 0.000021s |

### Evidence → judgment → recommendation → revalidation

- Evidence: `disk_insert` has the largest measured interval (79.7% of internal elapsed time); spill=`True`.
- Judgment: this locates elapsed time, not a causal CPU/I/O attribution. The memory interval includes scan and worker startup; spill drain includes outstanding memory inserts and coordination; disk insertion includes scan/waits until scans finish. Flush measures page materialization, not storage-device fsync latency.
- Recommendation: if memory headroom permits, raise maintenance_work_mem; keep the same data, image, workers, m and ef_construction.
- Revalidation: compare repeated low/high-memory runs; verify spill/disk becomes N/A, then compare internal and command elapsed time and peak memory. Do not claim a speedup from this single run.

## Diagnosis

- The graph spilled after `988380` tuples.
- Spill context: `1069547520` bytes used, `1070596096` bytes nominal limit, dimensions `100`, `m=16`, `ef_construction=64`.
- Parallel builds reserve an allocation safety margin of `1.00 MiB` and trigger when graph memory plus that margin reaches the nominal limit. For this run the effective trigger threshold was `1069547520` bytes, so reported memory used may be below the nominal limit.
- Recommendation: if the host has enough headroom, increase `maintenance_work_mem` and rerun the same workload; accept the change only if spill disappears or build time improves without unsafe memory use.
- Observed phase order monotonic: `true`.

## Interpretation limits

- The sampled timeline contains sampled spans, not exact instrumentation; a short phase may be missed. Internal timing, when enabled, is reported separately.
- Tuple percentage is `tuples_done / requested rows`; the input must contain only indexable, non-null vectors.
- Container memory includes the database process and supporting state, not only HNSW.
- Mac ARM64 results support local functional and relative claims, not production sizing.
