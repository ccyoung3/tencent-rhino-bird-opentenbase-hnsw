# HNSW build diagnostic report

- Status: `passed`
- Rows / dimensions: `20000` / `64`
- `maintenance_work_mem`: `8MB`
- `m` / `ef_construction`: `16` / `64`
- Requested parallel workers: `2`
- Container image: `opentenbase-pg18-pgvector:diagnostics-v2-arm64`
- Launched parallel workers: `2`
- Build time: `17.762s`
- Index size: `11403264` bytes
- Approximate peak container-memory delta: `37.37 MiB`
- Verification query used HNSW: `true`

## Sampled phase timeline

| Phase | First seen | Last seen | Sampled span | Tuple progress | Samples |
|---|---:|---:|---:|---:|---:|
| building index: loading tuples in memory | 0.004s | 0.329s | 0.324s | 0.000%–16.495% | 3 |
| building index: loading tuples on disk | 0.518s | 17.008s | 16.490s | 22.445%–99.125% | 69 |
| building index: writing index pages to WAL | 17.278s | 17.278s | 0.000s | 100.000%–100.000% | 1 |

## Diagnosis

- The graph spilled after `4476` tuples.
- Spill context: `4195168` bytes used, `5242880` bytes effective limit, dimensions `64`, `m=16`, `ef_construction=64`.
- Recommendation: if the host has enough headroom, increase `maintenance_work_mem` and rerun the same workload; accept the change only if spill disappears or build time improves without unsafe memory use.
- Observed phase order monotonic: `true`.

## Interpretation limits

- Phase times are sampled spans, not exact instrumentation; a short phase may be missed.
- Tuple percentage is `tuples_done / requested rows` for this generated all-non-null dataset.
- Container memory includes the database process and supporting state, not only HNSW.
- Mac ARM64 results support local functional and relative claims, not production sizing.
