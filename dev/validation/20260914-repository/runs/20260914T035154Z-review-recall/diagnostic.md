# HNSW build diagnostic report

- Status: `passed`
- Rows / dimensions: `10000` / `32`
- `maintenance_work_mem`: `64MB`
- `m` / `ef_construction`: `16` / `64`
- Requested parallel workers: `0`
- Container image: `opentenbase-pg18-pgvector:review-arm64`
- Launched parallel workers: `0`
- Build time: `1.269s`
- Index size: `4358144` bytes
- Approximate peak container-memory delta: `10.04 MiB`
- Verification query used HNSW: `true`

## Sampled phase timeline

| Phase | First seen | Last seen | Sampled span | Tuple progress | Samples |
|---|---:|---:|---:|---:|---:|
| building index: loading tuples in memory | 0.002s | 0.587s | 0.586s | 0.250%–56.860% | 2 |

## Internal build timing

- Timing status: `complete`.
- Internal HNSW elapsed wall time: `1.095046s`.
- One leader timeline; not summed worker CPU time, full CREATE INDEX time, or commit latency.

| Internal phase | Elapsed |
|---|---:|
| setup | 0.000067s |
| memory_build | 1.088183s |
| spill_drain | N/A (not executed) |
| flush | 0.006000s |
| disk_insert | N/A (not executed) |
| finalize | 0.000001s |
| wal | 0.000776s |
| cleanup | 0.000019s |

### Evidence → judgment → recommendation → revalidation

- Evidence: `memory_build` has the largest measured interval (99.4% of internal elapsed time); spill=`False`.
- Judgment: this locates elapsed time, not a causal CPU/I/O attribution. The memory interval includes scan and worker startup; spill drain includes outstanding memory inserts and coordination; disk insertion includes scan/waits until scans finish. Flush measures page materialization, not storage-device fsync latency.
- Recommendation: no spill was measured, so this run alone does not justify more build memory.
- Revalidation: repeat the same workload to establish variability before changing one setting.

## Diagnosis

- No HNSW memory spill NOTICE was observed in this run.
- Observed phase order monotonic: `true`.

## Recall@K evaluation

- Query source: `deterministic synthetic holdout sample`.
- Queries / K: `20` / `10`.
- Ground truth: exact distance ordering with HNSW/index scans disabled.
- Approximate path: HNSW forced and verified for every tested `ef_search`.
- No acceptance threshold was supplied, so this run records measurements without inventing a pass/fail decision.

| ef_search | Queries | Mean recall | Median | Min | Max | Median execution | Below threshold |
|---:|---:|---:|---:|---:|---:|---:|:---:|
| 40 | 20 | 0.9750 | 1.0000 | 0.9000 | 1.0000 | 0.6310 ms | unknown |
| 100 | 20 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0020 ms | unknown |
| 200 | 20 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.3965 ms | unknown |

### Diagnosis and adjustment order

- No threshold breach was observed, or no threshold was supplied. Keep the measured curve rather than treating this as a universal guarantee.
- Query execution values come from PostgreSQL `EXPLAIN ANALYZE` Execution Time with node timing disabled; they exclude Docker command startup and should only be compared within the same environment.
- If the highest practical `ef_search` remains insufficient, rebuild with a higher `ef_construction` and then consider a higher `m`; remeasure build time, index size, and memory for every rebuild.
- This deterministic synthetic holdout sample is development and reproducibility evidence. It is independent of the indexed rows, but it is not a public benchmark or a claim that the same recall generalizes to production data.

## Interpretation limits

- The sampled timeline contains sampled spans, not exact instrumentation; a short phase may be missed. Internal timing, when enabled, is reported separately.
- Tuple percentage is `tuples_done / requested rows`; the input must contain only indexable, non-null vectors.
- Container memory includes the database process and supporting state, not only HNSW.
- Mac ARM64 results support local functional and relative claims, not production sizing.
