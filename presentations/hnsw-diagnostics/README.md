---
title: OpenTenBase HNSW 阶段汇报初稿
status: 完成
date: 2026-09-13
tags: [opentenbase, hnsw, presentation]
---

# OpenTenBase HNSW 阶段汇报初稿

本页的“完成”仅指初版汇报文件已制作，不代表项目性能验收、维护者 Review 或正式交付完成。

- [放映版 PDF](hnsw-diagnostics.pdf)：19 页，15 页主报告、4 页技术附录。
- [可编辑 Typst 源码](main.typ)：沿用用户指定的 ECNU 模板。
- [逐页讲解备注](speaker-notes.md)：逐页建议时长、可选 3 分钟演示和常见追问。
- [来源索引](sources.md)：对应各页的 S1–S17，链接到原始记录、公开问题依据和模板、绘图库。
- [证据与复验入口](reproduction.md)：从随包真实报告开始，按需进入完整项目复验。
- [环境摘要](environment-summary.md)：区分功能回归、GloVe 案例与正式性能对照，附版本和候选身份。
- [图表数据](data.json)：从已有结果抽取数值并保存输入 SHA-256。
- [数据图实现](visuals.typ)、[逻辑图实现](logic.typ)与 [DOT 文件](graphs/)：当前放映稿使用八张 diagraph 图和八个 lilaq 数据图面板，另有原生 Typst 证据摘要。
- [附录 A 预览](appendix-a.png)：12 项开销比较的单页图片；完整放映使用 PDF。
- [内存对照预览](memory-comparison.png)：构建收益与资源代价的单页图片。
- [真实诊断输出预览](diagnostic-example.png)：第 7 页，展示同一次运行的证据、判断、建议与复验方案。
- [使用体验单页草稿](user-experience-draft.pdf)与[图片预览](user-experience-draft.png)：新增第 4 页，当前终端截图待补。
- [问题与人群预览](requirements-preview.png)与[单页 PDF](requirements-preview.pdf)：第 3 页，用三条图示路径连接主要使用者、遇到的问题和本次提供的帮助。
- [召回与延迟预览](recall-comparison.png)：第 10 页，以散点和分组点图展示质量与代价。

第 14–15 页以分支关系与交付路径展示接收条件，保留当前依据和建议方案。问题尚未发送，未收到接收、延期或豁免确认。真实业务库未试用，三个并行条件仍未证明低于自设 5% 参考线。

## 编辑与编译

模板是 Typst 幻灯片模板，原生输出 PDF，本次不包含 `.pptx`。文字、表格、流程、架构与数据图均可在 Typst、DOT 源码和 JSON 数据中修改；PDF 中的图形保持为矢量。

已验证环境为 Typst 0.15.0，固定导入：

```typst
#import "@preview/touying:0.6.1": *
#import "@preview/touying-simpl-ecnu:0.0.1": *
#import "@preview/diagraph:0.3.7" as dg
#import "@preview/lilaq:0.6.0" as lq
```

字体沿用模板中的 Libertinus Serif 和 Source Han Sans SC；使用体验页正文统一使用 Source Han Sans SC，命令和采样节选使用 Menlo。本机已安装。换机时需安装相应字体，或在 `main.typ` 和 `user-experience.typ` 中指定可用字体。

在此目录运行：

```sh
typst compile main.typ hnsw-diagnostics.pdf
```

上传到 Typst Web 项目时，至少包含 `main.typ`、`visuals.typ`、`logic.typ`、`user-experience.typ`、`data.json` 和完整的 `graphs/`、`assets/` 目录，保留相对路径。第一次编译可能需要下载固定版本的公开包。备注与来源文件可一起上传方便核对。

`data.json` 已包含编译所需全部数值，不需要原始实验目录。如果需要从项目证据重新抽取数值，可在本仓库运行：

```sh
python3 presentations/hnsw-diagnostics/build_data.py
```

这个脚本只读取现有结果，不启动数据库或新实验。它依赖本仓库的原始证据路径，不是独立演示环境安装器。

## 图形与数据表达

| 页码 | 图形 | 编辑入口 |
|---|---|---|
| 2 | 上游基础与本次三个增量的分层图 | `graphs/contributions.dot` 与 `logic.typ` |
| 3 | 使用者连接三类问题，再对应本次提供的帮助 | `graphs/user-questions.dot` 与 `requirement-story`；公开依据见 S16–S17，详细说明和六项证据映射保留在讲稿 |
| 4 | 使用步骤、真实报告节选截图与手动复验记录；终端图暂由原始采样占位 | `user-experience.typ`、`assets/`、`evidence/user-experience/` |
| 5 | C 构建端、进度与日志、Python 工具、报告数据流；标明本次增强与复用接口 | `graphs/architecture.dot` 与 `visuals.typ` |
| 7 | 真实报告字段与四段诊断内容的中文摘录 | `main.typ`；原文在 `evidence/glove-low-r1-diagnostic.md` |
| 8 | 八段内部时间累计分解，四个主区间标注，短区间引线 | `phase-chart`；全部宽度按原始时间，数据源 `data.json` |
| 9 | 按预算对齐的构建时间与容器峰值两图 | `memory-chart` 与 `resource-chart`；保留六次实测、中位数、范围和 spill 次数 |
| 10 | 平均召回与 p50 散点，并列 p50 / p95 分组点图 | `recall-chart`、`latency-chart`；95% 为自设平均目标 |
| 11 | C / 工具 / 本地观察三组证据摘要，包含关系明确 | `verification-evidence`；不同单位不共用数量轴 |
| 12 | 三个未证明条件的中位点估计与单侧上界分栏 | `overhead-chart`；两栏共用 −2–10% 刻度，各有 5% 参考线 |
| 13 | 当前候选与后续交付步骤 | `graphs/delivery-progress.dot`；虚框表示待完成 |
| 14 | 技术接收边界的三类确认条件 | `graphs/technical-decisions.dot` 与 `technical-decisions` |
| 15 | 接收位置、集成与交付路径 | `graphs/delivery-route.dot` 与 `delivery-route` |
| 16 | 四个场景 × 三种模式的全部 12 项单侧上界 | `overhead-matrix`；三列共用 0–10% 刻度，各有自设 5% 参考线 |
| 17 | 统一构建、固定实验、面板聚合与联合判定流程 | `graphs/performance-method.dot` 与 `performance-method` |
| 18 | 机制检查的解释关系，及全部 12 次正式 CPU 校准 | `graphs/mechanism-reasoning.dot`、`cpu-chart`；推理不等于因果证明 |
| 19 | 全稿唯一的环境配置对照表 | `main.typ`；同字段核对功能、内存案例、正式开销条件 |

2026-09-13 图形修订使用 diagraph 0.3.7 和 lilaq 0.6.0，沿用初稿的实测数据、性能结论与待确认问题，没有新增测量。六次构建点不是置信区间；开销图也不把点估计到单侧上界之间的距离画成双侧区间。

附录 A 随后由数值表改为横条比较图，保留全部场景、模式与上界数值。每列从零起计，以长度比较上界、以颜色区分判定；蓝色 9 项支持低于自设 5%，红色 3 项尚未证明，不能将红色解释为已确认的性能缺陷。

此前全稿图表统一修订覆盖当时的第 6–11、16–18 页：实验图补齐数值和单位，避免参考线或背景压住标注；功能验证、交付范围和证据入口保留文字表，并加强类别与结果层次。时间和内存使用不同单位，CPU 校准仅提供机制线索，均不改变原有性能结论。下述汇报重构调整了部分页序，当前页码以上表为准。

## 面向犀牛鸟汇报的内容重构

2026-09-13 按用户认可的 Review 建议，将主线调整为“问题与贡献 → 需求覆盖 → 架构与工程难点 → 真实诊断 → 两个复验案例 → 功能与性能边界 → 交付计划和待确认决定”。

- 第 2–6 页明确上游基础与本次增量，增加六项需求映射和并行可见性、计时可靠性两个工程难点。
- 第 7 页直接展示已有全量 GloVe 诊断报告，连接第 8–9 页的阶段依据与内存建议复验；第 10 页明确低召回风险和查询代价。
- 第 11–12 页分别讲功能验证与诊断开销；完整性能方法及机制线索保留在附录。
- 第 13–15 页列出具体交付候选、剩余步骤，以及带建议方案的接收问题。
- 第 19 页补齐验证环境摘要；八段计时细节、只读观察命令和可选现场演示移入讲稿与复验入口。

随包附带十三个原样复制的关键报告和图片，均记录来源与 SHA-256。完整项目中的逐次原始目录、数据库镜像、C 源码及大向量数据不随汇报包复制；本包是可独立阅读、编译的汇报材料，不是完整产品交付包。

## 减少表格，突出阅读逻辑

2026-09-13 按用户认可的改版方案，将含表格的页面从九页减至一页。放映稿只保留第 19 页用于按相同字段核对环境配置；其余使用分层、需求路径、证据摘要、交付阶段和决策分支表达关系。

第 8 页使用 lilaq 累计阶段分解，第 10 页以分组点图替代延迟小表。保留第 9 页的全部六次实测与中位数，以及第 12 / 16 页适合表达性能边界的现有图形。没有为了增加图形种类构造评分、完成比例或小样本分布图。

历史 `graphs/diagnostic.dot` 与 `workflow` 函数保留为可复用源码，当前放映稿未调用。模板校徽、背景、页眉页脚和配色保持原样；页数与实测数据、性能结论均不变。讲稿中的页序与图示阅读方式已同步。

## 讲述安排

新增第 4 页建议讲解约 50 秒，整体时长按逐页备注排练，可按场合加入约 3 分钟演示，第 14–15 页用于提出问题，实际讨论时间另计。这是建议安排，尚无已确认的活动方 PPT 时长要求。附录仅在追问时展开。

当前署名为 CCYoung，日期为 2026 年 9 月 13 日。初稿保留已知限制，后续可以按真实汇报时长压缩，而不改变已测结果。

模板来源：[touying-simpl-ecnu](https://typst.app/universe/package/touying-simpl-ecnu)，版本 0.0.1，MIT 许可。通过官方包导入，保留其校徽、背景、配色、导航、标题栏及页脚。

## 使用体验页草稿

新增第 4 页位于“回答了哪些问题？”之后，保留原“本次贡献”页的内容。左侧约 35% 展示命令节选和可选的另终端观察，右侧约 65% 展示自动生成报告的真实节选预览，底部由使用者调整参数及一次复验结果收尾。原第 4–18 页顺延为第 5–19 页。

使用用户手动完成的 manual-low / manual-high 两次报告，数值与此前 guided-demo-low 不混用。“内存溢出”改为“内存不足触发落盘（spill）”，避免被理解为程序异常。报告中的表格属于用户要求展示的真实产物节选，原环境对照表仍位于第 19 页。

本页样式修订统一了字体、步骤编号和对齐关系，放大报告节选，底部以浅色结果区呈现参数选择、耗时和落盘变化。

**待补素材：终端 B 的真实截图。** 截图接口拒绝访问 Codex 原生窗口，因此当前左下明确显示真实进度采样占位，不冒充终端截图。收到截图后只替换这一块。报告预览由原 Markdown 的指定行渲染并截取，节选范围与素材来源见 `evidence/user-experience/preview-provenance.json`。
