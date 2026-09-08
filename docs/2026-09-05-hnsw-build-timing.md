---
title: HNSW 内部构建阶段计时增强
status: 进行中
date: 2026-09-05
tags: [opentenbase, hnsw, timing, implementation]
---

# HNSW 内部构建阶段计时增强

用户通过 Side 明确批准的新一轮增强：可靠阶段计时、诊断报告接入和真实行为测试。
上一版在 9 月 4 日完成并冻结，本轮属于新增贡献，不是补写原需求的遗漏验收。

## 2026-09-06 续作进度

状态：实现与功能验证完成；两种开销对照已执行，精确开销结论仍证据不足；
作者侧核对完成，人类/独立 Review 待完成。项目继续标记“进行中”，不假报正式验收。
没有修改 OpenTenBase 核心，没有远端提交。以下测试属于新候选，不借用旧版本结果。

| 验收 | 本轮结果 | 原始证据（项目根目录相对路径） |
|---|---|---|
| 新计时专项 | 1 文件 / 221 断言，通过 | `dev/logs/20260906-build-timing/tap-prototype-2.log` |
| Debian HNSW 全量，严格编译原型 | 28 文件 / 632 断言，通过 | 同目录 `tap-full-1.log` |
| Debian 正常优化参数、可重建 test 镜像全量 | 28 文件 / 632 断言，通过 | 同目录 `tap-canonical.log` |
| Debian SQL regression | 4/4，通过 | 同目录 `sql-regression-1.log` |
| Python 单元测试 | 45/45，通过 | 同目录 `python-tests-2.log` |
| 工具端到端 | 6/6，含两个预期超时与旧镜像摘要缺失 | 同目录 `e2e-1.log` |
| 非空图并行 spill 转换 | 1/1，先内存插入后 spill，摘要连续 | 同目录 `e2e-nonempty-spill.log` |
| 实际中断工具 | 2/2，串行/并行 spill 后取消与清理 | 同目录 `e2e-interrupt.log` |
| CentOS clean build + pgvector -Werror | 通过，0 编译 warning，链接无缺失 | 同目录 `centos/` 构建及链接日志 |
| CentOS 专项 / 全量 / SQL / 最小查询 | 226 / 632 断言、4/4 SQL、HNSW 查询，通过 | 同目录 `centos/tap-targeted.log`、`tap-full.log`、`sql-regression.log`、`smoke.log` |

221 个新增断言验证了默认关闭、四种串并行/内存路径、连续且不重叠的时间线、
真实 worker 数、unlogged 主/init fork 与 WAL N/A、实际取消/异常、同一连接恢复、
重复 REINDEX 与开关生命周期。它们不依赖轮询恰好捕获极短的 flush/WAL 阶段。
632 = 原有 411 + 本轮新增 221，不能把全部上游断言表述成个人新增测试。

工具实际中断后保留错误和日志；缺少完整摘要时不输出瓶颈判断，失败命令不能因
存在内部摘要而判为成功。每次隔离环境的清理结果写入 `summary.json.cleanup`。
主干示例报告可见
[[../experiments/hnsw_build/results/20260905T171633Z-timing-v1-serial-spill-smoke/diagnostic]]；
其余具体运行目录由端到端日志逐项列出。目录使用 UTC 时间，9 月 5 日 17 点对应
北京时间 9 月 6 日凌晨，并非日期写错。

### 新候选身份

- tracked patch：`dev/snapshots/20260906-build-timing/pgvector.patch`；
  SHA-256 `99da7d1050501be3d8060989511f26c39f0571e0a14c1d09a809c4a1fbf2bcc2`。
- 新增 TAP 尚未 git add，不在 `git diff HEAD` 内；同目录单独保存
  `049_hnsw_build_timing.pl`，SHA-256
  `c0d0ef1b10abc2d616a5680dfd17ab93a5e44a2630de0b3fd5fff2e523a7a3d9`。
  重建必须同时使用 patch 和新增 TAP，不可仅凭 tracked diff 称完整冻结。
- 正常 runtime `timing-v1-arm64`：
  `sha256:af1ee2f012f452048c080b591c5456e8a5a83fea77fb4df6e53f4d28ba395fc7`。
- 正常 test `timing-v1-test-arm64`：
  `sha256:583632f8a2ba73f694ffed52fcd8e9a9a385da94c2602bfd65de1086a92148c6`。
- benchmark `timing-v1-seed42-arm64`：
  `sha256:a8b091b6ff87fb8c35037cabd00fb4cd5b0a111ced58371310cc620a05e4b969`。
- 正常 test/runtime 的 `vector.so` 实测 SHA 一致：
  `679afd5c0ae367873e43e549ded9ba7f951eb88a97f56add2c3cc223a87d7656`；
  test 镜像源码哈希在 `tap-canonical.log` 开头，与宿主及 CentOS 输入一致。
- CentOS 使用全新的 `/home/ccyoung/opentenbase-timing-20260906/` 源码、构建、
  安装及数据库目录；只读取旧的干净 OpenTenBase 源码，不覆盖旧候选安装。
  复现脚本：`dev/centos/verify-timing.sh`。验收结束无 postgres 残留进程。

### 暴露的问题与修正

首次新增 TAP 失败保留于 `tap-prototype-1.log`：临时测试集群默认允许省略新建
索引 WAL，而测试错误假定一定写 WAL；DEBUG1 同时把测试环境的 statement LOG
送到客户端，触发 background_psql 的严格错误判断。修正为明确设置 replica WAL
模式和 NOTICE 客户端日志，并保留 unlogged 主 fork 的 WAL N/A 验证。没有为了
满足测试而改变数据库的 WAL 决策。

### 下一验收

`dev/benchmark_build_timing.py` 已完成 20k×32、三种版本/开关、四种串并行与
低/高内存场景、每组 3 次的 36-run 轻量筛查；每次 fresh volume、0.2s 采样，
三个版本按轮次轮换顺序。全部构建、计时完整性和清理检查通过，但开销结论暂不通过。
原始汇总为
[[../experiments/hnsw_build/results/20260905T172429Z-timing-overhead/summary.json]]，
36 个唯一 run 均已回查原始 JSON，运行时 `run.py` 哈希一致。

| 场景 | 上一版关闭 | 新版关闭 | 新版开启 |
|---|---:|---:|---:|
| 串行，高内存 | 2.489 [2.358–5.662] | 2.358 [2.338–4.468] | 2.376 [2.367–4.701] |
| 串行，低内存 | 7.678 [7.665–13.856] | 8.493 [8.180–9.850] | 8.274 [7.713–20.907] |
| 2-worker，高内存 | 0.972 [0.967–1.683] | 1.092 [0.972–2.199] | 1.014 [0.904–1.256] |
| 2-worker，低内存 | 4.629 [3.973–11.538] | 4.216 [3.446–4.272] | 6.197 [3.435–8.619] |

单位为秒，中位数 [最小–最大]，每格 n=3。低内存为串行 1MB/并行 4MB，高内存
128MB。并行低内存的新候选 on/off 中位数差约 +47%，不能把范围重叠等同于
“无回归”；其他场景与个别重复也有较大波动。当前数据不能定量归因于计时逻辑，
不能表述为零开销或百分之几的提速。所有离群点原样保留，不删除后重算。

已补充 `dev/benchmark_timing_switch.py`：每个场景在同一 backend 与同一数据上
交替 on/off，保留一对 warmup，另测 5 对；使用 psql 对 CREATE INDEX 的计时，
不轮询、不为每次构建重启实例。补充已完成：40 次纳入统计，8 次 warmup 单独保留，
全部命令与计时完整性通过，临时环境清理完成。不同协议单独保存，不合并上表。
原始 SQL、stdout/stderr 和逐次数据见
[[../experiments/hnsw_build/results/20260905T173247Z-timing-switch-paired/summary.json]]。

| 场景 | off 中位数（ms） | on 中位数（ms） | 每对 on/off 变化的中位数 |
|---|---:|---:|---:|
| 串行，高内存 | 2611.138 | 2463.580 | −4.474% |
| 串行，低内存 | 8426.148 | 8693.757 | +6.395% |
| 2-worker，高内存 | 1227.163 | 1313.104 | +1.972% |
| 2-worker，低内存 | 4133.074 | 4023.124 | −3.172% |

每场景 5 对、开关顺序交替。最后一列是逐对比值的中位数，不是前两列中位数之比。
此前并行低内存约 +47% 的表面差异没有在该协议复现，但这不等于证明没有开销；
串行低内存和并行高内存仍有正向变化与噪声。当前既不能宣称计时造成了稳定提速，
也不能给出“开销小于 1%”或“零开销”的保证。若负责人要求这样的门限，需在
更稳定的机器空闲窗口预先确定重复次数和判定标准，再做专项量化，不继续凭
当前波动数据无限追加试验。

诊断链条本身已得到复验：开启计时的低内存组 `disk_insert` 占内部时间
98.2%–99.4%，提高到 128MB 后所有对应构建均无 spill、disk_insert 为 N/A，
主要区间转为 memory_build；这支持“定位构建路径并验证内存建议”的功能，
不证明磁盘设备 I/O 是唯一因果瓶颈。正式 Recall 参数矩阵与 1M 规模线不重跑。

### 本轮收口与留痕

- 保留原冻结版；新候选只做本地开发，不发起 commit/push/PR。
- `dev/snapshots/20260906-build-timing/input-manifest.json` 是补充非空 spill 用例前
  的中间输入快照；最终源码/工具/测试与证据身份以同目录 `validated-manifest.json`
  为准。旧清单不改写历史；C 与 TAP 内容在两份清单之间没有变化。
- 最终工具归档为同目录 `validated-tooling.tar.gz`；已有全部参数/规模历史数据保留。
- 两种发行版验证、221 个新增 TAP 断言、45 项工具单元测试、9 个端到端用例
  构成功能证据；机器执行不算作用户独立完成或个人学习时长。
- 下一步是独立代码 Review 和用户自行复现/理解计时边界；精确开销量化与交付
  入口仍需明确标准/负责人意见，不自动扩展算法、数据集或分布式工作。

## 基线与范围

- 旧 pgvector patch：`dev/snapshots/20260905-before-build-timing/pgvector.patch`，
  SHA-256 `eb09370a414afda75eb7550f21d12f118d1d6f1b32ff0a46ecf1c4ec3bb7e50f`；
- 旧工具/文档归档：同目录 `tools-and-docs.tar.gz`，SHA-256
  `d8fb1512fa26c1df45bc67427fd610e03bd51e1f1927f74b25a62b5cc6752c19`；
- pgvector base `8ee86c96f0fd72390f890aa8a336fda6d3ab4c6c`，OpenTenBase base
  `4c66f172a09296b08d53526f802ddd2b461bd7e8`；旧结果目录与镜像保持可用；
- 仅扩展 HNSW 可选计时，不涉及数据库核心接口、算法加速、并行 tuple 聚合、
  自动调参或其他索引；默认关闭，仅成功返回时输出一条可解析摘要；
- 不 commit/push/PR，不联系负责人；旧 TAP/性能结果不作为新代码通过证据。

## 时间口径与最小原型

使用 PostgreSQL `instr_time` 的单调时钟（本轮 Linux）。以一次 HNSW BuildIndex
内部调用为单位记录边界；不是 worker CPU 累计，也不是完整 CREATE INDEX 命令
或事务提交时间。主 fork 和 unlogged init fork 分别标识，不混成一条记录。

划分为 setup、内存构建、spill 排空等待、FlushPages 本体、spill 后落盘插入、
并行收尾、末尾 WAL、资源释放。未发生的可选阶段写 null。时间线采用同一起点
的微秒 offset，按相邻边界之差计算时长，阶段不重复；内存构建包含扫描/调度，排空等待
包含已经开始的内存插入结束，FlushPages 本体不包括之前的锁等待。

flush 测量页面物化，并不等于存储设备的持久化/fsync 延迟；disk_insert 包含
剩余扫描、插入与等待，finalize 包含并行收尾但串行也有少量收尾开销。
空表/init fork 的 memory_build 只代表空扫描路径与设置开销，不声称插入了向量。

首次 spill 请求在 allocatorLock 下唯一记录；刷盘本体在独占 flushLock 内由
唯一执行者记录；leader 等所有 participant 完成后读取。共享计时在释放 DSM
前复制到 leader 私有数据。失败/取消时不输出 complete 摘要，工具必须结合命令
返回码与摘要完整性判定，禁止把 AM 内部完成理解成命令提交成功。

## 预算与验收关口

本轮预计用户阅读/复现 2–3 小时，计入项目预算；机器构建/回归单独记录，不
虚报个人学习投入。若需要数据库核心变更或超过这个范围的方案，再做范围决策。

1. 原型编译并验证串行内存/spill 与并行路径；
2. 接入诊断工具，完整性检查和“证据—判断—建议—复验”；
3. TAP 验证真实调用、阶段/时间覆盖、未发生阶段、连续构建与取消/失败后恢复；
4. 专项通过后运行 HNSW 全量回归，独立镜像做关闭/开启开销与低/高内存对照；
5. 在 CentOS Stream 9 Machine 本地磁盘复验当前候选。
