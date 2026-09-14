# HNSW build diagnostic report

- Status: `passed`
- Rows / dimensions: `1183514` / `100`
- `maintenance_work_mem`: `1024MB`
- `m` / `ef_construction`: `16` / `64`
- Requested parallel workers: `2`
- Container image: `opentenbase-pg18-pgvector:timing-v1-arm64`
- Launched parallel workers: `2`
- Build time: `1114.468s`
- Index size: `881410048` bytes
- Approximate peak container-memory delta: `996.52 MiB`
- Verification query used HNSW: `true`

## Sampled phase timeline

| Phase | First seen | Last seen | Sampled span | Tuple progress | Samples |
|---|---:|---:|---:|---:|---:|
| building index: loading tuples in memory | 0.005s | 252.190s | 252.185s | 0.000%–83.463% | 359 |
| building index: flushing in-memory graph | 252.879s | 255.571s | 2.692s | 83.503%–83.503% | 5 |
| building index: loading tuples on disk | 256.230s | 1111.124s | 854.894s | 83.504%–99.994% | 1174 |
| building index: writing index pages to WAL | 1111.763s | 1113.711s | 1.948s | 100.000%–100.000% | 4 |

## Internal build timing

- Timing status: `complete`.
- Internal HNSW elapsed wall time: `1114.206656s`.
- One leader timeline; not summed worker CPU time, full CREATE INDEX time, or commit latency.

| Internal phase | Elapsed |
|---|---:|
| setup | 0.000052s |
| memory_build | 252.343070s |
| spill_drain | 0.001280s |
| flush | 3.873814s |
| disk_insert | 855.368671s |
| finalize | 0.061013s |
| wal | 2.558736s |
| cleanup | 0.000020s |

### Evidence → judgment → recommendation → revalidation

- Evidence: `disk_insert` has the largest measured interval (76.8% of internal elapsed time); spill=`True`.
- Judgment: this locates elapsed time, not a causal CPU/I/O attribution. The memory interval includes scan and worker startup; spill drain includes outstanding memory inserts and coordination; disk insertion includes scan/waits until scans finish. Flush measures page materialization, not storage-device fsync latency.
- Recommendation: if memory headroom permits, raise maintenance_work_mem; keep the same data, image, workers, m and ef_construction.
- Revalidation: compare repeated low/high-memory runs; verify spill/disk becomes N/A, then compare internal and command elapsed time and peak memory. Do not claim a speedup from this single run.

## Diagnosis

- The graph spilled after `988275` tuples.
- Spill context: `1069548408` bytes used, `1070596096` bytes nominal limit, dimensions `100`, `m=16`, `ef_construction=64`.
- Parallel builds reserve an allocation safety margin of `1.00 MiB` and trigger when graph memory plus that margin reaches the nominal limit. For this run the effective trigger threshold was `1069547520` bytes, so reported memory used may be below the nominal limit.
- Recommendation: if the host has enough headroom, increase `maintenance_work_mem` and rerun the same workload; accept the change only if spill disappears or build time improves without unsafe memory use.
- Observed phase order monotonic: `true`.

## Interpretation limits

- The sampled timeline contains sampled spans, not exact instrumentation; a short phase may be missed. Internal timing, when enabled, is reported separately.
- Tuple percentage is `tuples_done / requested rows`; the input must contain only indexable, non-null vectors.
- Container memory includes the database process and supporting state, not only HNSW.
- Mac ARM64 results support local functional and relative claims, not production sizing.
