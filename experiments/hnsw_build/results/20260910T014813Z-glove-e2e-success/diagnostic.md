# HNSW build diagnostic report

- Status: `passed`
- Rows / dimensions: `10000` / `100`
- `maintenance_work_mem`: `64MB`
- `m` / `ef_construction`: `16` / `64`
- Requested parallel workers: `2`
- Container image: `opentenbase-pg18-pgvector:timing-v1-arm64`
- Launched parallel workers: `2`
- Build time: `0.671s`
- Index size: `7462912` bytes
- Approximate peak container-memory delta: `64.59 MiB`
- Verification query used HNSW: `true`

## Sampled phase timeline

| Phase | First seen | Last seen | Sampled span | Tuple progress | Samples |
|---|---:|---:|---:|---:|---:|
| building index: loading tuples in memory | 0.003s | 0.003s | 0.000s | 0.000%–0.000% | 1 |

## Internal build timing

- Timing status: `complete`.
- Internal HNSW elapsed wall time: `0.511093s`.
- One leader timeline; not summed worker CPU time, full CREATE INDEX time, or commit latency.

| Internal phase | Elapsed |
|---|---:|
| setup | 0.000030s |
| memory_build | 0.497407s |
| spill_drain | N/A (not executed) |
| flush | 0.009333s |
| disk_insert | N/A (not executed) |
| finalize | 0.002175s |
| wal | 0.002141s |
| cleanup | 0.000007s |

### Evidence → judgment → recommendation → revalidation

- Evidence: `memory_build` has the largest measured interval (97.3% of internal elapsed time); spill=`False`.
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

- 调参集选出的最小达标 ef_search：`100`。不是业务最优保证。
- 验证集不参与选参；0.95 等目标是实验口径，非官方标准。
- 严格 ID 重合 Recall@10；重复计时不增加独立查询数。
- 每次计时前执行同一查询取得结果；随机化配置/查询/重复顺序。耗时为暖缓存服务器执行时间，不是业务端到端延迟。

| 查询集 | ef_search | 独立查询数 | 平均 Recall@10 | p50 ms | p95 ms | 低于目标 |
|---|---:|---:|---:|---:|---:|---|
| tuning | 10 | 10 | 0.6900 | 0.071 | 0.080 | True |
| tuning | 40 | 10 | 0.8800 | 0.171 | 0.331 | True |
| tuning | 100 | 10 | 0.9500 | 0.316 | 0.727 | False |
| tuning | 200 | 10 | 0.9800 | 0.569 | 1.049 | False |
| tuning | 400 | 10 | 1.0000 | 0.992 | 1.843 | False |
| validation | 10 | 20 | 0.5400 | 0.076 | 0.092 | True |
| validation | 40 | 20 | 0.8400 | 0.168 | 0.292 | True |
| validation | 100 | 20 | 0.9350 | 0.338 | 0.482 | True |

提高 ef_search 的收益与成本属于参数调整，不是 C 补丁的算法加速。
若独立验证未达标或延迟代价不可接受，本轮不自动重建/继续扩大参数搜索。
