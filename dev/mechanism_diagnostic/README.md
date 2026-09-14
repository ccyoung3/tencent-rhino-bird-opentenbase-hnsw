# 本地 HNSW 机制诊断工具

这套工具区分建图工作量与进程 CPU 时间，仅用于内部实验。插桩不进入 pgvector
候选工作区，不输出“低于 5%”验收结论。先读
[固定方案](../../docs/2026-09-13-parallel-mechanism-diagnostic.md)。

`instrument.py` 仅接受解包到临时目录的源码副本，拒绝产品 checkout、重复插桩、
不匹配的源码锚点和符号链接。`build.py` 从既有统一构建清单锁定原版、候选、编译器
及运行时；两个镜像都保留 leader seed42 和未固定的 worker 随机流。

从项目根目录执行，所有输出路径必须为新路径。编译会使用已经在本机核验的
两个基础镜像，不访问包仓库或拉取新基础镜像：

```bash
.venv-glove/bin/python dev/mechanism_diagnostic/build.py \
  dev/snapshots/20260913-mechanism-diagnostic/build-NEW

.venv-glove/bin/python experiments/hnsw_build/mechanism_diagnostic.py \
  dev/snapshots/20260913-mechanism-diagnostic/build-NEW/build-manifest.json --mode smoke
```

预检只做 9 次，不进入随后 54 次诊断。分别完成后，离线审计对应目录：

```bash
.venv-glove/bin/python experiments/hnsw_build/audit_mechanism.py \
  --run experiments/hnsw_build/results/<本次机制目录> \
  --output experiments/hnsw_build/results/<本次机制目录>/independent-audit.json
```

完整诊断使用同一镜像清单、`--mode diagnosis`。要求 AC、没有其他本项目构建运行，
三个专用回环端口空闲；不会重用已有业务数据库。它创建并清理自己的实例和卷，
保留原始错误及不完整批次，不能把失败批当完整结果。54 次范围不能按结果追加。

三个参与进程各输出一条 `HNSW_MECHANISM` JSON。`distance_calls` 表示真正调用
HNSW 距离函数的次数，包含内存搜索、磁盘搜索和邻居筛选；不含向量归一化、相等
比较或直接赋零。计数及进程 CPU 仅覆盖 `scan_and_insert`，不覆盖扫描后最终
flush、WAL、清理与 SQL 收尾。三个 CPU 时间可以相加，三个 elapsed 时间不能相加。

即使距离数接近，也不保证相同图、相同指令量、缓存行为或锁竞争；CPU/距离仅是
描述性指标。计数分支和日志本身也可能扰动调度，不能用它们归一化后改判旧验收。

完整插桩上游源码归档留在本地并由快照引用，不作为个人仓库交付资产。
生成器、补丁、身份、协议、日志和结果可单独审阅；不需要重跑耗时实验来阅读结论。

本轮完整结论见[结果说明](../../docs/2026-09-13-parallel-mechanism-results.md)。
`instrumentation_bridge.py` 另有预先固定的12次原镜像/插桩对照，使用旧普通镜像
与新计数镜像；`audit_bridge.py` 独立核验。该入口同样只用于内部实验，不按效果
追加、不与机制诊断或正式验收合并。

离线检查：

```bash
.venv-glove/bin/python -m unittest discover -s dev/mechanism_diagnostic -p 'test_*.py'
.venv-glove/bin/python -m unittest discover -s experiments/hnsw_build -p 'test_mechanism.py'
```
