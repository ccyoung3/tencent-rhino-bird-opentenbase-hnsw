# HNSW build diagnostic report

- Status: `passed`
- Rows / dimensions: `50000` / `64`
- `maintenance_work_mem`: `64MB`
- `m` / `ef_construction`: `16` / `64`
- Requested parallel workers: `0`
- Container image: `opentenbase-pg18-pgvector:timing-v1-arm64`
- Launched parallel workers: `0`
- Build time: `14.402s`
- Index size: `28540928` bytes
- Approximate peak container-memory delta: `43.20 MiB`
- Verification query used HNSW: `true`

## Sampled phase timeline

| Phase | First seen | Last seen | Sampled span | Tuple progress | Samples |
|---|---:|---:|---:|---:|---:|
| building index: loading tuples in memory | 0.005s | 13.593s | 13.588s | 0.084%–96.866% | 22 |

## Internal build timing

- Timing status: `complete`.
- Internal HNSW elapsed wall time: `14.214298s`.
- One leader timeline; not summed worker CPU time, full CREATE INDEX time, or commit latency.

| Internal phase | Elapsed |
|---|---:|
| setup | 0.000034s |
| memory_build | 14.036361s |
| spill_drain | N/A (not executed) |
| flush | 0.063981s |
| disk_insert | N/A (not executed) |
| finalize | 0.000001s |
| wal | 0.113866s |
| cleanup | 0.000055s |

### Evidence → judgment → recommendation → revalidation

- Evidence: `memory_build` has the largest measured interval (98.7% of internal elapsed time); spill=`False`.
- Judgment: this locates elapsed time, not a causal CPU/I/O attribution. The memory interval includes scan and worker startup; spill drain includes outstanding memory inserts and coordination; disk insertion includes scan/waits until scans finish. Flush measures page materialization, not storage-device fsync latency.
- Recommendation: no spill was measured, so this run alone does not justify more build memory.
- Revalidation: repeat the same workload to establish variability before changing one setting.

## Diagnosis

- No HNSW memory spill NOTICE was observed in this run.
- Observed phase order monotonic: `true`.

## Interpretation limits

- The sampled timeline contains sampled spans, not exact instrumentation; a short phase may be missed. Internal timing, when enabled, is reported separately.
- Tuple percentage is `tuples_done / requested rows`; the input must contain only indexable, non-null vectors.
- Container memory includes the database process and supporting state, not only HNSW.
- Mac ARM64 results support local functional and relative claims, not production sizing.
