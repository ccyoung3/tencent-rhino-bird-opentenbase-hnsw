---
title: OpenTenBase 9 月 14 日交付倒排计划
status: 进行中
date: 2026-09-02
updated: 2026-09-08
deadline: 2026-09-14
tags: [opentenbase, deadline, delivery, plan]
---

# OpenTenBase 9 月 14 日交付倒排计划

## 已核实期限

- 启动 PPT 只写了第一周、每周、每双周的推进节奏，没有显示具体截止日；
- 会议逐字稿 `00:15:35` 处明确说“时间是到 9 月 14 号”以及“9 月 14 号
  就要提交结果”；
- 腾讯高校合作发布页也将 2026 年活动时间写为 `6 月 18 日—9 月 14 日`：
  <https://ur.tencent.com/article/1529>；
- 材料没有说明 9 月 14 日当天的具体提交时刻、提交入口或最终答辩日期。

因此把 `2026-09-14` 视为硬截止，并把 `2026-09-12` 设为本地交付候选冻结日，
给格式确认和意外问题预留两天。

## 工作原则

```text
本地实现完整功能
→ 本地自动化测试
→ 固定环境复现实验
→ 完成说明与结果
→ 最后整理代码交付
```

负责人暂未回复不阻塞本地开发。实现保持在独立 pgvector 分支中，并持续针对
OpenTenBase PG18 构建；最终无论要求外置扩展还是移入 `contrib/pgvector`，都能
转换交付形式。

## 9 月 2 日实际进展

技术候选比原倒排提前形成，但项目仍保持“进行中”，因为尚未完成独立 Review
和正式交付：

- 代码：4 个 HNSW 构建阶段、并行 leader/worker 同步、spill DETAIL；
- 工具：隔离 Compose project/volume 的构建实验脚本与结果比较器；
- 测试：27 个 HNSW TAP 文件共 411 个断言、4 项 SQL regression、最终专项
  TAP 5/5、实验工具单元测试 7/7，全部通过；
- 诊断输出：自动生成阶段 sampled span、tuple 进度区间、spill 上下文、调参
  建议与解释边界；
- 实验：串行全内存、串行 spill、2-worker spill 的功能验证；固定 HNSW seed、
  每组 3 次的 baseline/candidate 对照未见可分辨回归；
- 文档：[[2026-09-02-local-implementation-evaluation]] 与
  [[../experiments/hnsw_build/results/README|HNSW 实验证据索引]]；
- 远端状态：没有 commit、push 或 PR，等待最后交付阶段。

`2026-09-12` 仍作为正式交付候选冻结日：在此之前完成代码 Review、归属确认
和交付形态适配，而不是继续扩张功能。

## 9 月 3 日兼容性补充

切换环境前已冻结实际 binary patch、源码身份、镜像 ID 与采用中证据校验和。
同一补丁随后在 OrbStack CentOS Stream 9 原生 ARM64 Machine 中完成：

- OpenTenBase 18.6 out-of-tree clean build/install；
- pgvector clean build + `-Werror` 与动态链接检查；
- 专项低内存 TAP 5/5、4 项 HNSW SQL regression 4/4；
- 最小 HNSW smoke 与全部 HNSW TAP 27 文件、411 断言、0 skip；
- 最终 diff SHA 复核和数据库进程清理。

该轮只补项目方常用发行版的兼容性证据，不重跑正式性能对照。原始证据与复现
步骤见 [[2026-09-03-centos-stream9-arm64-compatibility]]。项目状态不变：独立
代码 Review、交付归属确认和正式提交仍未完成。

## 9 月 3 日需求复核与续作启动

重新逐页核对启动 PPT 和谢灿扬发言后，确认当前候选完整覆盖的是“构建慢、
低内存 spill 与进度观测”闭环，而不是项目二全部子项。低召回风险、完整参数
建议、内存规模关系、异常场景证据和较大规模验证继续按优先级补齐；当前 C 补丁
保持冻结，先从独立 Recall@K/参数诊断工具开始，避免扰动已通过的 27/411 回归。

详细状态、范围解释和逐项验收见
[[2026-09-03-requirements-progress-audit|项目二需求复核与续作留痕]]。

## 9 月 3 日续作完成情况

冻结 C diff 后，独立实验层已经完成 Recall@K/服务器侧查询计时、50k×64 固定
topology 参数矩阵、行数/维度/`m` 内存规模关系、异常证据矩阵和逐级 1M×64
实跑。参数实验 14 次、统一 0.2 秒采样的 scale 实验 10 次全部通过；工具单元
测试 28/28。

因此技术侧剩余项不再是“补功能”，而是负责人/维护者人类 Review 与交付治理：
确认代码归属/入口后，按目标形态做最终 clean rebuild，再由用户决定 commit、
push 或 PR。公开标准数据集可作为增强外部有效性的补充，不是项目二硬性阻塞项。

## 9 月 4 日冻结快照审查

统一采样补跑、工具 provenance、协议一致性与并行 safety margin 解释已经补齐；
AI 只读交叉审查未发现 P0/P1，但不能替代负责人或维护者的人类 Review。当前
不再扩张实验范围，下一动作仍是确认接收目录/提交入口，然后按目标形态做一次
clean rebuild。

## 9 月 8 日个人 GitHub 仓库

已在用户账号下创建私有仓库
<https://github.com/ccyoung3/tencent-rhino-bird-opentenbase-hnsw>，仅承载腾讯犀牛鸟
OpenTenBase 项目的本地化资产。该仓库不采用 GitHub fork 关系，不修改
OpenTenBase/pgvector 两个上游 checkout 的远端，也不创建上游 PR。会议音频、
逐字稿、启动 PDF 和完整上游源码不上传；代码候选以补丁、测试、工具、文档和
验证证据的形式保留。提交作者与提交者使用用户本人的 Git 身份，不引入 AI/Codex
contributor。是否向 OpenTenBase 提交，仍须用户 Review 确认后另行授权。

## 原定 12 天倒排

| 日期 | 里程碑 | 验收证据 |
|---|---|---|
| 9 月 2 日 | 固定 PG18/pgvector 版本，跑通 Mac ARM64 环境 | 编译、启动、HNSW 冒烟记录 |
| 9 月 3—4 日 | 建立未修改版本的可复现实验基线 | 参数清单、进度采样、耗时/内存/索引大小 |
| 9 月 5—7 日 | 实现 HNSW 构建阶段与诊断上下文补丁 | 本地 diff、编译通过、低内存路径可见 |
| 9 月 8—9 日 | 补 TAP/回归测试，覆盖串行与并行路径 | 自动测试结果、失败路径断言 |
| 9 月 10—11 日 | 运行前后对照并写参数调优说明 | 结果表、限制、复现命令 |
| 9 月 12 日 | 冻结本地交付候选 | 代码、测试、工具、报告四件套齐全 |
| 9 月 13 日 | 缓冲与交付格式适配 | clean rebuild、最终检查 |
| 9 月 14 日 | 提交结果 | 提交记录或负责人确认 |

## 最小完整交付

1. 一项聚焦的 HNSW 构建诊断代码改进；
2. 一个可直接运行的诊断/基线工具；
3. TAP 或回归测试；
4. 优化前后或功能前后的可验证对照；
5. 环境、数据规模、参数、运行次数、统计口径与限制；
6. 参数调整建议，以及验证建议是否有效的方法。

六项均已有本地证据。第六项现在同时覆盖：spill 时的
`maintenance_work_mem` 条件式建议，以及低召回时先调 `ef_search`、再评估
`ef_construction` 和 `m` 的复验顺序；不把单台 Mac、synthetic 数据或本轮
`0.95` 目标推广到生产环境。

## 交付前清单

1. 独立检查源码并发语义、错误路径与代码风格；
2. 请负责人确认外置 pgvector / OpenTenBase 内置目录、提交入口和精确时刻；
3. 按目标目录做 clean rebuild、专项 TAP 和 HNSW regression；
4. 冻结 diff 与结果索引，形成一页式项目说明；
5. 用户明确开始交付后再创建 commit、push 或 PR。

## 范围冻结

主线只做 HNSW 构建诊断。IVFFlat、新量化算法、DiskANN、分布式构建、LLM
诊断助手和通用内存预测模型都不进入本次 12 天交付。

## 对 90 天 Sprint 的影响

原 Sprint 中“项目 / GitHub / 求职”只有每周 3 小时，无法独立容纳这次硬截止。
9 月 2—14 日将本项目同时视为科研主线与项目资产，优先复用同一份代码、实验和
报告，不另开第二个向量数据库任务。若需要人工投入超过原 3 小时配额，应在当周
复盘中如实记录并压缩低优先级技术练习，不能虚增总时长或挤掉英语与既有科研责任。
