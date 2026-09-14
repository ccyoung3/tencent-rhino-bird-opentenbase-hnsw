# HNSW build diagnostic report

- Status: `passed`
- Rows / dimensions: `1183514` / `100`
- `maintenance_work_mem`: `1792MB`
- `m` / `ef_construction`: `16` / `64`
- Requested parallel workers: `2`
- Container image: `opentenbase-pg18-pgvector:timing-v1-arm64`
- Launched parallel workers: `2`
- Build time: `315.599s`
- Index size: `881410048` bytes
- Approximate peak container-memory delta: `1.77 GiB`
- Verification query used HNSW: `true`

## Sampled phase timeline

| Phase | First seen | Last seen | Sampled span | Tuple progress | Samples |
|---|---:|---:|---:|---:|---:|
| building index: loading tuples in memory | 0.006s | 308.601s | 308.595s | 0.000%–99.994% | 439 |
| building index: flushing in-memory graph | 309.256s | 311.863s | 2.607s | 100.000%–100.000% | 5 |
| building index: writing index pages to WAL | 312.461s | 315.241s | 2.780s | 100.000%–100.000% | 5 |

## Internal build timing

- Timing status: `complete`.
- Internal HNSW elapsed wall time: `315.191740s`.
- One leader timeline; not summed worker CPU time, full CREATE INDEX time, or commit latency.

| Internal phase | Elapsed |
|---|---:|
| setup | 0.000050s |
| memory_build | 308.439790s |
| spill_drain | N/A (not executed) |
| flush | 3.375461s |
| disk_insert | N/A (not executed) |
| finalize | 0.067008s |
| wal | 3.309420s |
| cleanup | 0.000011s |

### Evidence → judgment → recommendation → revalidation

- Evidence: `memory_build` has the largest measured interval (97.9% of internal elapsed time); spill=`False`.
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

- 调参集选出的最小达标 ef_search：`None`。不是业务最优保证。
- 验证集不参与选参；0.95 等目标是实验口径，非官方标准。
- 严格 ID 重合 Recall@10；重复计时不增加独立查询数。
- 每次计时前执行同一查询取得结果；随机化配置/查询/重复顺序。耗时为暖缓存服务器执行时间，不是业务端到端延迟。

| 查询集 | ef_search | 独立查询数 | 平均 Recall@10 | p50 ms | p95 ms | 低于目标 |
|---|---:|---:|---:|---:|---:|---|
| tuning | 10 | 200 | 0.4655 | 0.309 | 0.770 | True |
| tuning | 40 | 200 | 0.6905 | 1.031 | 2.397 | True |
| tuning | 100 | 200 | 0.8055 | 2.363 | 4.576 | True |
| tuning | 200 | 200 | 0.8545 | 4.324 | 7.332 | True |
| tuning | 400 | 200 | 0.8945 | 7.999 | 13.375 | True |
| validation | 10 | 1000 | 0.4798 | 0.449 | 1.189 | True |
| validation | 40 | 1000 | 0.6906 | 1.443 | 2.924 | True |
| validation | 400 | 1000 | 0.8971 | 9.876 | 17.440 | True |

提高 ef_search 的收益与成本属于参数调整，不是 C 补丁的算法加速。
若独立验证未达标或延迟代价不可接受，本轮不自动重建/继续扩大参数搜索。
