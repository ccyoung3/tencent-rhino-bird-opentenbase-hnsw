# 实现与证据索引

返回[仓库首页](../README.md)。首次阅读从[使用方法](usage.md)和[效果说明](results.md)开始。

## 五分钟了解项目

1. 看首页的主要功能和使用效果，了解工具的用途。
2. 看一次[实际诊断报告](../presentations/hnsw-diagnostics/evidence/user-experience/manual-low/diagnostic.md)
   和[调整后报告](../presentations/hnsw-diagnostics/evidence/user-experience/manual-high/diagnostic.md)。
3. 看[正式效果与限制](results.md)，区分参数收益和诊断成本。
4. 需要运行时，按[最小复现](usage.md)准备固定源码与新镜像。

## 代码阅读顺序

本仓库采用“固定上游版本 + 冻结补丁 + 工具”的组织形式。上游源码通过
`dev/prepare_sources.py` 获取，不重复提交整份 checkout。

| 内容 | 入口 | 重点 |
|---|---|---|
| 固定版本、重建与摘要核对 | [prepare_sources.py](../dev/prepare_sources.py) / [冻结清单](../dev/snapshots/20260906-build-timing/validated-manifest.json) | OpenTenBase 与 pgvector 的精确 commit；五个候选文件的 SHA-256 |
| C 诊断与阶段协调 | [pgvector.patch](../dev/snapshots/20260906-build-timing/pgvector.patch) | `src/hnsw.c`、`src/hnsw.h`、`src/hnswbuild.c`，以及低内存测试修改 |
| 新增内部计时测试 | [049_hnsw_build_timing.pl](../dev/snapshots/20260906-build-timing/049_hnsw_build_timing.pl) | 该文件单独交付，源码准备脚本会补齐 |
| 构建与报告 | [run.py](../experiments/hnsw_build/run.py) / [timing.py](../experiments/hnsw_build/timing.py) | 参数、采样、计时摘要校验、失败与清理 |
| 只读观察 | [observe.py](../experiments/hnsw_build/observe.py) / [test_observe.py](../experiments/hnsw_build/test_observe.py) | 读取指定 PID，权限/状态区分和只读边界 |
| Recall 与案例 | [recall.py](../experiments/hnsw_build/recall.py) / [glove.py](../experiments/hnsw_build/glove.py) | 精确对照、独立查询、召回和时间代价 |
| 性能方法 | [overhead_crossover.py](../experiments/hnsw_build/overhead_crossover.py) / [audit_crossover.py](../experiments/hnsw_build/audit_crossover.py) | 完整批次、面板内汇总、独立分析与判定 |

上游来源：[OpenTenBase](https://github.com/OpenTenBase/OpenTenBase) 与
[pgvector](https://github.com/pgvector/pgvector)。准备后的源码保留其原有版权和许可文件。
当前产品候选是 9/6 版本；`dev/mechanism_diagnostic/` 中的探索性插桩与
`dev/snapshots/20260913-parallel-variance/draft.patch` 不属于已交付候选。

## 本次仓库复现

[2026-09-14 验证记录](../dev/validation/20260914-repository/README.md)：从固定上游版本
重建候选，221 个计时断言、120 项 Python 测试和三个文档小案例通过。
这项检查证明最小交付流程可运行，不替代下面的正式实验。

## 正式证据

- [GloVe 内存案例](../experiments/hnsw_build/results/20260909T135759Z-glove-formal-cases/report.md)：六次构建及原始目录链接。
- [独立召回新轮](../experiments/hnsw_build/results/20260910T074253Z-bounded-recall/report.md)：新索引、独立查询与延迟代价。
- [完整开销对照](../experiments/hnsw_build/results/20260912T174623Z-bounded-crossover-formal/report.md)：12 项结果及全部样本。
- [只读观察验证](../experiments/hnsw_build/results/20260912T144752Z-observe-e2e/summary.json)：受限账号 11 项真实检查。
- [C 功能验证清单](../dev/snapshots/20260906-build-timing/validated-manifest.json)：发行版、源码摘要、测试计数和日志入口。
- [全部实验证据索引](../experiments/hnsw_build/results/README.md)：包含早期、失败和预检记录，不能与正式批次混用。

## 会议交流材料

现有[阶段汇报](../presentations/hnsw-diagnostics/README.md)可辅助介绍切入点、架构和结果。
本轮优先整理仓库、准备线上交流，未制作视频。幻灯片中的交付待确认内容是制作时
的状态；活动方已说明本期直接提交个人仓库链接，不以 PR 为重点。

适合会议演示的顺序：构建与进度 → 报告依据 → 参数调整 → 复验结果 → 正式证据与限制。
提交入口或时间等尚需协调的事项可在交流末尾确认。

## 历史设计与开发记录

以下文件保留当时的实验结论和决策，不作为当前首次使用流程。旧文档中的“本人
Review 待完成”“等待上游接收目录”等描述，应结合首页当前状态阅读。

- [整理前的开发首页](history/README-before-delivery-2026-09-14.md)：逐轮工作与原有入口。
- [实现范围](2026-09-02-hnsw-diagnostic-scope.md)、[内部计时设计](2026-09-05-hnsw-build-timing.md)。
- [项目过程复盘](2026-09-12-project-overall-review.md)、[开发收尾](2026-09-12-development-closeout.md)。
- [正式性能方法](2026-09-12-performance-method-review.md)、[机制与桥接结果](2026-09-13-parallel-mechanism-results.md)。

原始会议音频、逐字稿和讲解稿在作者本地留档，不随仓库发布；历史笔记指向这些
材料的链接也仅在原工作区可用。现有正式结果、原始数据与冻结摘要保持原样。
