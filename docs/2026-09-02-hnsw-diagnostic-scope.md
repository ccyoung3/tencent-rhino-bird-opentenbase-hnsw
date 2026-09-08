---
title: HNSW 索引构建诊断范围与首个候选补丁
status: 完成
date: 2026-09-02
tags: [opentenbase, pgvector, hnsw, diagnostics, scope]
---

# HNSW 索引构建诊断范围与首个候选补丁

## 结论

本地实现采用的主功能是：让 `pg_stat_progress_create_index` 区分 HNSW 的
内存构图、刷盘和落盘插入阶段。它比重复已有的建索引百分比或内存超限提示
更符合“索引构建与诊断”，且能在 Mac ARM64 容器中完成开发和验证。

该方案已在独立 pgvector `v0.8.6` 本地分支实现并验证；负责人尚未确认最终
代码归属，因此现在不 push、不建 PR，也不移动到 OpenTenBase 仓库。

## 已有能力，不能作为新贡献

- OpenTenBase PG18 已提供 `pg_stat_progress_create_index`、索引访问方法的
  `ambuildphasename` 映射，以及 heap scan 的 `blocks_total/blocks_done`；
- pgvector 已显示 HNSW 的 `initializing` 和 `loading tuples` 两个阶段；
- 图超出 `maintenance_work_mem` 时已经有 NOTICE、DETAIL 和 HINT；
- `HNSW_MEMORY` 编译宏已经能输出粗略内存值；
- 因此不能把“增加建索引进度”或“发现内存不够”写成项目创新。

## 首选候选：暴露真实构建模式

源码中的真实路径是：

```text
loading tuples in memory
        ↓ 内存预算不足或扫描结束
flushing in-memory graph
        ↓ 若仍有待处理元组
loading tuples on disk
        ↓ 构建完成且关系需要 WAL
writing index pages to WAL
```

当前公开状态始终只是：

```text
initializing → loading tuples
```

实际改动位置：

| 文件 | 作用 |
|---|---|
| `pgvector/src/hnsw.h` | 定义四个 HNSW 构建 subphase，并保存共享原子阶段 |
| `pgvector/src/hnsw.c` | 将 subphase 映射为用户可见名称 |
| `pgvector/src/hnswbuild.c` | 单调推进阶段、协调 worker/leader、增强 spill DETAIL |
| `pgvector/test/t/045_hnsw_low_memory_build.pl` | 断言阶段名称与诊断字段 |

并行构建不能简单让 worker 调普通 `pgstat_progress_update_param()`，因为它只
修改当前 backend 的进度项。本实现让 worker 通过共享原子值单调推进阶段并唤醒
leader，只有 leader 对外发布进度；最终并行 spill 实验确认实际启动 2 个 worker，
阶段没有倒退。

## 可并入的小改进：增强已有 NOTICE

保留现有主要文本，只在 DETAIL 中增加可复现实验所需的上下文：

- graph memory used；
- effective graph memory budget；
- dimensions；
- `m`；
- `ef_construction`。

这应叙述为“给已有告警补充诊断证据”，不是创造新的内存超限检测。

## 第二阶段候选：并行 `tuples_done` 准确性

当前 participant 都会调用只更新自身 backend 的普通进度接口；用户看到的
leader 进度可能依赖 leader 偶尔把共享总数写回，因此可能滞后。先用实验复现，
再考虑 participant 本地批量累计并通过
`pgstat_progress_parallel_incr_param()` 上报；不能每个元组都发消息。

该项涉及正确性、消息开销和并行时序，暂不作为第一刀。

## 验收结果

- [x] 串行、高内存构建可见内存构图阶段；
- [x] 低内存构建可证明进入落盘模式，并输出内存与索引参数；
- [x] 阶段只向前推进，并行 worker 竞争未造成倒退；
- [x] 构建结束后索引可查询，计划使用 HNSW；
- [x] TAP 覆盖全部阶段名称和低内存诊断字段；
- [x] 27 个 HNSW TAP 文件、411 个断言及 4 项 HNSW SQL regression 通过；
- [x] 固定拓扑、各 3 次的 baseline/candidate 对照未见可分辨回归；
- [ ] 独立代码 Review 与负责人交付形态确认。

完整证据见 [[2026-09-02-local-implementation-evaluation]] 和
[[../experiments/hnsw_build/results/README|HNSW 实验证据索引]]。

不改变本页 C 补丁范围的第二阶段实验诊断已补齐 Recall@K、参数矩阵、内存规模
和异常证据，见 [[2026-09-03-hnsw-parameter-diagnostics]]、
[[2026-09-03-hnsw-memory-scale]] 与 [[2026-09-03-hnsw-anomaly-matrix]]。

## 交付前仍需确认的代码归属

`REL_18_STABLE` 当前没有 `contrib/pgvector`；本地验证使用的是外置 pgvector
`v0.8.6`。而 OpenTenBase `master` 内置的是另一份 pgvector。因此在正式改动前
应向负责人确认：

> 我已基于 `REL_18_STABLE` + 外置 pgvector v0.8.6 完成本地 HNSW 构建诊断
> 候选，包括阶段细分、spill 上下文、TAP/回归测试和前后对照。目前
> `REL_18_STABLE` 没有 `contrib/pgvector`。最终交付希望采用哪种形式：提交
> 独立 pgvector 补丁，还是移入 OpenTenBase 的指定目录？另外请确认提交入口与
> 9 月 14 日当天的具体截止时刻。我收到格式后再整理最终代码交付。

## 明确不做

第一阶段不同时扩展 IVFFlat、新量化算法、DiskANN、分布式构建、通用内存预测
模型或自动调参。
