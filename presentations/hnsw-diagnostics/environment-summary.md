# 验证环境摘要

整理日期：2026-09-13。以下取自既有环境记录和实验协议，未把本次电脑状态当作历史测量条件。引用文件的 SHA-256 见 [evidence/manifest.json](evidence/manifest.json)。

## 共同基线

| 项目 | 已记录配置 |
|---|---|
| 宿主 | Apple M4，10 核 CPU，`hw.memsize=25769803776` bytes，即 24 GiB |
| 虚拟化与架构 | OrbStack；原生 Linux ARM64 / aarch64，无 x86 转译性能结果 |
| 数据库 | OpenTenBase 18.6，PG18，`REL_18_STABLE` |
| 扩展 | 外置 pgvector 0.8.6；OpenTenBase 核心源码未改 |
| 上游基线 commit | OpenTenBase `4c66f172a09296b08d53526f802ddd2b461bd7e8`；pgvector `8ee86c96f0fd72390f890aa8a336fda6d3ab4c6c` |
| 使用限制 | 本地非独占宿主，其他项目服务保持原状；无真实业务库验证 |

CPU、核数与精确内存来自 `dev/snapshots/20260911-overhead-acceptance/environment-20260912-review.json`；软件基线来自 `docs/2026-09-02-mac-arm64-baseline.md`。宿主 24 GiB、容器引擎可见内存和单个实例上限是三个不同层级。

## 按验证类型区分

| 类型 | 实际条件 | 对应证据 |
|---|---|---|
| C 功能与兼容性 | Debian ARM64 容器、CentOS Stream 9 原生 ARM64 Machine；使用同一 9/6 C 候选，各完成 28 个 HNSW TAP 文件 / 632 断言与 4 项 SQL 回归 | `docs/2026-09-05-hnsw-build-timing.md`；`dev/snapshots/20260906-build-timing/` |
| 全量 GloVe 内存案例 | Docker 可见 10 CPU、约 11.7 GiB；每次新容器限 6 GiB、无额外 swap；1,183,514 × 100，m=16，ef_construction=64，实际 2 worker；1024MB / 1792MB 各三次独立构建 | `docs/2026-09-09-glove-validation.md`；[内存报告](evidence/glove-memory/report.md) |
| 有限召回新轮 | 新建最终索引 m=16 / ef_construction=128；锁定参数后使用 1000 个新验证查询，同索引比较 ef_search=400 / 1000；每配置 3000 次计时，暖缓存服务器执行耗时 | [新轮报告](evidence/glove-recall/report.md)；逐次原始 JSON 见完整项目目录 |
| 正式新旧开销对照 | 9/11 统一工具链构建的原版 / 候选 seed42 镜像；每实例 2 GiB、无额外 swap；Linux 客体 CPU 0–9；0 / 2 worker、spill / 无 spill，共四场景 × 24 面板 | `docs/2026-09-12-performance-method-review.md`；正式批 `protocol.json` 和 [报告](evidence/performance/report.md) |

正式性能负载为 100,000 / 30,000 行、32 维，m=16、ef_construction=64，按协议区分场景；不与全量 GloVe 的正常随机构建混合。每面板每条件两次正式测量先取几何均值，共 768 次正式构建、384 次预热。每项仍只有 24 个面板统计单位。

9/9 GloVe 预检时宿主磁盘可用约 43 GiB；这是当时的剩余空间，不是磁盘容量或性能指标。未归档独立存储型号、IOPS 或持续吞吐测量，因此不能从阶段耗时推导 SSD 根因或生产容量。

## 候选与镜像身份

正常 GloVe 构建使用 `opentenbase-pg18-pgvector:timing-v1-arm64`，归档 runtime ID 为 `sha256:af1ee2f012f452048c080b591c5456e8a5a83fea77fb4df6e53f4d28ba395fc7`。不要用后来重建或改名的 tag 推断其内容相同。

9/12 正式协议锁定的镜像 ID：

- 原版：`sha256:3db4573bad80e77defd9e89f88f74affd77dc0ee1cd4d80ef670f6d0505b99bd`
- 候选关闭 / 开启 / 观察：`sha256:f8a66172be721f8240a6f21f7cd0cc164ad17d2061bc357518ef25c2227d63be`

候选 tracked patch 的 SHA-256 为 `99da7d1050501be3d8060989511f26c39f0571e0a14c1d09a809c4a1fbf2bcc2`；新增 `049_hnsw_build_timing.pl` 单独归档，SHA-256 为 `c0d0ef1b10abc2d616a5680dfd17ab93a5e44a2630de0b3fd5fff2e523a7a3d9`。这两部分共同构成候选输入，不能只复制 tracked patch 就声称包含全部新增测试。

性能结果仍是 9 项支持低于自设 5% 参考线、3 项尚未证明；以上配置用于解释适用范围，不保证换机后复现相同时间或通过相同门槛。
