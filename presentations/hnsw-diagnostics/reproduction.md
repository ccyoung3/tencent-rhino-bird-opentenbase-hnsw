# 汇报证据与复验入口

对应 2026-09-13 的 19 页阶段汇报。先核对已有报告，再按需要进入完整项目复验。新增使用体验页采用用户手动完成的本地两次构建记录，本次排版没有启动数据库或提交代码。

## 只拿到本汇报包时

以下报告和图片已随包附带，可以在解压后直接阅读。原文保持不变，复制前后的 SHA-256 见 [evidence/manifest.json](evidence/manifest.json)。

| 对应页 | 从这里开始 | 阅读重点 |
|---|---|---|
| 4 | [8MB 诊断报告](evidence/user-experience/manual-low/diagnostic.md)、[64MB 复验报告](evidence/user-experience/manual-high/diagnostic.md) | 手动使用体验，各一次；完整命令和可选进度查询见讲稿 |
| 7–8 | [一次 GloVe spill 构建的完整诊断原文](evidence/glove-low-r1-diagnostic.md) | 内部计时、spill 上下文及“证据—判断—建议—复验” |
| 9 | [GloVe 内存对照报告](evidence/glove-memory/report.md)的“构建内存对照” | 两档各三次、六次实测、spill 和容器峰值 |
| 10 | [有限召回新轮报告](evidence/glove-recall/report.md) | 新索引、调参与验证集分开、91.13% / 95.47% 与延迟 |
| 12、16–17 | [正式开销报告](evidence/performance/report.md) | 12 项完整结果、24 面板统计口径与证据限制 |
| 19 | [验证环境摘要](environment-summary.md) | 功能、案例与性能分别使用什么配置 |

内存报告保留了 9/9 旧轮召回结果，以免改写历史；第 10 页使用的是独立的 9/10 新轮报告。不能把两轮的索引和召回结果混在一起，也不能据此推断提高构建内存会提高召回。

本包可以独立编译幻灯片，见 [README.md](README.md)。图表全精度数值在 [data.json](data.json)，逐页解释见 [speaker-notes.md](speaker-notes.md)。完整数据库镜像、C 源码 checkout、测试运行器、向量数据和逐次实验目录不在本包内。归档报告中指向原实验目录的链接，需要在完整项目中使用。

## 拿到完整项目后

以下均为项目根目录相对入口，状态与用途分开列出。维护者接收仓库、分支和目录尚未确认；本页不提供尚不存在的 PR 链接。

| 材料 | 项目入口 | 注意事项 |
|---|---|---|
| C / TAP 候选 | `dev/snapshots/20260906-build-timing/` | 重建需同时使用 `pgvector.patch` 与新增 `049_hnsw_build_timing.pl`，后者不在 tracked patch 内 |
| ARM64 构建基线 | `dev/README.md`；`docs/2026-09-02-mac-arm64-baseline.md` | 固定 OpenTenBase / pgvector 版本和源码身份 |
| CentOS 验证 | `dev/centos/README.md`；`dev/centos/verify-timing.sh` | 用于功能兼容性，不能与 Debian 性能数据混批 |
| 工具安装与使用 | `experiments/hnsw_build/README.md` | 包含依赖、隔离构建、只读观察、GloVe 和 Recall 入口 |
| 当前正式性能 | `docs/2026-09-12-performance-method-review.md`；`experiments/hnsw_build/results/20260912T174623Z-bounded-crossover-formal/` | 使用该批固定协议、逐次记录和独立审计；历史失败不改写 |
| 当前开发边界 | `docs/2026-09-12-development-closeout.md`；`docs/2026-09-13-parallel-mechanism-results.md` | 当前产品 C 候选未应用机制定位草案；三项性能支持未建立 |

### 小规模诊断演示

先按项目 README 准备 Docker / Compose 和指定候选镜像，并核对镜像 ID。以下命令来自既有工具说明，从项目根目录运行；本次制作汇报未执行它。

```sh
python3 experiments/hnsw_build/run.py \
  --isolated --image opentenbase-pg18-pgvector:timing-v1-arm64 \
  --build-timing --rows 10000 --dimensions 32 \
  --maintenance-work-mem 1MB --parallel-workers 0 \
  --label timing-spill
```

查看输出目录的 `diagnostic.md`、`summary.json` 和 `progress.csv`。隔离模式使用新建的本次容器与数据卷，结束后清理该隔离实例。摘要中的八段内部时间与完整命令耗时分别报告；演示结果不能替代全量案例或正式性能对照。

### 观察一个已经在构建的任务

以下 service 和 PID 是待替换占位符，需预先配置非敏感 service 名称、相应数据库访问权限及可观察视图权限。密码不放入聊天、讲稿或命令行。

```sh
python3 experiments/hnsw_build/observe.py \
  --service <service名称> --pid <构建PID> \
  --output <报告目录> --interval 1 --duration 60
```

观察器只读进度、活动与等待信息，不读取构建日志。中途接入无法恢复接入前的历史；停止观察不会取消构建。任务从视图消失只表示观察结束，不能据此确定成功或取消，最终状态由构建方确认。本地 11 项实际检查的原始记录位于 `experiments/hnsw_build/results/20260912T144752Z-observe-e2e/summary.json`，尚无真实业务库试用。

## 再次验证时应固定什么

- 内存案例：同一数据、镜像、m / ef_construction 和实际 worker 数，每档重复构建；同时比较 spill、内部时间、完整命令时间与容器峰值。
- 召回案例：先按调参集选参数，再锁定索引和参数，用独立验证查询报告平均 Recall 与延迟。95% 是自设平均目标，不是项目方标准或逐查询保证。
- 性能补证：先确认门槛、估计对象、环境和执行预算，再固定新协议。当前 9 项支持、3 项未证明的结果保留，不通过删样本或不断追加样本改写。

正式交付前，仍需在最终接收目录下完成干净构建和回归。公开数据上的本地结果不能代替业务试用或生产容量规划。
