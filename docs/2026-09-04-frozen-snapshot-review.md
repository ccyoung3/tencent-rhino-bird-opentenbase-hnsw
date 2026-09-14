---
title: OpenTenBase HNSW 从零 Review 导览与历史审查
status: 进行中
date: 2026-09-04
updated: 2026-09-12
tags: [opentenbase, hnsw, review, evidence, reproducibility]
---

# OpenTenBase HNSW 从零 Review 导览与历史审查

本页是你从零开始检查本项目的入口，不要求先读完 PostgreSQL 或 HNSW 的全部源码。
9/10 真实向量案例的本地开发与验证完成；原五站仍用于理解 9/6 C 候选。
文件名保留原样，避免已有链接失效；前半部分覆盖新候选与新增案例，末尾保留
9 月 4 日的历史审查记录。**旧版“没有发现问题”的结论不覆盖新增计时代码。**

本页是 Review 阅读材料；本轮自动校验与端到端测试不能替代人类代码审查。
下面的核对框全部留空，表示你尚待亲自检查；参考解释不代表你已经独立掌握。

### 9 月 11–12 日：整套诊断开销验收（续验结束，性能未通过）

这次先不增加功能，而是回答“诊断是否会明显拖慢建索引”。
先读[验收报告](2026-09-11-overhead-acceptance.md)，从开头的结论表开始 Review：

1. 对照物是否公平：原版是未修改的 pgvector，不是上一版诊断；两者的数据库、
   编译器、数据和资源限制相同。入口是 [build.py](../dev/overhead/build.py)。
2. 数字是否可信：先让同一版本与自己比较，检查环境波动，再运行原版和三个诊断条件。
   顺序随机且位置平衡，不挑最快一次。看 [acceptance.py](../experiments/hnsw_build/acceptance.py)
   的 `schedule`、`measure`、`summarize`；无需一开始理解全部统计公式。
3. 结论能否复核：[audit_acceptance.py](../experiments/hnsw_build/audit_acceptance.py)
   对照原始日志、真实观察样本和镜像身份；常规编译版另验功能。最新检查点的
   `aa_screens` 保留三个完整但未通过的 A/A，`formal=null` 表示尚未执行正式对照。

当前：98 项工具测试与常规版 20 项检查通过，全部测试实例及临时卷清理。
三个完整A/A分别有3/4、0/4、0/4场景通过；确认窗口后的最后一次接电且负载降低，
仍有明显波动。没有放宽门槛或启动正式原版/诊断对照，不自动再加测。
`checkpoint-after-approved-window.json` 是新增的带失败结果收尾留痕，仍为
`performance_pending`，不是全部通过；两个旧检查点均保留不覆盖。
先Review准入条件与配对设计：8组时p90实为最大值，不能混同于中位成本上界。

- [ ] 我能区分“流程完成”“开销上界低于参考线”和“生产系统绝对零影响”。
- [ ] 我知道本轮比较整套诊断总成本，而不是继续沿用旧版诊断作为基准。
- [ ] 我知道当前没有为了得到好看数字而修改 C、删除异常样本或放宽 5% 线。
- [ ] 我能解释为什么“同一版本与自己比较仍波动”既不是诊断回归证明，也不是低开销证明。

### 9 月 10 日第三轮：默认关闭成本的定位

这一轮不新增产品功能，不修改C候选；检查第二轮中“新版关闭计时为什么慢”的
归因是否充分。先看[定位留痕](2026-09-10-default-off-triage.md)，再看新入口
[triage_overhead.py](../experiments/hnsw_build/triage_overhead.py) 的 `main` 和 `aggregate`。

需要理解的不是复杂统计公式，而是一个公平对比问题：旧版只跑一次正式构建，
新版连续跑三个条件，会不会把“第几次运行”误当成“版本影响”？本轮让两版
预热与正式构建次数相同，再把三个条件的六种顺序全部试一遍。旧数据不删改。

- [ ] 我能说明为什么同一环境内三次构建不是三个独立环境，以及为何按位置匹配。
- [ ] 我能区分“旧协议有混杂”“新对照未复现较大变慢”和“已证明零开销”。
- [ ] 我知道这里的旧版也有诊断改动，不能把本轮数字当作相对原始pgvector的总成本。

本轮于9/11收尾：108次正式+72次预热、全部六种排列和离线复算完成；
新增5项测试、全套83/83，全部临时环境已清理。默认关闭两场景位置匹配中位
差异为+0.49%/+3.29%，但未证明低于5%；没有直接归因到C，不修改候选。
完整实测结论统一看定位留痕，不把流程 `passed` 自动视为性能验收通过。

### 9 月 10 日第二轮：只读观察与有限验证

你授权先推进开发后，本轮增加独立的已有任务观察入口，以及预先限定预算的
召回改进、开销实验。C 补丁与上一轮 GloVe 工具/结果不变；当前进度和结果以
[本轮留痕](2026-09-10-observer-recall-overhead.md) 为准，不混入下面的历史未达标轮次。

新增阅读只需三站：

1. 看[锁等待报告](../experiments/hnsw_build/results/20260910T073830Z-observe-e2e/lock-wait/report.md)，
   再看 [observe.py](../experiments/hnsw_build/observe.py) 的 `SAMPLE_SQL`、`classify`
   与 `observe`。它怎样区分“正在等锁”“采样没变化”“任务已经消失”？为什么
   构建成功与失败结束时，观察器都不能仅凭进度视图确认成功？
2. 看 [bounded_recall.py](../experiments/hnsw_build/bounded_recall.py) 的 `splits`
   与 `main`。为什么用新的验证查询？为什么不能根据验证结果再继续调参？
   调整搜索参数和重建参数，分别产生什么成本？
3. 看 [bounded_overhead.py](../experiments/hnsw_build/bounded_overhead.py) 的
   `measure` 与 `upper_median_bound`。三个比值分别回答什么？为什么内部计时不能
   证明自身成本？为什么“未证明低于5%”不自动等于“确实回归超过5%”？

观察器与测试库操作明确分开：前者不创建/取消对象；[local_stack.py](../experiments/hnsw_build/local_stack.py)
仅供实验新建自己的本地库并清理；[verify_observe.py](../experiments/hnsw_build/verify_observe.py)
由测试管理员故意制造等待、取消等情况，不能拿它连接业务库。
新自动测试目前 78/78，受限账号真实检查 11 项；它们不是人类 Review。

本轮正式实验与复核已完成：新验证查询平均召回95.47%，但有延迟代价；开销
实验出现默认关闭新版相对旧版的变慢信号。**性能验收未关闭**，不能只读到
`passed` 就理解成全部成本达标。下一步优先定位该风险，不再扩展功能。

后续更正：上面的“下一步”已由第三轮承接。第二轮比值存在执行位置/前项操作
混杂，原始结果保留，但不能单独当作新增功能纯成本的因果估计。

- [ ] 我能使用服务配置观察一个明确授权的任务，并说明工具没有写库或读取向量。
- [ ] 我能从召回报告同时讲清收益和查询/重建成本，不声称修改了 HNSW 搜索算法。
- [ ] 我能区分本地开销证据、工程参考线和真实业务服务等级要求。

### 9 月 10 日新增阅读入口：真实向量诊断案例

本节保留首轮 GloVe 的阅读路线与当时结果；其中“本轮”指首轮实验。
最新召回改善与新增观察器看上方第二轮入口，不用新结果覆盖当时的未达标记录。

本轮 C 补丁没有再改，新增集中在实验层。全量六次构建、同索引召回验证和
59 项单元测试已完成，但本人及维护者 Review 尚未完成。

1. 先读 [中文案例结论](2026-09-09-glove-validation.md#先看结论这轮完成了什么)，
   再对照 [两张正式图](../experiments/hnsw_build/results/20260909T135759Z-glove-formal-cases/report.md)。
   构建中位数 23.6→5.4 分钟；验证集召回在 ef=400 时仍只有 89.71%，未达 95%。
   区分“索引构建慢”和“索引建成后召回不足”，不把 spill 当作故障，也不把
   增加 ef_search 当作 C 补丁算法优化。
2. 看 [GloVe 实验入口](../experiments/hnsw_build/glove_run.py)：新建自己的隔离
   实例，加载外部数据，复用原构建采样/计时，调参和验证在同一个索引上进行。
3. 看 [数据与 Recall 校验](../experiments/hnsw_build/glove.py)：二进制 COPY
   保持 float32；原 ID + 1；子集答案重算；全量答案抽查；调参与验证查询不重叠。
4. 看 [重复实验编排](../experiments/hnsw_build/glove_cases.py) 和
   [比较与图表](../experiments/hnsw_build/glove_report.py)：预登记顺序，不混合
   预检/失败/不同协议，不根据验证集继续选参。
5. 看 [新增测试](../experiments/hnsw_build/test_glove.py) 与
   [真实失败清理验证](../experiments/hnsw_build/verify_glove.py)，再按
   [小规模复现步骤](../experiments/hnsw_build/README.md#glove-外部向量案例2026-09-09)
   自己运行 10k；不要先重跑六次全量。

检查自己是否能解释：哪项调整有效、代价是什么、哪项建议没有得到证据支持？
旧 9/6 manifest 继续标识旧工具；本轮修改后的工具使用本轮新哈希，不改写历史。
特别注意 `status=passed` 只是实验完整完成；`selected_ef_search=null` 才说明
本轮没有选出满足目标的配置。工具没有“修好”召回，也没有证明 spill 导致低召回。

- [ ] 我能从低内存原始日志区分 flush 和 disk_insert，解释为什么不能直接断言 SSD 太慢。
- [ ] 我能解释为什么构建提速不是补丁提速，为什么 12,000 条测量不等于 12,000 个独立 query。
- [ ] 我能用未达标的召回结果说明诊断工具如何防止误报成功，而不是保证任意数据都能调到目标。

## 1. 先理解：这个项目到底做了什么

一句话：在 OpenTenBase PG18 上运行 pgvector 的 HNSW 索引，让建索引过程更容易
观察、解释和复验。我们没有重新实现 HNSW，也没有新增一种更快的索引算法。

假设你有一批向量，执行 `CREATE INDEX ... USING hnsw`。上游实现原本就会先在
内存中建图；内存预算不足时，把已有图写成索引页，之后走磁盘索引插入路径。
问题是：原来的进度信息比较笼统，难以知道慢在哪个阶段；仅靠定时查询进度，
又可能漏掉很短的阶段，不能准确得到阶段耗时。

我们分两步解决：先公开更细的阶段和告警上下文，再在实现内部记录时间边界。
Python 工具负责采集、检查、生成报告，并支持调整参数后的复验。

### 1.1 只需先懂这些词

| 词 | 在本项目中的意思 |
|---|---|
| OpenTenBase / PG18 | 数据库宿主；本地选用社区 PG18 分支，实测版本 18.6 |
| pgvector | 装入数据库的向量扩展；本地固定为 v0.8.6，实际产品改动在这里 |
| HNSW | 已有的图式近似向量索引；我们改的是构建可观测性，不是搜索算法 |
| `maintenance_work_mem` | 构建维护操作的内存预算设置，不等于整个数据库的内存上限 |
| spill | 图放不下，构建由内存路径转入磁盘索引路径；不是程序崩溃或宿主机 OOM |
| leader / worker | 发起构建的主进程 / 协助处理数据的并行进程 |
| DSM | 并行进程共用的内存区域；释放以后，指向它的指针不能再读取 |
| WAL | 数据库恢复日志；索引页的末尾 WAL 处理有自己的阶段，不是整条 SQL 的全部日志开销 |
| Recall@K | 近似检索返回的 K 个结果中，有多少与精确检索的 Top-K 重合 |
| TAP / regression | 自动测试：前者组织多步行为断言，后者比较 SQL 的实际与预期输出 |

### 1.2 哪些已有，哪些才是我们的改动

| 上游原本已有 | 本项目增加或改进 | 不能据此宣称 |
|---|---|---|
| HNSW 建图、查询、并行构建和 spill 路径 | 把真实构建模式公开成更细的进度阶段 | 发明 HNSW、实现了原本不存在的 spill |
| `pg_stat_progress_create_index` 进度视图 | 阶段命名、共享阶段协调与 leader 发布 | 从零实现 PostgreSQL 建索引进度系统 |
| 内存不足 NOTICE 与提示 | 补充图内存 used/limit、维度、`m`、`ef_construction` | 新增内存不足检测或内存分配算法 |
| 测试宏可输出粗略图内存 | 建立采样、内部计时、诊断和复验工具 | 测得所有进程的精确私有内存 |
| 大批上游 SQL/TAP 测试 | 扩展 045 测试，新增 049 计时测试并在两种环境复验 | 632 个断言全是个人原创 |

OpenTenBase 源码 checkout 当前没有修改；不是在两个数据库仓库中各改了一套 HNSW。
PG18 分支没有同版本的内置 `contrib/pgvector`，因此先采用外置扩展，最终提交位置
仍待负责人确认。需求背景见 [[2026-09-03-requirements-progress-audit]]。

## 2. 从一开始到现在，改动是怎样累积的

| 阶段 | 为什么做 | 实际产出 | 本轮阅读优先级 |
|---|---|---|---|
| 9/2：搭环境、定位源码 | 不能依赖组内 Linux 服务器，需要 Mac 上可复现的 Linux 环境 | `dev/Dockerfile`、Compose、启动脚本、smoke SQL；固定 OpenTenBase/pgvector 版本 | 先懂用途，不必先重编数据库 |
| 9/2：第一版 C 改动 | 进度只有笼统的 loading tuples，已有告警上下文不足 | 四阶段命名、阶段只前进的并行协调、增强 spill DETAIL；扩展 045 | 必读 |
| 9/2–9/4：实验和诊断工具 | 不能只凭一次运行说功能有效或参数更好 | `run.py`、`compare.py`、`recall.py`、`summarize_sweep.py`；报告、单元测试、参数与规模实验 | 主流程必读，实验细节第二遍读 |
| 9/3：CentOS 兼容线 | 项目推荐环境需要单独验证 | OrbStack CentOS Stream 9 ARM64 构建与回归记录 | 读结论和范围，不与 Docker 性能混算 |
| 9/4：旧版冻结审查 | 排查实验协议、来源与表述问题 | 本页末尾的历史审查；旧 patch/工具归档 | 第一遍可跳过 |
| 9/5–9/6：内部计时增强 | 轮询漏采短阶段，无法可靠给出阶段时间 | 默认关闭的计时开关、一次内部调用的时间线、解析校验、失败清理、049 与端到端测试 | 必读，这是旧报告没有覆盖的新增部分 |
| 9/6：两环境回归与开销复验 | 检查新功能没有破坏已有行为，并评估额外成本 | 632 个 HNSW 断言、SQL 4/4、Python 45/45、端到端 9/9；两种开销协议 | 读证据和限制，不能只看 PASS |
| 9/9–9/10：公开真实向量案例 | 检查诊断方法能否用于非合成向量，能否给出有边界的调整结论 | GloVe 导入/答案校验、全量六次构建、同索引调参/独立验证、两张图；Python 59/59、新端到端 3/3 | 先读本页新增入口；C 未再改 |
| 9/10：已有任务观察与有限验证 | 接入正在构建的任务；继续验证召回代价与计时成本 | 独立只读入口、受限账号测试、有限召回协议、三类配对开销协议；Python 78/78 | 读上方第二轮入口；最新正式状态见留痕 |

实验层还完成了 14 次参数实验、10 个独立规模点，最高实际跑到 1M×64。这些是
较早版本的实验资产，不等于本轮 GloVe 1,183,514×100；不能把旧版性能数字用于新计时补丁。
项目二的需求复核没有发现指定某个“官方数据集”的要求；合成数据用于受控实验，
不包装成真实业务数据。详见需求复核页和 [[2026-09-03-hnsw-memory-scale]]。

## 3. 你的阅读路线：先输出，再实现，最后验证

首轮按下面五站阅读即可。预计 2–3 小时是了解与小规模复现的预算，
**不保证从零精通并发 C 源码**；遇到不懂的锁或生命周期问题先记录，不用硬勾完成。
第一遍不需要读完整个 OpenTenBase、不需要跑 1M，也不需要重跑全部开销实验。

### 第一站：拿一份真实报告读懂问题（约 20 分钟）

打开这份[非空图并行 spill 报告](/Users/ccyoung/Develop/Quant_Job_Prep/OpentenBase/experiments/hnsw_build/results/20260905T173636Z-timing-v1-e2e-parallel-spill-nonempty/diagnostic.md)。
它对应 10,000 行、32 维、5MB 内存设置、2 个实际 worker。

按这个顺序找证据：

1. 参数和实际 worker 数：先确定测的是什么，不能把请求 2 个 worker 当作实际启动 2 个。
2. `Sampled phase timeline`：采样只看到了 initializing 和 disk；这不代表其他阶段没发生。
3. `Internal build timing`：内存路径约 43.145ms、排空等待 0.102ms、刷盘本体 0.574ms、
   落盘插入约 1.163s。内部计时弥补了采样遗漏。
4. `Diagnosis`：第 1296 个 tuple 附近触发 spill；used/limit 是图内存，不是容器总内存。
5. `Recommendation / Revalidation`：有余量时提高构建内存，在同数据和参数下复验。

再看[超时失败报告](/Users/ccyoung/Develop/Quant_Job_Prep/OpentenBase/experiments/hnsw_build/results/20260905T171816Z-timing-v1-e2e-parallel-timeout/diagnostic.md)。
它必须显示 `failed`、`incomplete`，而不是靠部分日志推断“构建完成且磁盘是瓶颈”。

报告中的八段时间可按下表理解。这里的“刷盘”是把图写成索引页，**不等于等待
所有数据通过 fsync 持久化到硬盘**；“磁盘插入”也不等于纯 I/O 等待。

| 内部阶段 | 计时范围的直观解释 |
|---|---|
| `setup` | 本次内部构建的初始化 |
| `memory_build` | 开始建图到首次请求 spill，或没有 spill 时到最后刷图前；也包含扫描、并行启动等时间 |
| `spill_drain` | 请求 spill 后，等待已有内存插入退出、取得刷图所需锁；没有 spill 则不适用 |
| `flush` | 执行已有图到索引页的转换与写入 |
| `disk_insert` | spill 后处理剩余行；包含扫描、插入和等待，不是单独测磁盘设备 |
| `finalize` | 建图结束的收尾，包括并行上下文清理 |
| `wal` | 本次内部构建末尾的索引页 WAL 处理；不需要时不适用 |
| `cleanup` | 本次构建状态的最后资源释放 |

你先试着回答：

- [ ] 为什么采样没看到 flush，但内部计时有 flush？
- [ ] 为什么内部总时间与整个构建命令耗时不一样？
- [ ] 报告能证明哪条路径耗时最多，为什么不能直接证明 SSD 太慢？

### 第二站：按调用关系读 C，而不是从第一行读到最后（约 45–60 分钟）

以下行号核对于 9/6；后续有变动时以函数名为准。产品侧重点只有三个文件：
`hnsw.c`、`hnsw.h`、`hnswbuild.c`。

```text
CREATE INDEX 调用扩展入口 hnswbuild
  → BuildIndex：围住一次内部构建、末尾 WAL、资源释放、输出摘要
      → BuildGraph：选择串行/并行，扫描所有行，收尾刷盘，释放并行上下文
          → BuildCallback → InsertTuple：一行向量如何进入构建路径
              内存够：在图内插入
              内存不够：请求 spill → 排空已有内存插入 → FlushPages → 磁盘插入
          扫描完仍未 spill：FlushPages，然后直接收尾（没有 disk_insert 阶段）
```

这是阅读索引，不是说这些函数都是我们新写的：多数建图函数上游已存在，
我们在关键边界增加状态发布或时间记录。

| 阅读顺序 | 打开位置 | 重点看什么 / 看完应能回答什么 |
|---|---|---|
| 1 | [hnswbuild → BuildIndex](/Users/ccyoung/Develop/Quant_Job_Prep/OpentenBase/pgvector/src/hnswbuild.c:1270) | 从入口找到一次调用的起止；为什么摘要不是整条 SQL/事务提交成功的证明？ |
| 2 | [BuildGraph](/Users/ccyoung/Develop/Quant_Job_Prep/OpentenBase/pgvector/src/hnswbuild.c:1166) | 扫描结束后何时刷盘？无 spill 时为什么没有磁盘插入阶段？ |
| 3 | [InsertTuple](/Users/ccyoung/Develop/Quant_Job_Prep/OpentenBase/pgvector/src/hnswbuild.c:540) | 找到内存检查、第一次 spill 时间、共享/独占锁切换和增强 DETAIL |
| 4 | [FlushPages](/Users/ccyoung/Develop/Quant_Job_Prep/OpentenBase/pgvector/src/hnswbuild.c:352) | 计时从函数本体开始；前面的等锁为什么必须单独列为 spill_drain？ |
| 5 | [ReportBuildPhase / AdvanceBuildPhase](/Users/ccyoung/Develop/Quant_Job_Prep/OpentenBase/pgvector/src/hnswbuild.c:92) | 为什么 worker 不能直接发布 leader 的进度？怎样保证阶段只前进？ |
| 6 | [共享计时结构](/Users/ccyoung/Develop/Quant_Job_Prep/OpentenBase/pgvector/src/hnsw.h:236)、[BuildState 私有副本](/Users/ccyoung/Develop/Quant_Job_Prep/OpentenBase/pgvector/src/hnsw.h:324) | 哪些数据共享、哪些只归 leader？副本为什么要在 DSM 释放前取走？ |
| 7 | [计时偏移与摘要生成](/Users/ccyoung/Develop/Quant_Job_Prep/OpentenBase/pgvector/src/hnswbuild.c:1214) | 所有边界以同一起点换算，如何防止把 worker 时间重复相加？ |
| 8 | [开关与阶段名称](/Users/ccyoung/Develop/Quant_Job_Prep/OpentenBase/pgvector/src/hnsw.c:112)、[阶段编号](/Users/ccyoung/Develop/Quant_Job_Prep/OpentenBase/pgvector/src/hnsw.h:75) | 默认关闭如何定义？四种进度名与八段内部计时为何不矛盾？ |

进一步检查并行生命周期时，再读 [ParallelHeapScan](/Users/ccyoung/Develop/Quant_Job_Prep/OpentenBase/pgvector/src/hnswbuild.c:833)、
[HnswEndParallel](/Users/ccyoung/Develop/Quant_Job_Prep/OpentenBase/pgvector/src/hnswbuild.c:965) 和
[HnswBeginParallel](/Users/ccyoung/Develop/Quant_Job_Prep/OpentenBase/pgvector/src/hnswbuild.c:1002)。
第一遍可以暂不深挖邻居搜索、距离计算、WAL 底层实现和其他索引。

几个必须检查的点：

- [ ] 原子阶段值只能从前一阶段推进，不能被迟到的 worker 写回旧阶段。
- [ ] 首次 spill 请求在已有 allocatorLock 下记录，真正刷盘由唯一执行者记录。
- [ ] leader 等扫描参与者结束后，先复制共享计时，再销毁 DSM；WAL/摘要不访问已释放共享图。
- [ ] 计时采用 wall time（经过了多久），不是各 worker CPU 时间之和。
- [ ] 默认关闭时不输出摘要；这里没有每插入一行都读取一次时钟。
- [ ] 不发生的 disk/WAL 等可选阶段写 null；耗时 0 则可能是微秒量化后的真实短区间。

### 第三站：看 Python 怎样避免错误结论（约 30 分钟）

| 文件 | 先读的函数 | 检查问题 |
|---|---|---|
| [run.py](/Users/ccyoung/Develop/Quant_Job_Prep/OpentenBase/experiments/hnsw_build/run.py:761) | `main` → `create_dataset` → `build_sql` → `execute_build` | 数据、参数、环境和日志怎么连起来？启用计时是否必须收到有效摘要？ |
| [run.py 的观测与报告](/Users/ccyoung/Develop/Quant_Job_Prep/OpentenBase/experiments/hnsw_build/run.py:316) | `read_progress`、`summarize_phase_observations`、`diagnose_build`、`render_diagnostic_report` | 哪些是采样结果？哪些来自 NOTICE？哪些才是内部计时？ |
| [timing.py](/Users/ccyoung/Develop/Quant_Job_Prep/OpentenBase/experiments/hnsw_build/timing.py:30) | `validate_record`、`parse_build_timing`、`render_timing_report` | 重复/损坏/缺失摘要、阶段重叠和命令失败怎样被拒绝？ |
| [取消与清理](/Users/ccyoung/Develop/Quant_Job_Prep/OpentenBase/experiments/hnsw_build/run.py:691) | `execute_build` 的 `finally`、`cleanup_experiment` | 为什么不能只结束 Docker 客户端？怎样限定只取消本次构建，并留下清理结果？ |
| [recall.py](/Users/ccyoung/Develop/Quant_Job_Prep/OpentenBase/experiments/hnsw_build/recall.py:311) | 第二遍再读 `evaluate_recall` | 精确结果与近似结果的查询计划是否逐次验证？`0.95` 为什么不是官方标准？ |
| [compare.py](/Users/ccyoung/Develop/Quant_Job_Prep/OpentenBase/experiments/hnsw_build/compare.py:63)、[summarize_sweep.py](/Users/ccyoung/Develop/Quant_Job_Prep/OpentenBase/experiments/hnsw_build/summarize_sweep.py:59) | `validate_matched`；`load_summaries`、`protocol` | 比较前是否固定工作负载？参数汇总怎样拒绝重复输入与混合协议？ |

先尝试画出你理解的顺序，再回到 `main` 核对：

```text
准备隔离数据库与数据 → 执行构建并留日志 → 核对返回码与计时完整性
  → 验证查询确实使用 HNSW → 可选 Recall 检查 → 清理临时环境 → 保存最终报告
```

- [ ] 我能区别 `summary.status`（本次实验状态）与 `internal_timing.status`（内部计时是否完整）。
- [ ] 即便 C 输出 complete，SQL 后续失败也不能让实验通过。
- [ ] `memory.current` 是容器级近似值；`used/limit` 是图内存；两者不能混用。
- [ ] 计时只帮助定位时间分布，调参建议仍需要控制变量复验。

### 第四站：看测试到底证明了什么（约 20 分钟）

| 入口 | 来源与作用 | 阅读方法 |
|---|---|---|
| [045 低内存测试](/Users/ccyoung/Develop/Quant_Job_Prep/OpentenBase/pgvector/test/t/045_hnsw_low_memory_build.pl) | 上游已有文件，本项目扩展阶段名称与 DETAIL 检查；当前共 5 断言 | 对照 git diff，分清原有断言和新增断言 |
| [049 计时测试](/Users/ccyoung/Develop/Quant_Job_Prep/OpentenBase/pgvector/test/t/049_hnsw_build_timing.pl:25) | 本轮新增文件，共 221 断言 | 先读 `check_timeline`，再看串并行/内存矩阵，最后看取消、恢复、REINDEX |
| [test_timing.py](/Users/ccyoung/Develop/Quant_Job_Prep/OpentenBase/experiments/hnsw_build/test_timing.py) | 工具的坏输入、错误状态、取消和清理测试；属于全部 45 项 Python 测试的一部分 | 挑一个被拒绝的输入，自己解释拒绝原因 |
| [verify_build_timing.py](/Users/ccyoung/Develop/Quant_Job_Prep/OpentenBase/dev/verify_build_timing.py) | 真实启动数据库的 9 个端到端场景 | 特别看 5MB 非空图 spill、旧镜像缺少摘要，以及中断后的清理 |

当前完整 HNSW TAP 是 **28 个文件、632 个断言 = 旧候选 411 + 新计时测试 221**。
Debian 与 CentOS 各执行一次不意味着有 1264 个不同测试。
自动化通过支持已覆盖行为正确，不是“所有并发时序无 bug”的数学证明，也不是维护者签字。

原始证据优先看这些文件的结尾，再按失败或关心的场景向上追：

- [Debian 全量结果](/Users/ccyoung/Develop/Quant_Job_Prep/OpentenBase/dev/logs/20260906-build-timing/tap-canonical.log)；
- [CentOS 全量结果](/Users/ccyoung/Develop/Quant_Job_Prep/OpentenBase/dev/logs/20260906-build-timing/centos/tap-full.log)；
- [Python 最终结果](/Users/ccyoung/Develop/Quant_Job_Prep/OpentenBase/dev/logs/20260906-build-timing/python-tests-final.log)；
- [完整验收表与失败留痕](/Users/ccyoung/Develop/Quant_Job_Prep/OpentenBase/docs/2026-09-05-hnsw-build-timing.md)。

### 第五站：第二遍才读环境、参数与性能（约 20–30 分钟）

环境从 [Dockerfile](/Users/ccyoung/Develop/Quant_Job_Prep/OpentenBase/dev/Dockerfile)、
[compose.yml](/Users/ccyoung/Develop/Quant_Job_Prep/OpentenBase/dev/compose.yml) 看起：前者构建
数据库和扩展，后者规定运行容器、共享内存、端口和数据卷。
`runtime` 是使用环境，`test` 带编译/测试依赖，`seed42` 是专门的实验镜像，不能混称。
CentOS 细节见 [[2026-09-03-centos-stream9-arm64-compatibility]] 与
[本轮脚本](/Users/ccyoung/Develop/Quant_Job_Prep/OpentenBase/dev/centos/verify-timing.sh)：
它使用 Machine 自己磁盘上的源码/构建目录，不在 Mac 共享目录编译。

实验报告按问题选择，不必一次看完所有 raw JSON：

- “参数会怎样影响召回？”读 [[2026-09-03-hnsw-parameter-diagnostics]]。
- “数据变多、维度变大时怎样？”读 [[2026-09-03-hnsw-memory-scale]]。
- “覆盖哪些异常？”读 [[2026-09-03-hnsw-anomaly-matrix]]。
- “新计时有没有开销？”读 [[2026-09-05-hnsw-build-timing]] 中的两张对照表。

新计时做过 36 次独立环境筛查，又做了 40 次同 backend 配对测量（另留 8 次 warmup）。
第一组并行低内存出现约 +47% 的表面差异，在第二种协议未复现；其他组也有噪声。
**当前不能宣称零开销、稳定提速或开销小于 1%。** 这不是缺少计时代码，而是性能
保证仍缺足够证据。Debian 性能与 CentOS 兼容性耗时不能放进同一比较表。

## 4. 怎样在本机做一次最小复现

自动化验收已经执行，但没有替你完成下面的本人 Review。先预测结果，再运行，再解释
输出；不要把照抄命令成功当作独立掌握。预计只需小数据，不必先重建全部数据库。

### 4.1 先读改动和运行纯本地测试

```bash
cd /Users/ccyoung/Develop/Quant_Job_Prep/OpentenBase
git -C pgvector status --short
git -C pgvector diff -- src/hnsw.c src/hnsw.h src/hnswbuild.c test/t/045_hnsw_low_memory_build.pl
python3 -m unittest discover -s experiments/hnsw_build -p 'test_*.py' -v
```

注意：`049_hnsw_build_timing.pl` 目前是新增但未 git add 的文件，**普通 git diff 不显示它**，
需要单独打开上面的链接。9/6 的 45 项和首轮 GloVe 的 59 项是历史数量；本轮
已增加到 98 项，系统 Python 未装可选依赖时预期 92 通过、6 skip。
用 `.venv-glove/bin/python` 执行同一命令应为 98/98，不应 skip。
若不一致，先记录报错，不要修改预期值来凑通过。

### 4.2 再复现一次非空图 spill 和一次高内存构建

先启动 OrbStack，确认没有其他本项目实验正在占用 `127.0.0.1:55432`。
`--isolated` 隔离数据卷，但本地端口仍固定；两条命令必须顺序执行。
先检查本地镜像存在，不要无意使用旧的默认 `dev-arm64`：

```bash
docker image inspect opentenbase-pg18-pgvector:timing-v1-arm64 --format '{{.Id}}'
```

应为 `sha256:af1ee2f012f452048c080b591c5456e8a5a83fea77fb4df6e53f4d28ba395fc7`。
若镜像缺失/身份不同，先停在这里核对来源，不自行覆盖已归档的同名镜像。

```bash
python3 experiments/hnsw_build/run.py \
  --isolated --image opentenbase-pg18-pgvector:timing-v1-arm64 \
  --build-timing --rows 10000 --dimensions 32 --parallel-workers 2 \
  --maintenance-work-mem 5MB --label personal-review-low

python3 experiments/hnsw_build/run.py \
  --isolated --image opentenbase-pg18-pgvector:timing-v1-arm64 \
  --build-timing --rows 10000 --dimensions 32 --parallel-workers 2 \
  --maintenance-work-mem 64MB --label personal-review-high
```

工具会创建并移除本次临时数据库和数据卷，保留新的结果目录，不覆盖历史结果。
读取命令末尾打印目录中的 `diagnostic.md`、`summary.json` 和 `build.stderr.txt`。
预期低内存出现 spill，高内存没有 spill；高内存的 `disk_insert` 应为 N/A。
不要要求第 1296 行、每段耗时或索引字节数与旧并行实验完全一致。

记录四项：实际 worker 数、spill 是否发生、内部时间线是否完整、清理是否 complete。
若要额外练习失败路径，可在同配置加入 `--statement-timeout-ms 100`；预期命令失败且
计时 incomplete，退出码非零在这里是故意测试的结果，不是要“修到成功”。

需要进一步复跑新增 C 测试时，才运行下面这一项（不会重跑全部 HNSW 测试）：

```bash
docker run --rm --shm-size=2g opentenbase-pg18-pgvector:timing-v1-test-arm64 \
  make prove_installcheck PROVE_TESTS=test/t/049_hnsw_build_timing.pl
```

当前预期为 221 个断言通过。该命令验证镜像内的源码与安装库，不会自动包含你以后
在宿主目录的新修改；修改代码后必须重建新的测试镜像，不能拿旧镜像的 PASS 验收新代码。

## 5. Review 到什么程度才算你检查过

先自己回答，再返回代码核对。建议每次只做一站，把问题记在下一节。

- [ ] 不看文档，我能讲清上游本来有什么、我们两轮分别加了什么。
- [ ] 我能找到三个产品源码文件、两个重点 C 行为测试文件和 Python 工具入口。
- [ ] 我能解释 memory → spill drain → flush → disk 的区别，以及无 spill 的分支。
- [ ] 我能解释为什么进度由 leader 发布、为什么共享时间必须在 DSM 销毁前复制。
- [ ] 我能用一份失败报告说明“索引实现内部 complete ≠ SQL 命令成功”。
- [ ] 我亲自跑过小规模低/高内存对照，并能说明结果符合或不符合预测的原因。
- [ ] 我能区分旧版与新版的测试/性能证据，不把旧版 AI 审查当作新版已审查。
- [ ] 我能陈述当前无法支持的结论：零开销、生产性能、分布式能力、通用参数最优值。

这是一轮作者本人理解与复现，不替代维护者对并发正确性、接口习惯和合入标准的审查。
本轮功能已经实现，但默认关闭的性能风险仍需定位，Review 找到真实问题后仍
可能修代码；交付入口与正式提交尚未完成。

组内衔接也要准确：李莲鑫是你的师兄，组内讨论提供图式向量检索与内存预算的问题背景。
本项目目前没有已核实的“把师兄成熟代码直接移植过来”的证据；你应在理解并复现后，
说明自己在 AI 辅助下完成的定位、实现与验证，以及具体启发的归属。

## 6. 你的 Review 记录区（待填写）

不要因为文档或测试已经存在就勾选。没有确定的问题也可以先记“待理解”，不必马上判 bug。

| 日期 / 阅读站点 | 文件或函数 | 我的理解 / 疑问 | 验证方法与结果路径 | 状态 |
|---|---|---|---|---|
| 待填写 | 待填写 | 待填写 | 待填写 | 待开始 |

建议提出问题时用这个格式：

```text
位置：函数名或源码行
我的理解：这段代码应该……
疑问：如果……，是否会……？
证据：实际日志 / 测试 / 我画的调用顺序
下一步：定点阅读或设计哪个最小验证
```

9/6 C 候选与镜像身份见[原 validated-manifest.json](/Users/ccyoung/Develop/Quant_Job_Prep/OpentenBase/dev/snapshots/20260906-build-timing/validated-manifest.json)。
9/10 工具、GloVe 实验证据与反算见[本轮快照](/Users/ccyoung/Develop/Quant_Job_Prep/OpentenBase/dev/snapshots/20260910-glove/README.md)。
旧 manifest 的工具哈希不约束本轮已改的工具；C/TAP 输入仍与旧快照相同。
哈希用于确认“看的是不是同一份东西”，不等于已经证明逻辑正确。

---

## 附录：2026-09-04 旧版冻结审查记录（保留历史）

以下“当前”“最终”均指 9 月 4 日那份旧候选，只覆盖表内的旧哈希。
本附录当时已完成；本页总状态为“进行中”，因为新增导览中的个人 Review 尚待你完成。
以下原结论保留，不追认 9 月 5–6 日的新代码已通过独立 Review。

### 当时结论

对当前 C 补丁、Python 实验工具、参数/规模 raw evidence 和报告口径完成独立的
AI 辅助只读交叉审查。修正审查中暴露的协议与表述问题后，最终快照没有发现
P0、P1、P2 或新增 P3 问题，可以进入负责人/维护者人类 Review 与交付准备。

本页不是维护者签字，也不能替代人类代码 Review；审查过程没有 commit、push、
PR、清理结果或修改冻结 C diff。

### 当时冻结身份

| 对象 | 身份 |
|---|---|
| pgvector 4 文件 binary diff | `eb09370a414afda75eb7550f21d12f118d1d6f1b32ff0a46ecf1c4ec3bb7e50f` |
| 参数汇总器 | `a319275c1463ea42bcdaae23a4df3fb696b36f806510755c0683b91f5fbd5677` |
| 最终 `run.py` | `18d31610af4efc6c652c2453b153b9dd8f63b8ae9e80bbb3f50aa93267cfbcef` |
| 最终 `recall.py` | `8fed0edf184dfb9375f9038f60a5e04ce9e5c9ef167f87d4b10ba920e7e0fb89` |
| `dev/compose.yml` | `e348f673186e72e472aad3abc7f8c7a1950fb92fb5918eb4161367a4aca8304e` |

`git diff --check` 通过，OpenTenBase checkout 保持 clean。C diff 与此前通过
Debian/CentOS 全量回归时完全相同，因此本次只读终检引用已归档的 27/411 TAP、
4/4 SQL regression 和专项 5/5，不把它们冒充 9 月 4 日重新执行。

### 当时代码与工具复核

- C：原子阶段只前进，parallel worker 只更新共享状态并唤醒 leader；leader 在
  DSM 销毁前完成读取，WAL 阶段不再解引用共享图；未发现并发或生命周期阻断项；
- Python：`py_compile` 通过，`unittest discover` 28/28 通过；参数汇总器会拒绝
  重复 source，以及混合采样间隔、宿主/版本、距离/分布、镜像和 checkout 身份；
- r4：`20260903T112623Z-final-tooling-provenance-spill-smoke-r4` 实际启动 2 个
  worker、触发 spill，验证 Exact `Seq Scan` 与目标 HNSW，并正确解释 1MiB
  parallel allocation safety margin；记录的三个工具/Compose 哈希与磁盘一致。

### 当时机器证据反算

#### 参数矩阵

- 从 14 个唯一 raw `summary.json` 重新聚合，与现有
  `20260903-parameter-sweep.json` 逐字段相同；
- 全部为 0.2 秒采样、PASS、Exact 顺序扫描和 HNSW 路径；
- 工作负载明确为 Euclidean L2、`vector_l2_ops`/`<->`，索引数据和独立 holdout
  均为逐维 synthetic uniform `[0,1)`。

#### 规模关系

- 三张表共有 12 个引用、10 个唯一 raw run，全部正式采用点均为 0.2 秒采样；
- 采用字段全部反查一致；早期三个未解析的测试宏内存值另从 stderr 复核；
- 统一补跑后的 300k/500k/1M 分别为 `60.953895s`、`110.278092s`、
  `247.055756s`；1M 图内存为 `969,932,800` 字节（宏向下截断显示 925MiB），
  索引为 `570,105,856` 字节。

### 当时已披露而非隐藏的边界

- 14 个历史参数 run 没有序列化当时 Python 工具哈希，当前 r4 不能反向补记；
- 历史 source 字段描述运行时宿主 checkout，不是 Docker build-source
  attestation；baseline/candidate 主要依赖固定 image ID、构建留痕与行为证据；
- scale 每个点只有一次固定 seed，时间只作趋势，不作显著性或生产吞吐结论；
- scale JSON 是人工整理的机器可读派生表，但采用字段已逐项回查 raw evidence；
- `HNSW_MEMORY` 用整数除法向下截断到整 MiB；容器 `memory.current` 仍只是近似；
- 轮询可能漏掉短阶段，查询计时也没有随机化 ef 顺序或清空缓存。

### 当时列出的下一门槛

1. 负责人或维护者做人类 Review；
2. 确认外置 pgvector 补丁、OpenTenBase 目标目录和提交入口；
3. 按确认后的目标形态 clean rebuild 并复跑专项回归；
4. 用户明确开始交付后再 commit、push 或创建 PR。
