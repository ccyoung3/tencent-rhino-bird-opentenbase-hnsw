# HNSW build diagnostic report

- Status: `passed`
- Rows / dimensions: `100000` / `100`
- `maintenance_work_mem`: `64MB`
- `m` / `ef_construction`: `16` / `64`
- Requested parallel workers: `2`
- Container image: `opentenbase-pg18-pgvector:timing-v1-arm64`
- Launched parallel workers: `2`
- Build time: `77.086s`
- Index size: `74481664` bytes
- Approximate peak container-memory delta: `120.58 MiB`
- Verification query used HNSW: `true`

## Sampled phase timeline

| Phase | First seen | Last seen | Sampled span | Tuple progress | Samples |
|---|---:|---:|---:|---:|---:|
| building index: loading tuples in memory | 0.008s | 16.190s | 16.182s | 0.000%–55.728% | 22 |
| building index: flushing in-memory graph | 16.919s | 16.919s | 0.000s | 58.165%–58.165% | 1 |
| building index: loading tuples on disk | 17.668s | 76.119s | 58.451s | 58.693%–99.904% | 77 |

## Internal build timing

- Timing status: `complete`.
- Internal HNSW elapsed wall time: `76.685078s`.
- One leader timeline; not summed worker CPU time, full CREATE INDEX time, or commit latency.

| Internal phase | Elapsed |
|---|---:|
| setup | 0.000047s |
| memory_build | 16.868585s |
| spill_drain | 0.000834s |
| flush | 0.187817s |
| disk_insert | 59.295823s |
| finalize | 0.006988s |
| wal | 0.324962s |
| cleanup | 0.000022s |

### Evidence → judgment → recommendation → revalidation

- Evidence: `disk_insert` has the largest measured interval (77.3% of internal elapsed time); spill=`True`.
- Judgment: this locates elapsed time, not a causal CPU/I/O attribution. The memory interval includes scan and worker startup; spill drain includes outstanding memory inserts and coordination; disk insertion includes scan/waits until scans finish. Flush measures page materialization, not storage-device fsync latency.
- Recommendation: if memory headroom permits, raise maintenance_work_mem; keep the same data, image, workers, m and ef_construction.
- Revalidation: compare repeated low/high-memory runs; verify spill/disk becomes N/A, then compare internal and command elapsed time and peak memory. Do not claim a speedup from this single run.

## Diagnosis

- The graph spilled after `58165` tuples.
- Spill context: `62914904` bytes used, `63963136` bytes nominal limit, dimensions `100`, `m=16`, `ef_construction=64`.
- Parallel builds reserve an allocation safety margin of `1.00 MiB` and trigger when graph memory plus that margin reaches the nominal limit. For this run the effective trigger threshold was `62914560` bytes, so reported memory used may be below the nominal limit.
- Recommendation: if the host has enough headroom, increase `maintenance_work_mem` and rerun the same workload; accept the change only if spill disappears or build time improves without unsafe memory use.
- Observed phase order monotonic: `true`.

## Interpretation limits

- The sampled timeline contains sampled spans, not exact instrumentation; a short phase may be missed. Internal timing, when enabled, is reported separately.
- Tuple percentage is `tuples_done / requested rows`; the input must contain only indexable, non-null vectors.
- Container memory includes the database process and supporting state, not only HNSW.
- Mac ARM64 results support local functional and relative claims, not production sizing.
