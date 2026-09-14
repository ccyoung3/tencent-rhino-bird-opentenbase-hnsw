# HNSW build diagnostic report

- Status: `passed`
- Rows / dimensions: `10000` / `100`
- `maintenance_work_mem`: `64MB`
- `m` / `ef_construction`: `16` / `64`
- Requested parallel workers: `2`
- Container image: `opentenbase-pg18-pgvector:timing-v1-arm64`
- Launched parallel workers: `2`
- Build time: `2.162s`
- Index size: `7462912` bytes
- Approximate peak container-memory delta: `69.31 MiB`
- Verification query used HNSW: `true`

## Sampled phase timeline

| Phase | First seen | Last seen | Sampled span | Tuple progress | Samples |
|---|---:|---:|---:|---:|---:|
| building index: loading tuples in memory | 0.007s | 1.471s | 1.464s | 0.520%–81.580% | 3 |

## Internal build timing

- Timing status: `complete`.
- Internal HNSW elapsed wall time: `1.921676s`.
- One leader timeline; not summed worker CPU time, full CREATE INDEX time, or commit latency.

| Internal phase | Elapsed |
|---|---:|
| setup | 0.000057s |
| memory_build | 1.884444s |
| spill_drain | N/A (not executed) |
| flush | 0.025314s |
| disk_insert | N/A (not executed) |
| finalize | 0.005909s |
| wal | 0.005937s |
| cleanup | 0.000015s |

### Evidence → judgment → recommendation → revalidation

- Evidence: `memory_build` has the largest measured interval (98.1% of internal elapsed time); spill=`False`.
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

## GloVe 同索引召回验证

- 调参集选出的最小达标 ef_search：`200`。不是业务最优保证。
- 验证集不参与选参；0.95 等目标是实验口径，非官方标准。
- 严格 ID 重合 Recall@10；重复计时不增加独立查询数。
- 每次计时前执行同一查询取得结果；随机化配置/查询/重复顺序。耗时为暖缓存服务器执行时间，不是业务端到端延迟。

| 查询集 | ef_search | 独立查询数 | 平均 Recall@10 | p50 ms | p95 ms | 低于目标 |
|---|---:|---:|---:|---:|---:|---|
| tuning | 10 | 10 | 0.6300 | 0.345 | 0.449 | True |
| tuning | 40 | 10 | 0.8900 | 0.834 | 1.267 | True |
| tuning | 100 | 10 | 0.9400 | 1.476 | 1.958 | True |
| tuning | 200 | 10 | 0.9800 | 2.982 | 3.818 | False |
| tuning | 400 | 10 | 1.0000 | 5.001 | 10.673 | False |
| validation | 10 | 20 | 0.5350 | 0.218 | 0.467 | True |
| validation | 40 | 20 | 0.8450 | 0.575 | 0.893 | True |
| validation | 200 | 20 | 0.9800 | 2.915 | 4.017 | False |

提高 ef_search 的收益与成本属于参数调整，不是 C 补丁的算法加速。
若独立验证未达标或延迟代价不可接受，本轮不自动重建/继续扩大参数搜索。
