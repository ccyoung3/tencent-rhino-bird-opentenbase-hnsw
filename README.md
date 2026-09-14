# OpenTenBase HNSW 构建诊断与参数复验

面向负责向量索引构建和调参的数据库工程师、DBA，为 OpenTenBase PG18 上的
pgvector HNSW 增加构建诊断能力：看清耗时阶段、识别内存不足后的落盘路径，
再通过同负载复验判断参数调整是否有效。

腾讯犀牛鸟开源计划项目二的个人项目仓库。实现基线为 **OpenTenBase 18.6 / PG18
+ pgvector 0.8.6**；C 改动位于外置 pgvector，OpenTenBase 核心源码未改。

**阅读入口：[用法与最小复现](docs/usage.md) · [效果、测试与限制](docs/results.md) · [实现与证据索引](docs/README.md)**

## 三个主要亮点

- **构建过程有依据：** 在上游 HNSW 能力上细分四类构建阶段，补充落盘时的内存与
  索引参数；可选的八段内部计时默认关闭，开启后报告实际耗时区间。
- **从输出得到可复验的建议：** 工具保存阶段、日志、参数和资源数据，生成诊断
  报告，说明判断依据、建议与下一次需要比较的指标。
- **同时看到收益和代价：** 对比构建时间与容器内存，使用独立查询验证 Recall@K
  和查询延迟。只读观察器还可用于已有构建任务，停止观察不会取消构建。

```mermaid
flowchart LR
  A[查看构建进度] --> B[读取耗时与落盘信息]
  B --> C[选择参数调整]
  C --> D[同负载复验]
  D --> E[比较时间、内存与检索质量]
```

上游已经提供 HNSW 算法、进度视图和内存不足告警。本项目的贡献是诊断信息、
计时、观察与复验流程；参数调优收益与补丁本身的开销分别报告。

## 先看效果

| 案例 | 结果 | 解释与证据 |
|---|---|---|
| GloVe 构建内存对照 | 1024MB → 1792MB；构建中位数 1414.649s → 326.571s；落盘 3/3 → 0/3 | 两档各三次；容器峰值中位数 2781.1 → 3580.7MiB。这是参数调整收益。[完整报告](experiments/hnsw_build/results/20260909T135759Z-glove-formal-cases/report.md) |
| 独立查询验证 | 同一新索引上 ef_search 400 → 1000；平均 Recall@10 91.13% → 95.47% | 查询 p50 同时从 3.740 → 28.998ms；1000 个独立验证查询。[完整报告](experiments/hnsw_build/results/20260910T074253Z-bounded-recall/report.md) |
| 诊断增强开销 | 12 项比较中 9 项支持低于自设 5% 参考线，3 项并行条件尚未证明 | 完整结果保留；不宣称整体性能验收通过。[正式对照](experiments/hnsw_build/results/20260912T174623Z-bounded-crossover-formal/report.md) |

以上为 Linux ARM64 本地环境、公开或合成数据的结果。具体环境、重复次数、统计
方法及功能测试见[效果说明](docs/results.md)。没有真实业务库试用或生产性能保证。

## 开始使用

首次运行使用 Git、Python 3.11+ 和支持 `linux/arm64` 的 Docker / Compose。
在一个新 clone 中执行：

```bash
git clone https://github.com/ccyoung3/tencent-rhino-bird-opentenbase-hnsw.git
cd tencent-rhino-bird-opentenbase-hnsw
python3 dev/prepare_sources.py

docker build --platform linux/arm64 --target runtime \
  -t opentenbase-pg18-pgvector:review-arm64 -f dev/Dockerfile .

python3 experiments/hnsw_build/run.py \
  --isolated --image opentenbase-pg18-pgvector:review-arm64 \
  --build-timing --rows 10000 --dimensions 32 \
  --maintenance-work-mem 1MB --parallel-workers 0 \
  --statement-timeout-ms 180000 --label review-low
```

源码准备脚本获取固定上游 commit，应用冻结补丁、补齐新增 TAP 测试并核对 SHA-256。
已有源码目录会拒绝覆盖。首次构建需要下载源码和依赖；小规模运行只需 Python
标准库，结束后输出报告路径，并清理本次隔离数据库。

继续看[用法说明](docs/usage.md)：如何读报告、提高内存后复验、查看实时进度、
启用 Recall 检查，以及观察一个已经在构建的任务。
这套步骤已在独立目录验证，见[本次复现记录](dev/validation/20260914-repository/README.md)。

## 代码与材料在哪里

| 入口 | 内容 |
|---|---|
| [冻结 C 补丁与新增测试](dev/snapshots/20260906-build-timing/) | `pgvector.patch`、单独提供的 `049_hnsw_build_timing.pl`、固定版本和输入摘要 |
| [源码准备脚本](dev/prepare_sources.py) / [构建环境](dev/Dockerfile) | 从上游固定版本重建当前候选 |
| [构建诊断入口](experiments/hnsw_build/run.py) | 隔离构建、采样、日志、计时与报告 |
| [只读观察器](experiments/hnsw_build/observe.py) | 通过专用连接观察已有构建任务 |
| [实验工具目录](experiments/hnsw_build/) | Recall、GloVe、对照分析和测试 |
| [实现与证据索引](docs/README.md) | 代码阅读顺序、正式证据与历史记录 |
| [阶段汇报材料](presentations/hnsw-diagnostics/README.md) | 现有 PDF、图表来源和讲稿，供会议交流参考 |

## 当前交付状态

本地约定功能、试用验证和本人 Review 已完成。根据项目方最新说明，以个人仓库
链接和用法、效果文档提交；维护者反馈与活动评审尚待进行。当前三项性能证据限制
继续保留。会议交流围绕切入点、工具亮点、真实演示和结果展开。

早期首页中的逐轮过程和当时待办已保存在[开发首页存档](docs/history/README-before-delivery-2026-09-14.md)。
历史记录不代表当前仍需重新完成本人 Review，或必须先合入上游 PR 才能提交活动成果。
