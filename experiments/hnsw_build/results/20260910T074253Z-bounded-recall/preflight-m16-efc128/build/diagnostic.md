# HNSW build diagnostic report

- Status: `passed`
- Rows / dimensions: `100000` / `100`
- `maintenance_work_mem`: `1792MB`
- `m` / `ef_construction`: `16` / `128`
- Requested parallel workers: `2`
- Container image: `opentenbase-pg18-pgvector:timing-v1-arm64`
- Launched parallel workers: `2`
- Build time: `17.462s`
- Index size: `74481664` bytes
- Approximate peak container-memory delta: `1.76 GiB`
- Verification query used HNSW: `true`

## Sampled phase timeline

| Phase | First seen | Last seen | Sampled span | Tuple progress | Samples |
|---|---:|---:|---:|---:|---:|
| building index: loading tuples in memory | 0.003s | 16.288s | 16.285s | 0.000%–97.442% | 27 |
| building index: flushing in-memory graph | 16.932s | 16.932s | 0.000s | 99.990%–99.990% | 1 |

## Internal build timing

- Timing status: `complete`.
- Internal HNSW elapsed wall time: `17.370943s`.
- One leader timeline; not summed worker CPU time, full CREATE INDEX time, or commit latency.

| Internal phase | Elapsed |
|---|---:|
| setup | 0.000019s |
| memory_build | 16.984093s |
| spill_drain | N/A (not executed) |
| flush | 0.167827s |
| disk_insert | N/A (not executed) |
| finalize | 0.075673s |
| wal | 0.143314s |
| cleanup | 0.000017s |

### Evidence → judgment → recommendation → revalidation

- Evidence: `memory_build` has the largest measured interval (97.8% of internal elapsed time); spill=`False`.
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
