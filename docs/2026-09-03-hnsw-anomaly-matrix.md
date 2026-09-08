---
title: HNSW 异常场景与测试证据矩阵
status: 完成
date: 2026-09-03
updated: 2026-09-04
tags: [opentenbase, pgvector, hnsw, anomaly, tests, evidence]
---

# HNSW 异常场景与测试证据矩阵

## 结论

谢灿扬提出的“异常情况下的测试”不等于必须为每个异常新增代码。复核后确认，
空表、NULL、非法参数、超限维度、重复向量、插入、VACUUM、过滤、WAL 和低召回
等大部分情形已经存在于 pgvector 上游 SQL/TAP；本项目应复用并证明它们在
OpenTenBase 18.6 上通过，同时只把新增的阶段、spill 上下文、Recall 诊断和规模
实跑列为本项目贡献。

## 上游已有、由本项目复验的场景

| 场景 | 上游测试入口 | 验证内容 | OpenTenBase 证据 |
|---|---|---|---|
| NULL 与空结果 | `test/sql/hnsw_vector.sql` | NULL 行不进入距离排序；NULL query；TRUNCATE 后空查询 | HNSW SQL regression 4/4 |
| 非法构建参数 | 同上 `options` | `m=1/101`、`ef_construction=3/1001`、`ef_construction < 2m` 拒绝 | HNSW SQL regression 4/4 |
| 非法查询参数 | 同上 | `hnsw.ef_search=0/1001`、iterative/max tuples/memory multiplier 越界 | HNSW SQL regression 4/4 |
| 维度边界 | 同上 `dimensions` | vector(2000) 可建；vector(2001) HNSW 拒绝 | HNSW SQL regression 4/4 |
| 重复向量 | `015/023/027/031_*duplicates.pl` | vector/bit/halfvec/sparsevec 重复值与 TRUNCATE | 全量 HNSW TAP 27/411 |
| 插入后召回 | `013/021/025/029_*insert_recall.pl` | 建索引后增量写入与召回 | 全量 HNSW TAP 27/411 |
| VACUUM 与再插入 | `011_hnsw_vacuum.pl`、`014/022/026/030_*vacuum_recall.pl`、`038/047_*vacuum_insert.pl`、`046_hnsw_vacuum_scan.pl` | 删除、VACUUM、扫描和再插入 | 全量 HNSW TAP 27/411 |
| 过滤与 iterative scan | `017_hnsw_filtering.pl`、`043/044_hnsw_iterative_scan*.pl` | 过滤后结果不足、严格/宽松顺序与召回复验 | 全量 HNSW TAP 27/411 |
| WAL/恢复 | `010_hnsw_wal.pl` | HNSW WAL 路径 | 全量 HNSW TAP 27/411 |
| 串行/并行/落盘召回 | `012/020/024/028_*build_recall.pl` | 串行、并行内存、并行 spill 后召回 | 全量 HNSW TAP 27/411 |

同一冻结补丁在两条环境线均通过：

- Debian ARM64 Docker：HNSW SQL regression 4/4、全量 TAP 27 文件/411 断言；
- CentOS Stream 9 ARM64：SQL 4/4、TAP 27/411、0 skip，原始
  `sql-regression.log` 与 `tap-hnsw-full.log` 已归档。

## 本项目新增或专项形成的证据

| 场景 | 预期诊断 | 结果与证据 |
|---|---|---|
| 极低内存、并行、首 tuple 前 spill | 阶段不倒退；NOTICE 带 used/limit/维度/m/ef | 新增 `045_hnsw_low_memory_build.pl`，5/5，通过两套环境 |
| 1MB 串行 spill | 明确进入磁盘加载阶段，输出原因和调整方式 | `20260902T133920Z-final-functional-report-low-memory`，通过 |
| 8MB、2-worker spill | 实际启动 worker，阶段单调，索引可查 | `20260902T133947Z-final-functional-report-parallel`，通过 |
| 低 `ef_search` | Exact/HNSW 计划分离；Recall@K 触发本轮风险 | 50k×64 参数矩阵；弱配置及低 `ef_search` 可稳定复现 |
| 已测查询预算内仍不足 | 继续提高 ef_search 并权衡延迟；到可接受代价上限后再判断图质量 | `m=8/efc=16` 到 ef=80 仍为 0.36；增强配置可改善，但不能据此断言弱配置必须立即重建 |
| 接近内存预算的大规模构建 | 不主动制造宿主 OOM；记录是否 spill、峰值、阶段和可查询性 | 1M×64、1GB，925MiB 图内存，无 spill，构建后 HNSW 查询通过 |
| 工具非法组合 | 不运行含糊或不可解释实验 | `ef_search`/threshold 未启用 recall、rows<K 等由参数校验拒绝 |

## 贡献归属边界

- 上游 `hnsw_vector.sql` 和原有 26 个 HNSW TAP 文件是复验证据，不是本项目新写；
- 本项目修改的是第 27 个专项 TAP 中的阶段与 DETAIL 断言，以及独立实验工具；
- 全量 27/411 的价值是证明新增 C 代码没有破坏既有异常和生命周期路径，不能
  表述为“个人新增 411 个测试”；
- synthetic 参数矩阵与 1M 实跑是本项目新产生的 OpenTenBase 集成证据，但不是
  公开数据集排名或生产压力测试。
- 并行 spill 为共享内存分配预留 1MiB safety margin，因此 used 可以低于 nominal
  limit；最终工具会解释有效触发阈值，但冻结 C 层 DETAIL 尚未单列该 margin。

## 验收判断

异常场景条目现已满足：有确定性输入、明确预期、两套 Linux 环境的自动回归结果，
并有项目新增的低内存、低召回和规模边界证据。后续若 C 补丁再变化，必须重跑
27/411 和 4/4；当前仅实验工具变化，冻结 C diff 哈希未变。

## 证据入口

- `experiments/hnsw_build/results/test-summary.json`；
- `experiments/hnsw_build/results/20260903T010012Z-centos-stream9-arm64/verification-summary.json`；
- `experiments/hnsw_build/results/20260903T010012Z-centos-stream9-arm64/sql-regression.log`；
- `experiments/hnsw_build/results/20260903T010012Z-centos-stream9-arm64/tap-hnsw-full.log`；
- [[2026-09-03-hnsw-parameter-diagnostics|Recall@K 与参数诊断报告]]；
- [[2026-09-03-hnsw-memory-scale|内存与规模关系验证]]。
