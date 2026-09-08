---
title: HNSW Recall@K 与参数诊断报告
status: 完成
date: 2026-09-03
updated: 2026-09-04
tags: [opentenbase, pgvector, hnsw, recall, parameters, diagnostics]
---

# HNSW Recall@K 与参数诊断报告

## 结论

在不修改已冻结 C 补丁的前提下，实验工具已增加可选 Recall@K 诊断：用固定种子
的独立 synthetic holdout 查询做精确 Top-K 与 HNSW Top-K 对照，同时校验精确
查询实际走顺序扫描、近似查询实际走目标 HNSW 索引，并记录 PostgreSQL 服务器侧
查询执行时间。低召回现在可以形成“发现问题、判断原因、调整参数、相同查询复验”
的闭环。

本轮 `0.95` 是命令行显式传入的实验目标，不是 OpenTenBase、pgvector 或会议
指定阈值。项目二也没有指定某个官方数据集；本报告用于控制变量和功能诊断，
不冒充公开 benchmark 结果。

## 受控协议

| 项目 | 设置 |
|---|---|
| 环境 | Mac ARM64、Debian ARM64 Docker、每次独立 Compose 数据卷 |
| 镜像 | `opentenbase-pg18-pgvector:diagnostics-v2-seed42-arm64` |
| 数据 | 50,000 行、64 维、SQL seed `0.42` |
| 查询 | 30 个独立 synthetic holdout、query seed `20260903`、K=10 |
| 拓扑 | pgvector 已有 `HNSW_MEMORY` 测试宏固定 HNSW seed 42 |
| 距离/数据分布 | Euclidean L2（`vector_l2_ops`、`<->`）；索引数据与 holdout 均为逐维 synthetic uniform `[0,1)`，但使用独立 PRNG/seed |
| 内存/并行 | `maintenance_work_mem=256MB`、串行、全部配置无 spill |
| 构建参数 | 7 组 `m / ef_construction` 控制配置 |
| 查询参数 | `ef_search=10/20/40/80`；关键配置扩展到 `160/320` |
| 判断口径 | 本轮 mean Recall@10 目标 `0.95`；每个关键配置扩展曲线重复 3 次 |

精确 ground truth 禁用 index/index-only/bitmap scan 并验证 `Seq Scan`；近似路径
禁用 seq scan，并对每个查询、每个 `ef_search` 验证执行计划引用
`items_embedding_hnsw_idx`。查询耗时取 `EXPLAIN ANALYZE` 的服务器
`Execution Time`，不包含 Docker 命令启动。

## 关键结果

| m | ef_construction | ef_search | 构建中位数 | 索引 | Mean Recall@10 | 查询中位数 | 召回重复 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 8 | 16 | 80 | 1.615s | 22.30MiB | 0.3600 | 1.1125ms | 1 |
| 16 | 64 | 80 | 7.763s | 27.18MiB | 0.6867 | 1.6420ms | 4 |
| 16 | 64 | 320 | 7.763s | 27.18MiB | 0.9600 | 3.5730ms | 3 |
| 16 | 128 | 320 | 12.349s | 27.18MiB | 0.9733 | 3.6345ms | 1 |
| 32 | 128 | 80 | 29.293s | 36.54MiB | 0.9200 | 2.7330ms | 4 |
| 32 | 128 | 160 | 29.293s | 36.54MiB | 0.9867 | 3.9790ms | 3 |
| 32 | 128 | 320 | 29.293s | 36.54MiB | 0.9967 | 5.9780ms | 3 |

固定 topology 后，两个关键配置三次扩展曲线的 mean Recall@10 完全一致；查询
时间仍按范围解释。默认构建的 4 次耗时为 `7.678–8.150s`，增强构建的 4 次
为 `28.635–31.879s`。两个配置每次索引大小分别固定为 `28,499,968` 和
`38,313,984` 字节。

容器 `memory.current` 增量在重复间明显波动，尤其强配置约为
`17.88–77.54MiB`，所以本矩阵不把单次或中位增量解释成 HNSW 私有内存；更可靠
的大小证据是固定 topology 后完全一致的索引字节数。内存规模关系另做专项实验。

## 参数建议与验证方式

1. 首先确认 `ef_search >= K`，然后只调整 `ef_search` 并复跑同一 query seed；
   这是不重建索引、风险最小的首选动作。
2. 没有业务目标时从 pgvector 默认构建参数 `m=16, ef_construction=64` 起步，
   不直接照抄本机的 `ef_search=320`。在本轮 50k×64 synthetic workload 和
   `0.95` 目标下，它在 320 达到 `0.96`，这只是一个受控实例。
3. 若提高 `ef_search` 后仍不足，再提高 `ef_construction`。本轮保持 `m=16`
   时，从 64 提高到 128，在 `ef_search=320` 上由 `0.9600` 提高到
   `0.9733`；索引大小不变，但构建中位时间约增加 `59%`。
4. 若需要更高召回并能接受重建、存储和查询代价，再提高 `m`。本轮
   `m=32, ef_construction=128, ef_search=160` 达到 `0.9867`，相对默认构建
   的构建中位时间约为 `3.77×`，索引约大 `34%`。
5. `m=8, ef_construction=16` 虽然构建快、索引小，但在本轮已测上限
   `ef_search=80` 时仍只有 `0.36`。这只能证明它在当前查询预算内不足；应继续
   提高 `ef_search` 并同时测量延迟，若达到业务可接受的查询代价上限后仍不足，
   再重建并重新测量 Recall、构建时间、索引大小和内存。
6. 若构建日志出现 spill，先根据宿主可用内存评估是否提高
   `maintenance_work_mem`，然后用完全相同的数据和参数复验。该建议与 Recall
   调参正交：一个处理构建路径，一个处理检索质量。

## 诊断闭环示例

```text
问题：mean Recall@10 低于本轮显式目标
→ 原因 1：ef_search 小于 K 或候选集过小
→ 动作 1：先提高 ef_search，以相同 query seed 复验
→ 原因 2：提高到可接受的查询代价上限后仍不足，图质量成为候选瓶颈
→ 动作 2：依次评估更高 ef_construction、再评估更高 m
→ 验证：同时比较 Recall、服务器执行时间、构建时间、索引大小和 spill
```

## 方法修正留痕

- `20260903T054320Z-recall-smoke` 最初使用表内向量并排除自身；低
  `ef_search` 时唯一候选可能先被过滤，混入过滤伪影，因此保留但不采用；
- 随后改为独立 synthetic holdout；`recall-holdout-smoke` 和
  `recall-timing-smoke` 分别验证召回路径与服务器侧计时；
- 正式矩阵使用固定 topology 镜像，避免把 HNSW 随机图差异误判成参数效果。

## 可复现性补充与历史限制

- 14 个正式 run 的原始 `summary.json` 固定了参数、0.2 秒采样间隔、宿主
  OS/架构、实际 image ID，以及运行时宿主 checkout 的 OpenTenBase/pgvector
  commit 和 C diff SHA；当前汇总器会拒绝混合采样间隔、宿主、镜像、版本或
  checkout 身份的输入；
- 机器可读汇总记录当前 `summarize_sweep.py` 的 SHA-256；最终小型并行 spill
  端到端烟测 `20260903T112623Z-final-tooling-provenance-spill-smoke-r4` 还记录并
  复核了冻结的 `run.py`、`recall.py`、`dev/compose.yml` 的 SHA-256、Python
  版本、Exact/HNSW 计划和 1MiB safety margin 解释；
- 但 14 个正式 run 生成时还没有“实验工具源码哈希”字段，因此不能追溯证明当时
  两个 Python 文件的逐字节内容。最终烟测只能证明当前工具闭环，不能把该哈希
  反向补记为历史运行证据。
- 正式 source summary 也尚未序列化距离/分布字段；当前聚合结果将其明确标为
  `serialized_in_source_summary=false`，L2/uniform 定义来自该批运行所用的固定
  executor 协议，不伪装成原始 JSON 自带字段。
- `pgvector_source`/`opentenbase_source` 是运行时宿主 checkout 留痕，不是 Docker
  镜像构建源码证明；实际 image ID 固定运行镜像身份，若要做构建源码 attestation，
  仍需在未来镜像中加入 source label 或独立 build manifest。

## 解释边界

- 30 个 synthetic 查询可验证工具和相对方向，不能代替真实业务查询分布；
- 固定 HNSW seed 的镜像只用于受控实验，不是正常交付镜像；
- `0.95` 只属于本轮实验协议，换数据、距离、K、过滤条件或业务代价后必须重定；
- 服务器执行时间只在同一环境横向比较，不代表生产延迟或并发吞吐；
- 每次 run 按递增 `ef_search` 顺序测量，未随机化查询顺序或清空缓存；因此时间
  只作同协议下的方向性证据，不作严格的冷缓存延迟归因；
- 本轮只完成参数诊断，不声称 HNSW 参数在所有数据集上单调或普遍最优。

## 证据

- `experiments/hnsw_build/results/20260903-parameter-sweep.json`：机器可读汇总；
- `experiments/hnsw_build/results/20260903-parameter-sweep.md`：完整矩阵；
- 各 `20260903T*-params-*` 目录：原始 `summary.json`、`recall.csv`、执行计划、
  构建日志与诊断报告；
- `experiments/hnsw_build/recall.py`、`run.py`、`summarize_sweep.py`：实现；
- `test_recall.py`、`test_summarize_sweep.py`：纯本地自动测试。
