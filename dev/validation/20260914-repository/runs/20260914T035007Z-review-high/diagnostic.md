# HNSW build diagnostic report

- Status: `passed`
- Rows / dimensions: `10000` / `32`
- `maintenance_work_mem`: `64MB`
- `m` / `ef_construction`: `16` / `64`
- Requested parallel workers: `0`
- Container image: `opentenbase-pg18-pgvector:review-arm64`
- Launched parallel workers: `0`
- Build time: `1.293s`
- Index size: `4358144` bytes
- Approximate peak container-memory delta: `13.37 MiB`
- Verification query used HNSW: `true`

## Sampled phase timeline

| Phase | First seen | Last seen | Sampled span | Tuple progress | Samples |
|---|---:|---:|---:|---:|---:|
| building index: loading tuples in memory | 0.002s | 1.183s | 1.182s | 0.940%–99.050% | 3 |

## Internal build timing

- Timing status: `complete`.
- Internal HNSW elapsed wall time: `1.196784s`.
- One leader timeline; not summed worker CPU time, full CREATE INDEX time, or commit latency.

| Internal phase | Elapsed |
|---|---:|
| setup | 0.000021s |
| memory_build | 1.189969s |
| spill_drain | N/A (not executed) |
| flush | 0.006000s |
| disk_insert | N/A (not executed) |
| finalize | 0.000000s |
| wal | 0.000778s |
| cleanup | 0.000016s |

### Evidence → judgment → recommendation → revalidation

- Evidence: `memory_build` has the largest measured interval (99.4% of internal elapsed time); spill=`False`.
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
