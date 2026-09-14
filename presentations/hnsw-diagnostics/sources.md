# 汇报来源索引

截至 2026-09-13。幻灯片中的 `[Sx]` 对应下列本地证据与公开来源。数值来自归档实验与 S15 的手动体验记录，本次排版未重新测量。代码与模板来源按真实归属引用。

| 编号 | 支撑内容 | 来源 |
|---|---|---|
| S1 | 项目二原始要求、选题范围、目标用户、已有能力与贡献边界、当前状态 | [项目整体复盘](../../docs/2026-09-12-project-overall-review.md)，第 2、5、6、9、10 节；该文已索引启动会原材料 |
| S2 | 第一版阶段细分、spill 上下文、工具与 OpenTenBase 本地实现 | [本地实现与评估](../../docs/2026-09-02-local-implementation-evaluation.md) |
| S3 | 八段计时、并行生命周期、失败/取消行为、默认关闭、两环境 632 断言与 4 项 SQL 回归 | [计时实现与验收](../../docs/2026-09-05-hnsw-build-timing.md)；[9/6 候选归档](../../dev/snapshots/20260906-build-timing/) |
| S4 | 120 项工具测试、观察器 11 项本地复验、开发边界 | [开发收尾](../../docs/2026-09-12-development-closeout.md)；[观察复验原始汇总](../../experiments/hnsw_build/results/20260912T144752Z-observe-e2e/summary.json)；[工具测试日志](../../dev/snapshots/20260913-mechanism-diagnostic/tool-tests.log) |
| S5 | 全量 GloVe 构建内存对照、实际诊断报告、spill 分段案例、资源代价 | [案例报告](../../experiments/hnsw_build/results/20260909T135759Z-glove-formal-cases/report.md)；[1024MB 第一次实际运行](../../experiments/hnsw_build/results/20260909T140726Z-glove-formal-low-r1/summary.json)；[随包完整诊断原文](evidence/glove-low-r1-diagnostic.md) |
| S6 | 同一最终索引的 Recall 与延迟、1000 独立验证查询、选参边界 | [有限召回新轮报告](../../experiments/hnsw_build/results/20260910T074253Z-bounded-recall/report.md)；[原始汇总](../../experiments/hnsw_build/results/20260910T074253Z-bounded-recall/summary.json) |
| S7 | 正式新旧对照、24 面板统计口径、9 项支持与 3 项未证明 | [冻结方法](../../docs/2026-09-12-performance-method-review.md)；[完整正式结果](../../experiments/hnsw_build/results/20260912T174623Z-bounded-crossover-formal/report.md)；[原始汇总](../../experiments/hnsw_build/results/20260912T174623Z-bounded-crossover-formal/summary.json)；[独立审计](../../experiments/hnsw_build/results/20260912T174623Z-bounded-crossover-formal/independent-audit.json) |
| S8 | 原交付顺序、9/14 提交日期来源、最终目录及流程待确认 | [交付计划](../../docs/2026-09-02-delivery-plan.md)；[整体复盘第 10 节](../../docs/2026-09-12-project-overall-review.md) |
| S9 | 机制计数、插桩桥接、固定 CPU 工作、未应用 C 草案及解释限制 | [机制与校准报告](../../docs/2026-09-13-parallel-mechanism-results.md)；[固定工作校准原始汇总](../../dev/cpu_calibration/results/20260913T030031Z-ce171210b519/summary.json)；[独立校准报告](../../dev/cpu_calibration/results/20260913T030031Z-ce171210b519/report.md) |
| S10 | 用户指定模板、作者与许可、固定版本使用方式 | [Typst Universe](https://typst.app/universe/package/touying-simpl-ecnu)；[模板仓库](https://github.com/ccyoung3/touying-simpl-ecnu) |
| S11 | 流程与架构绘图库 diagraph 0.3.7，MIT 许可；本稿使用 DOT 与 Typst 标签 | [Typst Universe](https://typst.app/universe/package/diagraph)；[官方仓库](https://github.com/Robotechnic/diagraph) |
| S12 | 数据绘图库 lilaq 0.6.0，MIT 许可；本稿使用条形、散点、参考线及标注 | [Typst Universe](https://typst.app/universe/package/lilaq/)；[官方文档](https://lilaq.org/) |
| S13 | 宿主 CPU / RAM、版本、功能 / 案例 / 性能三类环境与实例上限 | [硬件归档](../../dev/snapshots/20260911-overhead-acceptance/environment-20260912-review.json)；[ARM64 基线](../../docs/2026-09-02-mac-arm64-baseline.md)；[GloVe 环境与预检](../../docs/2026-09-09-glove-validation.md)；[正式方法](../../docs/2026-09-12-performance-method-review.md)；[正式协议](../../experiments/hnsw_build/results/20260912T174623Z-bounded-crossover-formal/protocol.json)；[随包环境摘要](environment-summary.md) |
| S14 | 第 3 页原始需求映射、行数 / 维度 / m 控制变量、异常场景与参数建议 | [需求审计](../../docs/2026-09-03-requirements-progress-audit.md)；[内存规模记录](../../docs/2026-09-03-hnsw-memory-scale.md)；[参数诊断](../../docs/2026-09-03-hnsw-parameter-diagnostics.md)；[异常证据矩阵](../../docs/2026-09-03-hnsw-anomaly-matrix.md)；后续完成情况以 S3–S7 为准 |
| S15 | 第 4 页的用户操作、自动诊断报告与 8MB / 64MB 各一次复验 | [低内存报告](evidence/user-experience/manual-low/diagnostic.md)、[原始汇总](evidence/user-experience/manual-low/summary.json)、[进度样本](evidence/user-experience/manual-low/progress.csv)；[高内存报告](evidence/user-experience/manual-high/diagnostic.md)、[原始汇总](evidence/user-experience/manual-high/summary.json)；[预览来源及截图状态](evidence/user-experience/preview-provenance.json) |
| S16 | 第 3 页的上游阶段粒度、构建内存影响和召回 / 速度权衡 | pgvector **v0.8.6** 官方 README：[HNSW 进度](https://github.com/pgvector/pgvector/blob/v0.8.6/README.md#indexing-progress)、[构建耗时](https://github.com/pgvector/pgvector/blob/v0.8.6/README.md#index-build-time)、[查询参数](https://github.com/pgvector/pgvector/blob/v0.8.6/README.md#query-options)、[召回监测](https://github.com/pgvector/pgvector/blob/v0.8.6/README.md#monitoring)；2026-09-13 核验 |
| S17 | 第 3 页的真实用户调参疑问，作为问题存在的公开个例 | pgvector 官方仓库 [Issue #969](https://github.com/pgvector/pgvector/issues/969)，原题为 `Tuning maintencne_work_mem to improve HNSW index build time`；2026-03-15 发起，2026-09-13 核验时已关闭；提问环境为 pgvector 0.8.2 |

## 第 3 页：问题依据与目标人群

主要人群是负责 HNSW 构建和调参的数据库工程师 / DBA；检索平台工程师协同做质量验证。这是依据项目工作流形成的定位 [S1]，不是客户访谈结果。

S16 在本项目基线版本中列出两个 HNSW 阶段，并说明内存预算和搜索参数会影响性能。“需要补充阶段耗时与复验依据”是本项目据此作出的需求判断。S17 中的用户报告了增大内存后收益不明显，并询问适用条件，说明确实有人遇到这类调参困难。

这些来源支撑问题的现实依据，不衡量发生比例；已关闭的历史提问不等于当前版本缺陷，也不证明本项目已在该用户环境解决问题。本地验证结果和生产效果仍需区分。

## 数值口径

- 第 2 页以层次表示上游基础与本次增强的依赖关系，不表示新的 HNSW 算法或自动执行流程。第 3 页以关系图连接主要使用者、三个问题和对应帮助，灰线表示用户面对的问题，蓝箭头表示本次提供的判断依据；不表示执行顺序或量化效果。公开依据保留为页脚链接，具体机制、异常验证和完整六项证据映射保留在讲稿。两页均不表示已获项目方接收。
- 第 4 页：手动体验的完整构建命令耗时为 72.998722 / 14.402411 秒，分别显示为 73.00 / 14.40 秒。内部 disk_insert=70.307945 秒，占内部总时间 72.820972 秒约 96.5%。两次同负载、同镜像，仅构建内存为 8MB / 64MB，各一次，不代替稳定性或性能验收。报告图是原文节选的阅读器预览；左下为同次运行的真实进度样本占位，终端截图待补。64MB 由使用者选择，不是工具自动设置。
- 第 7–8 页使用同一次 1024MB 实际运行：第 7 页左侧是字段排版节选，右侧为原报告四段诊断内容的中文摘录；`disk_insert=982.004717s`、`spill=True` 和 69.4% 均来自该运行。不是现场运行或产品界面截图。
- 第 8 页：选用 1024MB 第一次运行，按 setup、memory_build、spill_drain、flush、disk_insert、finalize、wal、cleanup 的原始秒数累计成一条时间分解横条。四个主要区间标注秒数和比例，短的 flush / WAL 使用引线，条宽不人为放大；其余四段合计 0.067768s，保留原宽度。内部总时间 1414.450097s，完整命令 1414.648555s，二者不能混同。
- 第 9 页：每档三次独立构建，左图蓝点显示全部六次命令耗时，纵向轻微错位仅为分辨重叠；浅色条从零延伸至中位数，并保留三次范围与 spill 次数。右图是容器采样峰值的中位数，按同一预算行对齐，两图单位不同。耗时减少比例由 `1 − 326.571234 / 1414.648555` 计算，峰值增加比例由 `3580.6953125 / 2781.08203125 − 1 ≈ 28.8%` 计算。未画置信区间，峰值包含数据库和缓存。
- 第 10 页：同一个最终索引上的 `ef_search=400 / 1000`，来自新的验证集。横轴为查询 p50，纵轴为平均 Recall@10；两个点不是连续参数扫描或拟合曲线，虚线 95% 是自设平均目标。右图新增两配置的 p50 / p95 分组点图，共用从零起计的毫秒刻度，以圆点 / 方点及蓝 / 红两种方式区分配置；四个值是汇总统计量，不是原始样本或置信区间。召回差 4.34 个百分点，p50 比值 `28.998 / 3.740 ≈ 7.75`。展示舍入不改变底层数据。
- 第 11 页：632 为每环境断言总数，已包含新增计时专项 221；120 为工具测试，11 / 11 为本地实际检查。三组单位不同，仅用大数字和文字说明，不相加、不制造共同完成率。
- 第 13–15 页：路径和分支是当前材料状态、拟议交付顺序与待确认条件；灰色虚框为未完成步骤，不表示耗时估算或已获认可。
- 第 12、16 页：使用完整正式批的分析结果，不把中断批、机制插桩或 CPU 校准混入。第 12 页分为中位点估计、联合单侧上界两栏，分别用圆点与三角表示；两栏保持相同的 −2–10% 刻度及自设 5% 参考线。仅显示三个未证明项，未用连线表示双侧区间。上界针对聚合后配对比值中位数，经 12 项校正。它不是单次最坏开销或所有环境保证。
- 第 16 页：完整 12 项按四个场景、三种模式排列；每列使用相同的 0–10% 刻度，横条从各列的零点延伸至该项单侧上界，条尾保留两位小数。蓝色表示支持低于自设 5%，红色表示尚未证明；三条虚线均为同一个 5% 参考值。这些条形不是实测点估计或双侧置信区间。
- 第 17 页：流程图对应冻结实验方法，“均须低于自设 5%”表示预定判定条件，不代表已经全部达到；面板独立可比、失败批和旧 A/A 记录的限制保留。
- 第 18 页：左侧汇总三类检查的解释限制及当前判断，不构成没有缺陷的因果证明。右侧按运行序号展示全部 12 次正式固定 CPU 工作耗时，不包含预热；纵轴从零起计，最小值 6.493s、最大值 8.471s 由同一数组取得，不连线或拟合趋势。仅用于展示该探测存在执行时间差异，不能用来计算产品开销或归一化 HNSW 时间。
- 第 19 页：24 GiB 为宿主内存，约 11.7 GiB 为 Docker 可见内存；6 GiB 为 GloVe 构建容器上限，2 GiB 为正式性能单实例上限。43 GiB 是 9/9 预检时的磁盘可用空间，不是容量或吞吐。不同验证类型不混批，环境摘要不代表新增测量。

`build_data.py` 从现有 JSON 抽取数据，在 `data.json` 的 `source_sha256` 中保留对应文件摘要。图表中的数字可能按展示需要舍入，完整精度留在数据文件。

随包附带十三个原样复制的关键报告 / 图片，复制来源及 SHA-256 见 `evidence/manifest.json`；可独立阅读的入口见 [reproduction.md](reproduction.md)。内存报告中的旧召回结果保留原样，第 10 页使用独立新轮报告。

启动会私人原材料、完整上游源码 checkout、数据库与大向量数据集均不随幻灯片复制。这里的项目内相对链接与归档报告中指向逐次运行目录的链接，需在完整原仓库目录中使用。
