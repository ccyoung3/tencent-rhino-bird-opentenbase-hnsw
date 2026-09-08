# HNSW 实验证据索引

本目录保留工具开发、方法校正和最终验证的全部小型结果。最终报告
只采用下面列出的证据；其余带 `smoke`、`formal` 或 `isolated-final` 的目录属于
探索过程，不用于最终性能结论。

## 2026-09-06 内部计时增强

本轮与以下历史基线分开记账。新计时 runtime/test/seed42 镜像、输入 patch 与
新增 TAP 哈希、两种发行版的 632 断言与 4 项 SQL regression 证据见
[[../../../docs/2026-09-05-hnsw-build-timing|内部阶段计时增强留痕]]。
构建/回归日志位于 `dev/logs/20260906-build-timing/`，不放入历史测试汇总。

- `20260905T171633Z-timing-v1-serial-spill-smoke/`：内部计时首次接入的串行 spill 报告；
- 六项成功/超时/旧镜像缺失摘要用例由 `e2e-1.log` 列出唯一原始目录；
- 串行与并行工具中断的原始目录由 `e2e-interrupt.log` 列出；均保留失败摘要，
  清理完成，不进行瓶颈归因；
- `20260905T173636Z-timing-v1-e2e-parallel-spill-nonempty/`：5MB 并行构建先装入
  非空图再触发 spill，验证真实转换和完整时间线；
- `*-timing-overhead/` 及对应 36 个 `*-timing-overhead-w*` run：本轮小规模重复
  开销筛查，和历史 50k×64 性能对照分开，不能混合统计。
- `20260905T173247Z-timing-switch-paired/`：同 backend 交替计时开关的补充协议，
  40 次纳入配对统计、8 次 warmup 保留；此前 +47% 的并行低内存差异未复现，
  但不能据此保证零开销或小于某个门限。

这些目录前缀是 UTC，北京时间已经是 9 月 6 日。新的 `run.py`/`timing.py`
哈希只约束本轮运行，不反向补写历史工具身份。

## Recall@K 与参数矩阵

`20260903-parameter-sweep.json` 和 `20260903-parameter-sweep.md` 汇总固定 HNSW
seed 的 50,000×64 维受控矩阵。查询集为 30 个固定 seed 的独立 synthetic
holdout，K=10；精确路径验证为顺序扫描，近似路径逐查询验证使用 HNSW，并记录
PostgreSQL 服务器侧执行时间。

矩阵覆盖 7 组 `m / ef_construction` 和 `ef_search=10–320`。两个关键配置的扩展
曲线各重复 3 次，mean Recall@10 完全一致：

- `m=16, ef_construction=64`：`ef_search=320` 时 `0.9600`，查询中位数
  `3.573ms`；
- `m=32, ef_construction=128`：`ef_search=160` 时 `0.9867`，查询中位数
  `3.979ms`，但构建中位时间约为前者 `3.77×`、索引约大 `34%`。

本轮显式使用 `0.95` 作为实验目标，不是通用阈值；synthetic 结果只支持诊断
流程和相对权衡。完整解读见
[[../../../docs/2026-09-03-hnsw-parameter-diagnostics|HNSW Recall@K 与参数诊断报告]]。

最早的 `20260903T054320Z-recall-smoke` 使用表内查询并排除自身，会在极低
`ef_search` 时混入过滤伪影，因此只保留为方法修正留痕，不进入参数结论。

## 最终工具冻结烟测

`20260903T112623Z-final-tooling-provenance-spill-smoke-r4/` 使用 10k×8、5MB、
2 个实际 worker 的隔离运行，同时触发 spill 并验证 Exact 顺序扫描、HNSW 路径、
1MiB parallel safety margin 解释和构建后可查询性。其 `summary.json` 记录
Python 3.14.7，以及冻结 `run.py`、`recall.py`、`dev/compose.yml` 的 SHA-256；
三项均已在上一轮冻结时复核；9 月 6 日工具再次增强，不再代表当前源码哈希。
该烟测只证明上一版工具闭环，不进入性能结论，也不
反向补齐 14 个正式参数 run 当时未记录的工具源码哈希。

## 内存与规模关系

`20260903-scale-study.json` 汇总固定 topology 镜像下的三条控制变量：

- 64 维、`m=16` 的行数从 25k 逐级上探到 1M；
- 50k、`m=16` 的维度为 32/64/128；
- 50k×64 的 `m` 为 8/16/32。

10 个独立 scale run 全部通过、无 spill、阶段单调且查询使用 HNSW；正式采用的
10 点统一为 0.2 秒采样间隔。固定配置的 1M 实跑耗时 `247.056s`，测试宏向下
截断记录 HNSW 图内存 `925MiB`，索引大小
`570,105,856` 字节。行数关系在该配置内近似线性，但不跨维度或 `m` 外推。
该 JSON 是人工整理的机器可读派生表，采用字段已逐项与 10 个唯一 raw
`summary.json`（早期三个内存值另回查 stderr）交叉核验。
完整解释见
[[../../../docs/2026-09-03-hnsw-memory-scale|HNSW 内存与规模关系验证]]。

## 异常场景证据

空表/NULL、非法参数、维度边界、重复向量、插入/VACUUM、过滤、WAL 与
串行/并行/落盘召回主要由 pgvector 上游 regression/TAP 覆盖；本项目在
OpenTenBase 18.6 的 Debian 与 CentOS 两条环境线上复验。新增贡献和上游复用
的逐项边界见
[[../../../docs/2026-09-03-hnsw-anomaly-matrix|HNSW 异常场景与测试证据矩阵]]。

## CentOS Stream 9 ARM64 兼容性验收

`20260903T010012Z-centos-stream9-arm64/` 保存冻结候选在 OrbStack CentOS
Stream 9 原生 `aarch64` Machine 中的完整验证证据。结果包括：

- OpenTenBase 18.6 out-of-tree clean build/install 通过；
- pgvector clean build + `-Werror` 通过，0 warning；
- 动态链接检查无缺失库；
- 专项低内存 TAP 5/5、4 项 HNSW SQL regression 4/4；
- 最小 HNSW 建索引/查询通过，执行计划使用 HNSW；
- 全部 HNSW TAP 27 文件、411 断言、0 skip；
- 最终补丁 SHA 与环境切换前冻结值一致，数据库进程已停止。

其中 `verification-summary.json` 是机器可读结果索引，`SHA256SUMS` 覆盖除自身
以外的全部原始证据。该目录只证明 CentOS 发行版与工具链兼容性，不包含正式
性能实验，也不得与下方 Debian Docker 数据横向比较。完整解读见
[[../../../docs/2026-09-03-centos-stream9-arm64-compatibility|CentOS Stream 9 ARM64 兼容性报告]]。

## 普通功能镜像

镜像：`opentenbase-pg18-pgvector:diagnostics-v2-arm64`  
image ID：`sha256:8665e677e3fa7d62a1158698add8d1da173e4c64491643e7d0182ff32adaea91`

| 场景 | 证据 |
|---|---|
| 100k、全内存、快速阶段采样 | `20260902T090002Z-final-functional-memory-fastpoll/summary.json` |
| 10k、1MB、串行 spill 与 NOTICE | `20260902T085906Z-final-functional-low-memory/summary.json` |
| 20k、8MB、2-worker 并行 spill | `20260902T085932Z-final-functional-parallel/summary.json` |

三组均为独立临时数据卷，构建后查询计划均使用 HNSW，观测到的阶段顺序均
单调。合并三组证据可覆盖：内存加载、内存图刷盘、磁盘加载与 WAL 写入。

加入 `diagnostic.md` 输出后的端到端功能证据：

| 场景 | 证据 |
|---|---|
| 10k、1MB、串行 spill | `20260902T133920Z-final-functional-report-low-memory/diagnostic.md` |
| 20k、8MB、2-worker spill | `20260902T133947Z-final-functional-report-parallel/diagnostic.md` |
| 100k、256MB、全内存快速采样 | `20260902T134019Z-final-functional-report-memory-fastpoll/diagnostic.md` |

这些报告直接列出阶段的首次/末次采样时间、sampled span 和 tuple 进度区间，
并对 spill 给出带验证条件的 `maintenance_work_mem` 建议。第三组运行时宿主负载
明显升高，其 110 秒耗时不进入性能对照，只用于验证阶段与报告字段。

并行阶段协调另做了 3 次独立数据卷的重复验证：

- `20260902T131701Z-parallel-stress-r1/summary.json`；
- `20260902T131712Z-parallel-stress-r2/summary.json`；
- `20260902T131724Z-parallel-stress-r3/summary.json`。

三次均实际启动 2 个 worker、触发 spill、保持阶段单调，并在构建后使用 HNSW
查询。WAL 阶段很短，普通轮询不保证每次采到，因此这里验证的是“出现过的阶段
不倒退”，确定性的阶段名称覆盖仍由 TAP 提供。

自动测试的机器可读汇总见 `test-summary.json`。当前最终 test 镜像上重跑全部
HNSW TAP 的结果是 27 个文件、411 个断言全部通过；续作后的实验工具单元测试
28/28 通过。

## 固定 HNSW seed 的性能对照

这组镜像同时使用 pgvector 已有的 `HNSW_MEMORY` 测试宏，使串行 HNSW seed
固定为 42，只用于比较补丁开销：

- baseline：`sha256:0cd8f08b52b2ef9107977d245d5aee06d68c143bdd4d18f86b67faec17dfee76`；
- candidate：`sha256:bac4bb4f7c4b0e183882b6cf653f9ef5af2c046dcd073a25a20f6c97cc76160c`。

最终汇总：

- `seed42-final-comparison-memory.json`；
- `seed42-final-comparison-disk.json`。

两个配置均为 50,000 行、64 维、`m=16`、`ef_construction=64`、串行、每组
3 次、每次全新数据卷。各版本三次生成的索引字节数完全一致，说明图拓扑已被
有效固定。

历史 `summary.json` 中的 `pgvector_source` 读取的是运行实验时的宿主 checkout，
不是镜像构建源码 attestation；baseline 运行时该字段也记录了 candidate checkout，
因此不能用于证明 baseline 源码归属。这里的 baseline/candidate 区分主要依赖上述
不可变 image ID、构建留痕和运行时旧/新 phase 行为。后续若重建交付镜像，应把
build-source commit/diff 写入 image label 或独立 manifest。

## 并行 leader 开销补充对照

`seed42-final-comparison-parallel.json` 使用 50,000×64 维、256MB、2 个 worker，
baseline/candidate 各 3 次交错运行：

- baseline：中位数 `21.957s`，范围 `20.177–27.201s`；
- candidate：中位数 `21.095s`，范围 `18.393–24.834s`；
- 中位数表面变化 `-3.924%`，但范围高度重叠，不能解释为提速。

即使用了测试 seed，并行调度仍使图拓扑与索引大小在各次运行间变化，因此这组
证据只用于排除新增 leader 原子读取造成的明显退化，不用于精确性能归因。

## 为什么保留探索结果

早期实验先后暴露了容器 readiness 竞态、持久数据卷导致的 WAL/存储状态漂移，
以及 SQL `setseed()` 不能控制 pgvector 所用 `pg_global_prng_state` 的事实。
这些结果不作为性能结论，但保留它们可审计实验协议是如何被修正的。
