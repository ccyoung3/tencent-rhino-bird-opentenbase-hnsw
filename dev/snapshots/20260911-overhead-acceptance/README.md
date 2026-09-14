# 9/11 总成本验收检查点

本轮源码候选仍是 9/6 的 C/TAP；新增统一编译与公平开销验收工具，不推送、不修改上游。
完整说明：`docs/2026-09-11-overhead-acceptance.md`。

- `build-manifest.json`：同一编译器与运行时的原版/候选 × seed42/normal 四个镜像，构建通过。
- `build-start.json` 与根目录首次构建日志：首次 FROM 引用错误留痕，不覆盖。
- `build-attempt-2/`：实际成功的构建输入、日志、逐源文件及二进制指纹。
- `environment-during-aa.json`：A/A 期间某时刻的 Mac M4、内存、AC 电源与无告警状态，
  不是整个实验从未变化的证明；后来实际合盖休眠，A/A 中断。
- `environment-at-checkpoint.json`：阶段收尾时的环境状态。
- `checkpoint.json`：常规版 16 构建/20 检查的离线核查、98 项测试、旧 639 文件保护、
  当前文件指纹与测试实例/卷清理核查。状态为 **performance_pending**，不是最终性能通过。
- `environment-at-final-screen.json`：最后一项校准收尾之后的环境状态，不是全程证明。
- `checkpoint-after-final-screen.json`：新建收尾审计，保留两次完整 A/A 的离线复算
  及未通过结果（3/4、0/4场景通过），再验常规功能证据、98项工具测试、旧证据与C候选
  身份和清理。`formal=null`、状态仍为 **performance_pending**，不冒充验收通过。
- `environment-20260911T1119Z-approved-window.json`：用户确认窗口后的启动前点时状态。
- `environment-20260912-review.json`：次日复核时的点时状态；此时电池供电，不解释昨天测量。
- `checkpoint-after-approved-window.json`：9/12新增审计，含第三个完整但未通过的A/A，
  复核常规功能、98项测试和清理；仍为 **performance_pending**，两个旧检查点不覆盖。

所有 `*-bounded-acceptance-*` 目录（含失败）都保留在实验结果下。19:06的校准与
19:43结束的确认窗口复验均完整但未通过，正式24面板新旧对照未启动。
本轮停止继续加测，不改5%线、不拼接残缺结果。先Review测量方法，不反复请求空闲
窗口，不擅自停止其他程序。旧检查点保持原样。
