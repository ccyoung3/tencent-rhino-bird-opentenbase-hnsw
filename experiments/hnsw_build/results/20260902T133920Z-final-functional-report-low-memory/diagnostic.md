# HNSW build diagnostic report

- Status: `passed`
- Rows / dimensions: `10000` / `32`
- `maintenance_work_mem`: `1MB`
- `m` / `ef_construction`: `16` / `64`
- Requested parallel workers: `0`
- Container image: `opentenbase-pg18-pgvector:diagnostics-v2-arm64`
- Launched parallel workers: `0`
- Build time: `13.288s`
- Index size: `4349952` bytes
- Approximate peak container-memory delta: `7.57 MiB`
- Verification query used HNSW: `true`

## Sampled phase timeline

| Phase | First seen | Last seen | Sampled span | Tuple progress | Samples |
|---|---:|---:|---:|---:|---:|
| building index: loading tuples in memory | 0.004s | 0.148s | 0.144s | 0.340%–8.930% | 2 |
| building index: loading tuples on disk | 0.312s | 12.977s | 12.666s | 13.340%–99.690% | 67 |

## Diagnosis

- The graph spilled after `1239` tuples.
- Spill context: `2097024` bytes used, `1048576` bytes effective limit, dimensions `32`, `m=16`, `ef_construction=64`.
- Recommendation: if the host has enough headroom, increase `maintenance_work_mem` and rerun the same workload; accept the change only if spill disappears or build time improves without unsafe memory use.
- Observed phase order monotonic: `true`.

## Interpretation limits

- Phase times are sampled spans, not exact instrumentation; a short phase may be missed.
- Tuple percentage is `tuples_done / requested rows` for this generated all-non-null dataset.
- Container memory includes the database process and supporting state, not only HNSW.
- Mac ARM64 results support local functional and relative claims, not production sizing.
