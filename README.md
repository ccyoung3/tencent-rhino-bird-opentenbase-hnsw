# OpenTenBase HNSW 构建诊断

为数据库工程师和 DBA 提供 HNSW 索引构建的进度、阶段耗时与调参依据。构建变慢时，先看清时间花在哪里，再通过参数调整后的复验判断效果。

基于 **OpenTenBase 18.6 / PG18 + pgvector 0.8.6**，包含 pgvector 诊断补丁和 Python 命令行工具。

[使用文档](docs/usage.md) · [实验结果](docs/results.md) · [实现说明](docs/README.md)

## 主要功能

- **查看进度与耗时**：细分内存加载、刷盘、磁盘加载和 WAL 阶段，按需开启八段内部计时。
- **诊断与参数复验**：生成包含落盘、内存和参数信息的报告，提供调整建议，并检查构建时间、Recall@K 与查询延迟。
- **观察已有任务**：通过只读连接查看指定构建会话的阶段与等待状态，支持中途接入。

## 使用效果

一次完整的使用过程是：**查看构建进度 → 阅读诊断报告 → 调整参数 → 对比复验结果**。

在 GloVe-100 的约 118 万条向量案例中，报告帮助定位了落盘后的耗时区间。将构建内存从 **1024MB 调至 1792MB** 后，落盘由 **3/3 次变为 0/3 次**，构建时间中位数从 **23.6 分钟降至 5.4 分钟**，同时容器内存峰值增加。

这是同一环境下、每档三次构建的参数调整收益。诊断工具提供定位和复验依据，该结果不代表补丁本身带来相同幅度的加速。

[查看诊断报告](presentations/hnsw-diagnostics/evidence/glove-low-r1-diagnostic.md) · [查看完整对照](experiments/hnsw_build/results/20260909T135759Z-glove-formal-cases/report.md)

## 快速开始

准备 **Git、Python 3.11+、Docker 和 Docker Compose**。当前验证环境为 Linux ARM64；以下步骤也适用于通过 Docker 运行该环境的 Apple Silicon Mac。本机端口 `55432` 需空闲。

**1. 获取项目，准备固定版本的源码**

```bash
git clone https://github.com/ccyoung3/tencent-rhino-bird-opentenbase-hnsw.git
cd tencent-rhino-bird-opentenbase-hnsw
python3 dev/prepare_sources.py
```

源码准备脚本自动下载上游版本、应用补丁并核对摘要；已有源码目录会拒绝覆盖。

**2. 构建运行镜像**

```bash
docker build --platform linux/arm64 --target runtime \
  -t opentenbase-pg18-pgvector:review-arm64 -f dev/Dockerfile .
```

**3. 运行一个低内存案例**

```bash
python3 experiments/hnsw_build/run.py \
  --isolated --image opentenbase-pg18-pgvector:review-arm64 \
  --build-timing --rows 10000 --dimensions 32 \
  --maintenance-work-mem 1MB --parallel-workers 0 \
  --statement-timeout-ms 180000 --label review-low
```

运行结束后，终端会给出结果目录。先打开 `diagnostic.md` 阅读诊断；`summary.json` 保存完整参数与结果，`progress.csv` 保存进度采样。本次临时数据库会自动清理。

接着将 `--maintenance-work-mem` 改为 `64MB`、`--label` 改为 `review-high` 再运行一次，即可比较落盘与耗时变化。详细步骤见[使用文档](docs/usage.md)。

## 实现与验证

C 改动位于外置 pgvector，OpenTenBase 核心源码保持原样。仓库通过“固定上游版本 + 补丁”提供实现，源码准备脚本会同时补齐新增测试。

- **代码**：[C 补丁与测试](dev/snapshots/20260906-build-timing/) · [构建诊断工具](experiments/hnsw_build/run.py) · [只读观察器](experiments/hnsw_build/observe.py)
- **验证**：独立目录复现已通过 120 项 Python 测试、221 个计时专项断言和三个运行案例。[查看记录](dev/validation/20260914-repository/README.md)
- **更多结果**：[召回与延迟、诊断开销及环境说明](docs/results.md) · [代码与完整证据索引](docs/README.md)

诊断增强的三项并行条件尚未证明低于自设 5% 开销参考线。现有结果来自本地公开与合成数据，具体条件和限制随实验报告保留。

---

腾讯犀牛鸟开源计划 · OpenTenBase 项目二：向量索引构建与诊断增强。
