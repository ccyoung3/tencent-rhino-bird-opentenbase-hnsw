---
title: HNSW 构建诊断本地实现与验证报告
status: 完成
date: 2026-09-02
updated: 2026-09-04
tags: [opentenbase, pgvector, hnsw, diagnostics, evaluation]
---

# HNSW 构建诊断本地实现与验证报告

## 结论

本地候选已经形成“代码补丁、诊断工具、自动测试、实验报告”四件套，并在
Apple Silicon Mac 的原生 `linux/arm64` 容器中针对 OpenTenBase 18.6 与
pgvector 0.8.6 完成验证；同一冻结补丁随后又在 OrbStack CentOS Stream 9
原生 `aarch64` Machine 中完成 clean build 与功能回归兼容性验收。当前没有
推送远端、创建 PR 或改变 OpenTenBase 仓库；最终代码归属与提交格式仍等待
负责人确认。

## 被证实的问题

未修改版本把整个 HNSW 构建过程都显示为：

```text
building index: loading tuples
```

但实现实际存在内存建图、刷盘、磁盘逐点插入和 WAL 写入。固定 HNSW seed 的
50,000×64 维实验中，256MB 全内存构建的 baseline 中位数为 `8.307s`，8MB
spill 构建为 `31.444s`，后者约为前者的 `3.78×`。低内存路径在第 `8,645`
个 tuple 后切换，但原有进度视图不能说明慢在哪个阶段，NOTICE 也没有留下维度
和索引参数。

## 本地实现

| 文件 | 改动 |
|---|---|
| `pgvector/src/hnsw.h` | 定义 4 个 HNSW subphase，并在共享图中保存原子阶段 |
| `pgvector/src/hnsw.c` | 将阶段映射为用户可见名称 |
| `pgvector/src/hnswbuild.c` | 单调推进阶段、协调并行 worker/leader、增强 spill DETAIL |
| `pgvector/test/t/045_hnsw_low_memory_build.pl` | 断言阶段名称和新增诊断字段 |

正常路径现在可表达为：

```text
initializing
→ loading tuples in memory
→ flushing in-memory graph
→ writing index pages to WAL
```

发生 spill 时则为：

```text
initializing
→ loading tuples in memory
→ flushing in-memory graph
→ loading tuples on disk
→ writing index pages to WAL
```

刷盘和 WAL 可能短于一次普通轮询，因此单次运行不保证采到每个瞬时阶段；阶段
名称由 TAP 确定性覆盖，快速轮询功能实验合并覆盖了全部四个新增阶段。

### 并行正确性

并行 worker 不能调用普通 `pgstat_progress_update_param()` 期待更新 leader，
因为该接口只写当前 backend。本实现将阶段放入共享 `pg_atomic_uint32`：

1. 阶段只通过 compare-and-swap 向前推进，不允许 worker 竞争导致倒退；
2. worker 改变阶段后唤醒等待中的 leader；
3. 只有 leader 把共享阶段发布到 `pg_stat_progress_create_index`；
4. 串行 callback 不做逐 tuple 原子读取；只有参与扫描的并行 leader 检查共享
   阶段，避免给常见串行路径增加可测开销。

20,000×64 维、8MB、请求 2 个 worker 的最终实验确认实际启动两个 worker，
spill 后索引可查询，观测阶段单调。随后又用全新数据卷重复 3 次并行 spill；
三次均实际启动 2 个 worker、阶段单调且查询使用 HNSW。

### NOTICE 诊断上下文

保留原有 NOTICE 与 HINT，只扩充 DETAIL。最终串行低内存实验示例：

```text
NOTICE:  hnsw graph no longer fits into maintenance_work_mem after 1249 tuples
DETAIL:  Graph memory used: 2097024 bytes; graph memory limit: 1048576 bytes;
         dimensions: 32; m: 16; ef_construction: 64.
         Building will take significantly more time.
HINT:    Increase maintenance_work_mem to speed up builds.
```

这使一次现场日志足以还原内存上限和关键建图参数。

并行路径还会为共享内存分配预留 1MiB safety margin，触发条件实际是
`memoryUsed + 1MiB >= memoryTotal`。因此并行日志中的 used 可能略低于 nominal
limit，并不矛盾；最终 Python 诊断报告会据冻结源码显式解释并计算有效阈值。
当前 C 层 DETAIL 本身尚未打印 margin，若后续允许解冻补丁，可把该字段作为
非阻塞的可解释性增强，并重新跑完整回归。

## 源码自审

当前 4 文件 diff 的 SHA-256 为
`eb09370a414afda75eb7550f21d12f118d1d6f1b32ff0a46ecf1c4ec3bb7e50f`。
本轮自审没有发现阻塞问题，重点核对了：

- 私有图和 DSM 共享图都在 `InitGraph()` 初始化原子阶段；
- compare-and-swap 只允许阶段从小到大，不在 spinlock 内调用进度接口；
- parallel worker 只改变共享状态并发信号，只有 leader 写自己的进度槽；
- leader 在销毁 parallel context 前完成共享图读取，WAL 阶段不解引用已释放 DSM；
- 串行 callback 不做逐 tuple 原子读取；并行 leader 的读取开销另做了补充对照；
- phase 名称、低内存 DETAIL、串行/并行功能和索引可查询性均有自动证据。

这仍属于作者自审，不能替代负责人或另一位开发者的独立 Review；交付前清单保留
该门槛。

## 自动测试

| 验证 | 结果 |
|---|---|
| OpenTenBase PG18 + pgvector 默认功能镜像 clean rebuild | 通过，无编译警告 |
| pgvector clean rebuild + `-Werror` | 通过 |
| 全部 HNSW TAP | `27` 个文件、`411` 个断言；当前最终 test 镜像重跑 `335s`，全部通过 |
| HNSW SQL regression | vector / halfvec / bit / sparsevec，`4/4` 通过 |
| 最终专项 TAP（当前 Dockerfile test 阶段） | `5/5` 通过 |
| 实验工具单元测试 | 续作后 `28/28` 通过 |
| 普通镜像串行全内存 / 串行 spill / 并行 spill | 全部通过且查询计划使用 HNSW |
| CentOS Stream 9 ARM64 兼容性 | clean build + `-Werror`、专项 5/5、SQL 4/4、全量 TAP 27/411 且 0 skip，全部通过 |

测试镜像把 OpenTenBase Perl 测试模块、`IPC::Run` 和非 root `initdb` 用户固化
在独立 stage 中，不进入运行镜像。

## 阶段耗时、进度与诊断报告

`experiments/hnsw_build/run.py` 除原始 CSV 与 JSON 外，现在为每次运行生成
`diagnostic.md`，直接展示：

- 总构建时间、索引大小、容器内存增量与实际 worker 数；
- 每个被采到阶段的首次/末次时间、sampled span、tuple 进度起止百分比；
- spill tuple、内存使用/上限、维度、`m`、`ef_construction`；
- 是否按单调顺序观测阶段，以及查询是否实际使用 HNSW；
- 带验证条件的调参建议和 Mac/采样/容器内存解释边界。

最终带报告的三个端到端场景均使用普通功能镜像和全新数据卷：

| 场景 | 关键报告结果 |
|---|---|
| 10k×32、1MB、串行 | spill；内存阶段采到 0.34%–8.93%，落盘阶段 13.34%–99.69% |
| 20k×64、8MB、2-worker | 实际 2 worker；spill；落盘后采到 WAL，进度到 100% |
| 100k×64、256MB、串行 | 无 spill；采到内存加载、刷盘、WAL，进度到 100% |

对应证据目录分别为：

- `20260902T133920Z-final-functional-report-low-memory`；
- `20260902T133947Z-final-functional-report-parallel`；
- `20260902T134019Z-final-functional-report-memory-fastpoll`。

阶段 span 是轮询样本首尾之间的下界，不是精确埋点耗时；短阶段可能完全漏采。
tuple 百分比只对本工具生成的全非空数据使用 `tuples_done / requested rows`。
最后一组运行时宿主负载明显升高，110 秒只作为功能证据，不替换固定协议的性能
结果。

## 固定拓扑的前后对照

测量条件：Apple M4、OrbStack、`linux/arm64`、50,000 行、64 维、
`m=16`、`ef_construction=64`、串行、每组 3 次、每次独立数据卷、相同 0.1 秒
采样。数据生成由 SQL seed 固定；HNSW 拓扑用 pgvector 已有的
`HNSW_MEMORY` 测试宏固定为 seed 42。该宏只用于 benchmark 镜像，不属于正常
功能交付配置。

| 内存 | baseline 中位数（范围） | candidate 中位数（范围） | 变化 | 索引字节数 |
|---|---:|---:|---:|---:|
| 256MB | 8.307s（8.204–8.482） | 8.294s（8.258–8.338） | -0.158% | 两边均 28,499,968 |
| 8MB | 31.444s（31.150–35.637） | 31.505s（31.080–33.649） | +0.192% | 两边均 28,467,200 |

结论只能写成：在这台 Mac 的受控小样本中，没有观察到可分辨的构建性能或
索引大小回归。`-0.158%` 不是提速结论，`+0.192%` 也不构成显著变慢证据。

最终机器可读汇总见：

- `experiments/hnsw_build/results/seed42-final-comparison-memory.json`；
- `experiments/hnsw_build/results/seed42-final-comparison-disk.json`。

### 并行 leader 开销补充

新增的逐 tuple 原子读取只存在于参与扫描的并行 leader，所以上述串行对照不能
替它背书。补充的 50,000×64 维、256MB、2-worker 对照各运行 3 次：baseline
中位数 `21.957s`（20.177–27.201），candidate 中位数 `21.095s`
（18.393–24.834），表面变化 `-3.924%`。

两边范围高度重叠，且并行调度使图拓扑和索引字节数在重复间变化。因此这里只能
说“没有观察到明显退化”，不能声称并行提速或精确等价。机器可读汇总见
`experiments/hnsw_build/results/seed42-final-comparison-parallel.json`。

自动测试汇总见 `experiments/hnsw_build/results/test-summary.json`。

## CentOS Stream 9 ARM64 补充验收

切换环境前冻结了 binary patch、源码身份、Docker 镜像 ID 和采用中证据文件的
校验和。随后在 Machine home 中按精确 commit 重新获取源码、应用相同补丁并
完成 OpenTenBase 18.6 out-of-tree build/install、pgvector `-Werror`、动态
链接、专项 TAP、4 项 SQL regression、最小 HNSW smoke 和全部 HNSW TAP。

27 个 TAP 文件共 411 个断言全部通过且 0 skip，最终 diff SHA 仍为
`eb09370a414afda75eb7550f21d12f118d1d6f1b32ff0a46ecf1c4ec3bb7e50f`。
这只新增 CentOS Stream 9 ARM64 兼容性证据，不重跑或替代 Docker 性能结果。
详见 [[2026-09-03-centos-stream9-arm64-compatibility]]。

## 9 月 3 日第二阶段诊断补齐

在保持上述 4 文件 C diff 完全不变的前提下，独立实验层继续补齐项目二剩余的
低召回、参数、内存规模和异常证据：

- Recall@K 使用固定 seed 的独立 synthetic holdout；精确路径逐查询验证为
  `Seq Scan`，近似路径验证引用目标 HNSW 索引；
- 50k×64 固定 topology 参数矩阵覆盖 7 组构建参数、`ef_search=10–320`，
  两个关键扩展曲线各重复 3 次，并记录服务器侧查询执行时间；
- 行数/维度/`m` 三条控制变量共 10 个独立 scale run，正式结果统一使用 0.2 秒
  采样，最高实际完成 1M×64；该点构建 `247.056s`、测试埋点图内存
  `925MiB`、无 spill；
- 异常矩阵明确区分上游 regression/TAP 复验与本项目新增证据；
- 工具测试由 7 项扩展到 28 项，全部通过；当前 pgvector diff SHA 仍为
  `eb09370a414afda75eb7550f21d12f118d1d6f1b32ff0a46ecf1c4ec3bb7e50f`。

详见 [[2026-09-03-hnsw-parameter-diagnostics]]、
[[2026-09-03-hnsw-memory-scale]] 和 [[2026-09-03-hnsw-anomaly-matrix]]。

## 实验协议如何被修正

探索阶段出现过两类假信号：复用持久卷导致后半程 spill 从约 31 秒漂移到
36–40 秒；未固定 HNSW 全局 PRNG 时，不同随机图拓扑也放大了波动。最终工具
因此加入每次独立临时 Compose project/volume，并明确区分 SQL 数据 seed 与
HNSW 全局 PRNG。失败和探索结果保留审计，但不进入最终数字。

另一个历史 provenance 限制是：旧 `summary.json` 的源码字段读取运行时宿主
checkout，并不证明所选 Docker image 的构建源码；baseline 记录也因此带有当时
宿主的 candidate diff。固定 image ID 和行为证据仍能区分两组运行，但交付重建
时应增加 image source label 或独立 build manifest，不能引用该宿主字段作镜像
源码 attestation。

## 适用边界与剩余事项

- Debian ARM64 Docker 结果只支持功能正确性和同机相对比较；CentOS Stream 9
  ARM64 结果只增加发行版/工具链兼容性。两者均不代表 x86、裸机 Linux、
  分布式 OpenTenBase 或生产存储；
- `memory.current` 是容器总内存，只能作为近似峰值，不能称为 HNSW 私有内存；
- 并行 `tuples_done` 的精确聚合仍是第二阶段候选，本补丁没有顺手扩大范围；
- `REL_18_STABLE` 没有同版本 `contrib/pgvector`，交付前仍要确认采用外置扩展
  补丁还是移入 OpenTenBase 仓库；
- 当前未提交 commit、未 push、未建 PR，符合“最后再进行代码交付”的约定。

## 叙事闭环

组内向量数据库工作关注向量检索算法、索引与召回；本项目把同一知识延伸到工业
数据库的工程运行面：先从 HNSW 源码还原真实构建状态，再让状态可观测，最后用
可复现实验和回归测试证明改动不破坏索引。这比泛泛地说“研究过向量数据库”更
完整，也能清楚区分科研积累与本次个人工程贡献。具体汇报口径和贡献归属见
[[2026-09-02-research-integration]]。
