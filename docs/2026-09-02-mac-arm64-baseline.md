---
title: OpenTenBase PG18 + pgvector Mac ARM64 环境基线
status: 完成
date: 2026-09-02
tags: [opentenbase, pgvector, hnsw, mac, arm64, reproducibility]
---

# OpenTenBase PG18 + pgvector Mac ARM64 环境基线

## 结论

在 Apple M4 Mac 上，使用原生 `linux/arm64` 容器，已从源码成功编译、
初始化并运行 OpenTenBase `REL_18_STABLE` 与 pgvector `v0.8.6`。最小
HNSW 索引创建和查询验证通过。

本页只记录“开发环境基线通过”这一历史验收点。其后的索引诊断候选已经完成
本地验证，见 [[2026-09-02-local-implementation-evaluation]]。

## 固定版本

| 组件 | 分支 / 标签 | Commit |
|---|---|---|
| OpenTenBase | `REL_18_STABLE` → `codex/hnsw-build-diagnostics` | `4c66f172a09296b08d53526f802ddd2b461bd7e8` |
| pgvector | `v0.8.6` → `codex/hnsw-build-diagnostics` | `8ee86c96f0fd72390f890aa8a336fda6d3ab4c6c` |

## 实测环境

- 宿主：Apple M4，10 核 CPU，24 GB 内存；
- 容器引擎：OrbStack 的 Docker 接口；
- 分配给容器引擎：10 CPU、12,590,047,232 bytes 内存；
- 目标架构：`linux/arm64`，容器内 `uname -m` 为 `aarch64`；
- Compose 共享内存：2 GB；
- 数据库端口：仅绑定 `127.0.0.1:55432`。

数据库报告：

```text
PostgreSQL 18.6 on aarch64-unknown-linux-gnu,
compiled by gcc (Debian 12.2.0-14+deb12u1) 12.2.0, 64-bit
pgvector extension: 0.8.6
```

## 已通过验证

1. OpenTenBase PG18 从源码完成 `configure`、`make` 和 `make install`；
2. pgvector 使用目标 OpenTenBase 的 `pg_config` 完成编译与安装；
3. `initdb` 成功且数据库健康检查通过；
4. `CREATE EXTENSION vector` 成功；
5. 5 条三维向量上成功创建 HNSW L2 索引；
6. `EXPLAIN` 显示 `Index Scan using hnsw_smoke_embedding_idx`；
7. 最近邻查询返回预期顺序 `1, 4, 5`，距离为 `0, 1, 1.4142...`。

验证入口：[[../dev/README|Mac ARM64 开发环境]]、
[[../dev/sql/smoke.sql|HNSW 冒烟 SQL]]。

## 复现

在本目录的父级项目根目录执行：

```bash
docker compose -f dev/compose.yml build
docker compose -f dev/compose.yml up -d
docker compose -f dev/compose.yml exec -T db \
  psql -v ON_ERROR_STOP=1 -U postgres -d postgres < dev/sql/smoke.sql
```

停止容器但保留实验数据：

```bash
docker compose -f dev/compose.yml down
```

## 适用边界

- 适合：编译、单元/回归测试、SQL 功能验证、小到中等规模的受控 HNSW
  构建实验、同一环境内的相对对比；
- 不适合直接声称：裸机 Linux、x86、NVMe 服务器、分布式集群或生产负载的
  绝对性能；
- 后续性能记录必须同时固定数据集、随机种子、向量维度、行数、`m`、
  `ef_construction`、`maintenance_work_mem`、并行 worker 数和冷/暖缓存条件；
- 如需 x86 兼容证据，优先使用 GitHub Actions 做编译和测试，不在本机通过
  QEMU 跑性能结论。

## 下一验收点

该验收点已在 2026-09-02 完成：实验工具可以采集构建耗时、索引大小、容器内存
近似值、阶段与参数；本地补丁细分真实构建阶段并增强已有 spill NOTICE，同时
补齐 TAP、SQL regression 和固定拓扑的前后对照。当前下一关是独立代码 Review
与交付形态确认，不再扩展新功能。
