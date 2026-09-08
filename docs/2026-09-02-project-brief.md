---
title: OpenTenBase HNSW 构建诊断一页说明
status: 完成
date: 2026-09-02
updated: 2026-09-04
tags: [opentenbase, hnsw, diagnostics, brief]
---

# OpenTenBase HNSW 构建诊断一页说明

## 项目状态

本地技术候选已完成，正式交付未开始。固定版本是 OpenTenBase 18.6
`REL_18_STABLE` + 外置 pgvector 0.8.6：Debian ARM64 Docker 承载可重复实验
和同机性能对照，OrbStack CentOS Stream 9 ARM64 Machine 补充构建与回归
兼容性。代码归属、提交入口和精确截止时刻仍待负责人确认。

## 问题

原版 pgvector 对外只显示 `initializing → loading tuples`，但 HNSW 构建实际会
经历内存建图、刷盘、spill 后磁盘插入和 WAL。受控 baseline 中，8MB spill
构建时间约为 256MB 全内存构建的 `3.78×`；只有总耗时时，用户无法判断慢在哪。

## 方案

1. 将 HNSW 进度细分为内存加载、内存图刷盘、磁盘加载、WAL 写入；
2. 用共享原子阶段协调 parallel worker，由 leader 发布数据库进度，阶段只前进；
3. 为既有 spill NOTICE 补充 memory used/limit、dimensions、`m`、
   `ef_construction`；
4. 实验工具自动生成 CSV、JSON 和 `diagnostic.md`，展示阶段 sampled span、
   tuple 进度区间、资源、spill 解释、调参建议与限制；
5. 可选 Recall@K 以独立 holdout、精确顺序扫描和已验证 HNSW 路径形成低召回
   诊断闭环，并记录服务器侧查询时间；
6. 用固定 topology 做参数矩阵和行数/维度/`m` 规模实验，逐级实跑到 1M。

## 验证

| 门槛 | 结果 |
|---|---|
| pgvector clean rebuild + `-Werror` | 通过 |
| 全部 HNSW TAP | 27 文件、411 断言，全部通过 |
| HNSW SQL regression | vector / halfvec / bit / sparsevec，4/4 |
| CentOS Stream 9 ARM64 兼容性 | clean build + `-Werror`、专项 5/5、SQL 4/4、全量 TAP 27/411 且 0 skip |
| 工具单元测试 | 28/28 |
| 串行/并行、全内存/spill | 均构建成功，查询使用 HNSW，观测阶段单调 |
| 固定拓扑串行对照 | 256MB `-0.158%`；8MB `+0.192%`；索引大小相同 |
| 并行补充对照 | 范围高度重叠，未见明显退化；不能声称提速 |
| Recall/参数矩阵 | 14 次通过；关键曲线各重复 3 次；Exact/HNSW 计划均核验 |
| 内存/规模与异常 | 10 次统一 0.2 秒采样的 scale run 全通过，最高 1M×64；异常证据矩阵已完成 |

结论是“没有观察到可分辨的回归”，不是性能提升。Mac 数据不外推到生产服务器。

## 现场演示顺序

1. 展示原版只有 `loading tuples`；
2. 跑 1MB 串行或 8MB 并行场景；
3. 打开生成的 `diagnostic.md`，指出阶段、进度区间和 spill 参数；
4. 展示 Recall 曲线，说明为何先调 `ef_search`、再考虑重建参数；
5. 展示 1M 实跑及行数/维度/`m` 的内存关系；
6. 展示专项 TAP、411 个全量断言和异常证据矩阵；
7. 展示前后对照并主动说明统计、数据和硬件边界。

## 贡献边界

组内图式 ANNS、内存预算和 SSD 研究提供问题意识与实验方法；本次个人贡献是源码
定位、并发设计、C 实现、容器、测试与本地实验。没有复用尚不存在的组内实现，
不声称发明 HNSW、解决分布式构建或取得生产性能提升。涉及李莲鑫师兄或组内图示
的具体启发，汇报时按事实点名致谢。

## 剩余工作

1. AI 只读交叉审查已完成且无 P0/P1；仍需负责人或另一位开发者正式 Review
   4 文件 diff 与实验方法；
2. 确认外置 pgvector 补丁还是 OpenTenBase 指定目录，以及提交入口和时刻；
3. 按目标形态 clean rebuild 后，再由用户决定 commit、push 或 PR。

完整报告：[[2026-09-02-local-implementation-evaluation]]；科研衔接：
[[2026-09-02-research-integration]]；原始证据：
[[../experiments/hnsw_build/results/README|HNSW 实验证据索引]]；CentOS 验收：
[[2026-09-03-centos-stream9-arm64-compatibility]]；续作留痕：
[[2026-09-03-requirements-progress-audit]]；参数诊断：
[[2026-09-03-hnsw-parameter-diagnostics]]；内存规模：
[[2026-09-03-hnsw-memory-scale]]；异常矩阵：
[[2026-09-03-hnsw-anomaly-matrix]]。
