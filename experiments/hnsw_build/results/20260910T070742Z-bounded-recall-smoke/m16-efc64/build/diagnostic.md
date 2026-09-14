# HNSW build diagnostic report

- Status: `passed`
- Rows / dimensions: `10000` / `100`
- `maintenance_work_mem`: `1792MB`
- `m` / `ef_construction`: `16` / `64`
- Requested parallel workers: `2`
- Container image: `opentenbase-pg18-pgvector:timing-v1-arm64`
- Launched parallel workers: `2`
- Build time: `0.880s`
- Index size: `7462912` bytes
- Approximate peak container-memory delta: `1.75 GiB`
- Verification query used HNSW: `true`

## Sampled phase timeline

| Phase | First seen | Last seen | Sampled span | Tuple progress | Samples |
|---|---:|---:|---:|---:|---:|
| building index: loading tuples in memory | 0.003s | 0.595s | 0.592s | 0.000%–88.900% | 2 |

## Internal build timing

- Timing status: `complete`.
- Internal HNSW elapsed wall time: `0.749042s`.
- One leader timeline; not summed worker CPU time, full CREATE INDEX time, or commit latency.

| Internal phase | Elapsed |
|---|---:|
| setup | 0.000108s |
| memory_build | 0.677561s |
| spill_drain | N/A (not executed) |
| flush | 0.011117s |
| disk_insert | N/A (not executed) |
| finalize | 0.058127s |
| wal | 0.002121s |
| cleanup | 0.000008s |

### Evidence → judgment → recommendation → revalidation

- Evidence: `memory_build` has the largest measured interval (90.5% of internal elapsed time); spill=`False`.
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
