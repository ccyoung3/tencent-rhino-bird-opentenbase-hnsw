# 2026-09-10 GloVe 本地验证快照

本快照接续 9/6 C 候选，不覆盖或重写旧快照。本轮只增加真实向量实验工具、
案例与校验；不是 Git commit、维护者 Review 或上游交付。

## 两个时间点，不混淆源码身份

- 正式实验使用的脚本保存在
  [tooling-at-start.tar.gz](../../../experiments/hnsw_build/results/20260909T135759Z-glove-formal-cases/tooling-at-start.tar.gz)。
  控制器与报告器哈希由 protocol.json 记录；其他测量工具哈希由各次 summary 记录。
- 正式实验完成后，只修改控制器 SIGINT 转发：通知子 Python 进程，而不先中断
  整个子进程组，以便按已有逻辑取消自己的 SQL 后端并清理实例。对应新增一个
  单元测试；没有更改正式测量入口、数据、C 或已保存的测量。新增真实端到端
  校验脚本验证成功、超时和中断。
- 本轮最终工具保存在 `validated-tooling.tar.gz`，包含测试、验证脚本与共用工具。
  此处 `audit.json` 记录当前源文件、文档与全部 GloVe 结果文件的 SHA-256；
  其中 `recall_target_met=false`，不把实验 passed 解释成召回达标。

## 验收入口

- [全量正式报告](../../../experiments/hnsw_build/results/20260909T135759Z-glove-formal-cases/report.md)
- [中文解读与边界](../../../docs/2026-09-09-glove-validation.md)
- [59/59 单元测试](python-tests-venv.log)
- [系统 Python：54 通过、5 skip](python-tests-system.log)
- [真实端到端 3/3](../../../experiments/hnsw_build/results/20260910T014813Z-glove-e2e-verification/summary.json)
- [离线反算及哈希清单](audit.json)

`audit.py` 是这批已保存证据的离线反算脚本，不调用实验汇总器的聚合函数。
它检查六次原始 NOTICE 与内部时间线、三次组内统计、固定数据/镜像/工具/并行度、
不重叠且确定的 query 划分、12,000 条返回 ID 的 Recall 与时延分位数、查询测量
顺序，以及保存的精确检查和索引计划。数据距离再用 float64 余弦独立反算。
它没有重跑 SQL，也不声称覆盖所有代码缺陷。

从当前项目根目录运行（需已有源码 checkout、本地 HDF5 与可选依赖环境）：

```bash
.venv-glove/bin/python dev/snapshots/20260910-glove/audit.py
```

这会重新生成本目录 `audit.json`，不修改原始测量、数据库或 Git 状态。不要用
Python 的 `-O` 关闭断言。哈希是内容身份与传输核验，不是签名或逻辑正确性证明。
若想验证已有快照是否改动，应先比较 `audit.json` 中既有哈希，不先覆盖清单。

所有正式及测试临时数据库已清理，结果与原始失败均保留；约 463MiB 数据缓存
和虚拟环境被 ignore，只在本地。本轮 C/TAP 与 9/6 相同，因此没有重跑历史
Debian/CentOS 的 632 个 TAP 断言与 4 项 SQL regression；计时开销仍无稳定上限保证。
