# HNSW build diagnostic report

- Status: `passed`
- Rows / dimensions: `100000` / `64`
- `maintenance_work_mem`: `256MB`
- `m` / `ef_construction`: `16` / `64`
- Requested parallel workers: `0`
- Container image: `opentenbase-pg18-pgvector:diagnostics-v2-arm64`
- Launched parallel workers: `0`
- Build time: `110.181s`
- Index size: `57016320` bytes
- Approximate peak container-memory delta: `29.91 MiB`
- Verification query used HNSW: `true`

## Sampled phase timeline

| Phase | First seen | Last seen | Sampled span | Tuple progress | Samples |
|---|---:|---:|---:|---:|---:|
| building index: loading tuples in memory | 0.006s | 109.202s | 109.196s | 0.109%–99.895% | 420 |
| building index: flushing in-memory graph | 109.376s | 109.376s | 0.000s | 100.000%–100.000% | 1 |
| building index: writing index pages to WAL | 109.556s | 109.731s | 0.175s | 100.000%–100.000% | 2 |

## Diagnosis

- No HNSW memory spill NOTICE was observed in this run.
- Observed phase order monotonic: `true`.

## Interpretation limits

- Phase times are sampled spans, not exact instrumentation; a short phase may be missed.
- Tuple percentage is `tuples_done / requested rows` for this generated all-non-null dataset.
- Container memory includes the database process and supporting state, not only HNSW.
- Mac ARM64 results support local functional and relative claims, not production sizing.
