# OpenTenBase｜HNSW 索引构建与诊断

腾讯犀牛鸟 OpenTenBase 实战项目的本地工作区。当前方向是：在固定版本和
固定负载下理解 pgvector HNSW 的构建路径，建立可重复的诊断基线，再提交一个
范围可控、带测试的可观测性改进。

从零开始 Review，请先读 [[docs/2026-09-04-frozen-snapshot-review|从零 Review 导览]]：
按“真实输出 → C 改动 → Python 工具 → 测试 → 环境与性能”五站推进。
该页前半部分覆盖 9 月 6 日候选；末尾的 9 月 4 日审查仅是历史记录，不覆盖新计时代码。

## 当前状态

2026-09-05：用户批准新增“可靠内部阶段计时”一轮开发，当前状态为进行中。
以下测试/冻结说明属于上一版；新代码须重新验证。范围与基线归档见
[[docs/2026-09-05-hnsw-build-timing]]。

2026-09-06：内部计时、报告接入与失败清理已实现。Debian/CentOS 新候选均通过
28 个 HNSW TAP 文件 / 632 断言和 4 项 SQL regression；工具 45 项单元测试、
9 个端到端成功/失败/取消用例通过。36 次隔离实验和 40 次配对测量（另有 8 次
warmup）已完成；开销仍有明显波动，不能宣称零开销。新候选待独立 Review。

2026-09-08：已在用户个人账号下创建[私有项目仓库](https://github.com/ccyoung3/tencent-rhino-bird-opentenbase-hnsw)，
用于保存腾讯犀牛鸟 OpenTenBase 项目的本地化资产。该仓库不是 OpenTenBase 或
pgvector 的 fork；会议原始材料与两个上游源码 checkout 不上传，不向上游提交
PR，也不改动上游远端。只有用户 Review 确认后，才另行决定是否影响 OpenTenBase。
仓库提交统一使用用户本人的 Git 身份，不引入 AI/Codex contributor。

### 上一版基线（9 月 4 日冻结）

- `进行中`：本地交付候选已验证，远端交付尚未开始；
- 硬截止：`2026-09-14` 提交结果；本地交付候选计划在 `2026-09-12` 冻结；
- 已完成：4 个 HNSW 构建阶段、spill 诊断上下文、可重复实验工具与本地报告；
- 已通过：全部 HNSW TAP（27 个文件、411 个断言）、4 项 HNSW SQL regression、
  专项 TAP（5/5）、实验工具单元测试（28/28），以及串行/并行、全内存/spill
  功能实验；
- CentOS 补充验收：在 OrbStack CentOS Stream 9 原生 ARM64 Machine 中完成
  OpenTenBase 18.6 clean build/install、pgvector `-Werror`、动态链接、专项 TAP、
  4 项 SQL regression、最小 HNSW smoke 和全部 27/411 TAP；全部通过、0 skip；
- 诊断输出：每次运行生成阶段 sampled span、tuple 进度区间、spill 上下文、
  可选 Recall@K/服务器执行时间、调参建议和解释边界；
- 参数与召回：完成固定 topology 的 50k×64 参数矩阵；两个关键配置的扩展曲线
  各重复 3 次，形成 `ef_search → ef_construction → m` 的条件式调整顺序；
- 内存与规模：完成行数、维度和 `m` 三条控制变量；实际上探到 1M×64，构建
  `247.056s`、HNSW 测试埋点内存 `925MiB`、无 spill；正式规模线统一为
  0.2 秒采样间隔；
- 异常证据：区分上游已有的空表/NULL/非法参数等回归与本项目新增的低内存、
  低召回、阶段/DETAIL 和 1M 边界证据；
- 前后对照：50,000×64 维固定拓扑实验中，全内存与 spill 场景的构建耗时变化
  分别为 `-0.158%` 和 `+0.192%`，未观察到可分辨的性能或索引大小回归；
- 尚未完成：负责人/维护者的人类 Review、负责人确认代码归属/提交入口、按目标
  形态最终 clean rebuild，以及用户决定后的 commit、push 或 PR；AI 只读交叉
  审查已经完成且没有发现 P0/P1；
- 环境证据：[[docs/2026-09-02-mac-arm64-baseline]]；
  [[docs/2026-09-03-centos-stream9-arm64-compatibility]]。
- 实现范围：[[docs/2026-09-02-hnsw-diagnostic-scope]]。
- 本地验证：[[docs/2026-09-02-local-implementation-evaluation]]。
- 一页说明：[[docs/2026-09-02-project-brief]]。
- 组内衔接：[[docs/2026-09-02-research-integration]]。
- 倒排计划：[[docs/2026-09-02-delivery-plan]]。
- 需求复核与续作留痕：[[docs/2026-09-03-requirements-progress-audit]]。
- 参数诊断：[[docs/2026-09-03-hnsw-parameter-diagnostics]]。
- 内存规模：[[docs/2026-09-03-hnsw-memory-scale]]。
- 异常矩阵：[[docs/2026-09-03-hnsw-anomaly-matrix]]。
- 冻结快照审查：[[docs/2026-09-04-frozen-snapshot-review]]。

## 工作区

| 路径 | 用途 |
|---|---|
| `OpenTenBase/` | `REL_18_STABLE` 的本地开发分支 |
| `pgvector/` | `v0.8.6` 的本地开发分支与 HNSW 源码 |
| `dev/` | Mac ARM64 Docker 环境及 CentOS Stream 9 Machine 兼容性复现 |
| `experiments/hnsw_build/` | 隔离数据卷的实验工具、比较器与机器可读结果 |
| `docs/` | 环境基线、实现设计、验证报告与交付计划 |

会议 PDF、音频与逐字稿保留在本目录作为需求来源，不改名、不移动。

## 开始使用

```bash
docker compose -f dev/compose.yml build
docker compose -f dev/compose.yml up -d
docker compose -f dev/compose.yml exec -T db \
  psql -v ON_ERROR_STOP=1 -U postgres -d postgres < dev/sql/smoke.sql
```

完整说明见 [[dev/README|Mac ARM64 开发环境]]。
CentOS 兼容性复现见 [[dev/centos/README|CentOS Stream 9 ARM64 兼容性复现]]。

## 第一阶段边界

只做 HNSW 构建可观测性与诊断，不同时扩展到 IVFFlat、新量化算法、DiskANN、
分布式执行或自动调参。Mac 数据只用于功能验证和同机相对实验，不包装成生产
服务器的绝对性能结论。

## 下一步

1. 根据本轮留痕复现并理解内部计时、失败清理与报告边界；保留当前候选与原始证据；
2. 请负责人或维护者对新候选和实验方法做正式人类 Review；如果要求明确开销门限，
   先约定标准，再在稳定空闲环境复验，不宣称当前已证明零开销；
3. 向负责人确认 `REL_18_STABLE` 最终接收外置 pgvector 补丁，还是要求移入
   `contrib/pgvector`，并确认具体提交入口和时刻；
4. 按确认后的目录形态做一次 clean rebuild 与专项回归；
5. 在用户明确开始交付后，再整理 commit、push 或 PR；当前不做远端写入。
