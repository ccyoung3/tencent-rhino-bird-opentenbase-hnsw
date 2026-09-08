---
title: OpenTenBase HNSW CentOS Stream 9 ARM64 兼容性报告
status: 完成
date: 2026-09-03
tags: [opentenbase, pgvector, hnsw, centos, compatibility]
---

# OpenTenBase HNSW CentOS Stream 9 ARM64 兼容性报告

## 结论

冻结的 OpenTenBase 18.6 + pgvector 0.8.6 HNSW 构建诊断候选，已在
Apple Silicon Mac 的 OrbStack CentOS Stream 9 原生 `aarch64` Machine 中
完成独立源码获取、补丁还原、clean build、安装、动态链接、专项 TAP、SQL
regression、最小 HNSW 建索引/查询和全部 HNSW TAP 验证。

所有产品验收项均通过：专项 TAP `5/5`、4 项 SQL regression `4/4`、全部
HNSW TAP 为 27 个文件、411 个断言、0 skip。最终 diff SHA 与切换环境前冻结值
一致，没有残留数据库进程。

这条结果新增的是 CentOS Stream 9 ARM64 发行版和工具链兼容性证据，不替换、
重跑或混用 Debian Docker 的性能结果。

## 冻结输入

| 项目 | 固定值 |
|---|---|
| OpenTenBase commit | `4c66f172a09296b08d53526f802ddd2b461bd7e8` |
| OpenTenBase version | `18.6` |
| pgvector base commit | `8ee86c96f0fd72390f890aa8a336fda6d3ab4c6c` |
| pgvector version | `0.8.6` |
| candidate patch SHA-256 | `eb09370a414afda75eb7550f21d12f118d1d6f1b32ff0a46ecf1c4ec3bb7e50f` |

切换环境前保存了实际 binary patch、源码身份、4 个 Docker 镜像 ID，以及 141
个采用中的工具、文档与结果文件校验和：

- `experiments/hnsw_build/results/20260902T163630Z-pre-centos-freeze/`。

该清单在切换环境前已整体校验通过；补丁既通过反向应用检查，也在 CentOS 新
checkout 中通过正向 `git apply --check`。兼容性验收完成后，根 README、开发
说明、交付计划、本地评估、一页说明和结果索引共 6 个叙事文件按计划回填，因此
它们不再匹配“pre-CentOS”时刻的旧哈希；其余 135 个代码、工具与既有结果条目
仍匹配。该历史清单不应被改写成验收后的状态。

## 实测环境

| 项目 | 实测值 |
|---|---|
| OrbStack | `2.0.5`，Machine ID `01M1HG5W31JQMWEGD54FAFQJDQ` |
| Machine | `opentenbase-centos` |
| 发行版 | CentOS Stream 9 |
| 架构 | `aarch64`，64-bit |
| Kernel | `6.17.8-orbstack-00308-g8f9c941121b1` |
| CPU | OrbStack 全局上限 10，Machine 内 `nproc=10` |
| 内存 | OrbStack 全局上限 12288 MiB，Machine 内约 11 GiB 可见 |
| 根文件系统 | 约 58 GiB，验证前约 50 GiB 可用 |
| `/dev/shm` | 约 5.9 GiB |
| 编译器 | GCC 11.5.0，`aarch64-redhat-linux-gnu` |
| Perl TAP | Perl 5.32.1，TAP::Harness 3.42，IPC::Run 20200505.0 |

OrbStack 2.0.5 不支持在 `orb create` 中指定逐 Machine 的 CPU、内存和磁盘参数，
因此本次明确记录实际全局上限与 Machine 可见资源。兼容性验收不使用这些资源
生成或比较性能数字。

## 构建方法

Machine 固定为 `centos:9-Stream` 和 `arm64`。源码没有从 Mac 工作树直接复制，
而是在 Machine home 中分别按精确 commit 做 depth-1 fetch，再应用冻结补丁；
构建和安装均不位于 `/mnt/mac`。

CentOS Stream 9 启用了 CRB，以安装 `perl-IPC-Run`。OpenTenBase 使用独立构建
目录和下列关键配置：

```text
--without-icu
--with-openssl
--with-libxml
--enable-tap-tests
```

`--enable-tap-tests` 在 configure 阶段验证了 Perl 模块，并在 `make install` 时
把 `PostgreSQL::Test::*` 安装到 PGXS。pgvector clean build 通过环境变量附加
`PG_CFLAGS=-Werror`，同时保留 Makefile 的 `-march=native` 与向量化参数。

完整复现步骤见 [[../dev/centos/README|CentOS Stream 9 ARM64 兼容性复现]]。

## 验收结果

| 验收项 | 结果 | 证据 |
|---|---|---|
| OpenTenBase configure + TAP 依赖检查 | PASS | `opentenbase-configure.log` |
| OpenTenBase clean build/install | PASS | `opentenbase-build.log`、`opentenbase-install.log` |
| PGXS TAP 模块安装 | PASS | `opentenbase-install-verification.log` |
| pgvector clean build + `-Werror` | PASS；0 warning | `pgvector-build-werror.log` |
| `postgres` / `vector.so` 动态链接 | PASS；0 `not found` | `ldd.log` |
| 专项低内存 TAP | PASS；1 文件、5 断言 | `tap-low-memory.log` |
| 最小 HNSW smoke | PASS；扩展 0.8.6，计划使用 HNSW | `smoke.log` |
| HNSW SQL regression | PASS；4/4 | `sql-regression.log` |
| 全部 HNSW TAP | PASS；27 文件、411 断言、0 skip、98s | `tap-hnsw-full.log` |
| 最终源码与进程完整性 | PASS；SHA 不变、无残留 postgres | `final-integrity.log` |

原始证据和机器可读汇总位于：

- `experiments/hnsw_build/results/20260903T010012Z-centos-stream9-arm64/`；
- `verification-summary.json` 是机器可读索引；
- `SHA256SUMS` 覆盖该目录中除自身外的全部证据文件，并已验证通过。

## 执行中暴露的问题

保留了两个非产品问题，没有把它们隐藏为“从未失败”：

1. 第一次创建 Machine 时，rootfs 下载发生一次 `unexpected EOF`。确认没有残留
   Machine、OrbStack doctor 正常、固定镜像目录与 URL 有效后，对相同固定镜像
   重试成功；没有改用其他发行版或版本。
2. 第一次启动 SQL 验证实例时，嵌套 shell 引号导致 `pg_ctl -k` 丢失参数。
   实例从未启动；改为显式 `unix_socket_directories` 和固定端口后，smoke 与
   regression 全部通过。失败日志与成功重试日志均保留。

两者都发生在 OpenTenBase/pgvector 运行之前或启动参数解析处，不是候选代码、
CentOS ABI 或数据库功能兼容性失败。

## 适用边界

本次可以表述为：

> 已验证 HNSW 构建诊断候选在 CentOS Stream 9 ARM64 环境中的源码构建、动态
> 链接与功能回归兼容性。

不能扩张为：

- 已验证 x86_64；
- 已验证裸机或生产服务器性能；
- 已验证分布式 OpenTenBase；
- CentOS 与 Debian 的耗时可以横向比较。

项目启动会议明确本题不要求分布式场景，因此“未覆盖分布式”符合当前任务范围，
不是本地候选的未完成项。若负责人后续明确要求服务器 x86_64，再补一次 amd64
正确性回归，不把 Rosetta 环境数据纳入性能结论。

## 当前状态

CentOS 兼容性补充验证已经完成。项目仍记为“进行中、待独立代码 Review 与正式
交付”，因为本轮没有改变代码归属、创建 commit、push 或 PR，也不能把作者侧
环境验证误记成独立 Review 通过。
