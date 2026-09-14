# 固定预算开销验证

流程状态：passed

三个来源分开比较。5% 是本轮工程参考线，不是官方标准；不是证明零开销。

| worker | spill | 对比来源 | 配对数 | 中位变化 | 中位比值的单侧上界 | 采到进度的观察次数 | 低于5%的证据 |
|---:|---|---|---:|---:|---:|---:|---|
| 0 | False | dormant_timing | 12 | +0.66% | +24.13% | None | not_established |
| 0 | False | enabled_timing | 12 | -0.11% | +9.34% | None | not_established |
| 0 | False | observer | 12 | -0.89% | +5.38% | 12 | not_established |
| 0 | True | dormant_timing | 12 | +8.04% | +10.85% | None | not_established |
| 0 | True | enabled_timing | 12 | -4.71% | -0.04% | None | supported_below_reference |
| 0 | True | observer | 12 | +0.95% | +4.43% | 12 | supported_below_reference |
| 2 | False | dormant_timing | 12 | +25.05% | +52.74% | None | not_established |
| 2 | False | enabled_timing | 12 | -3.31% | +21.02% | None | not_established |
| 2 | False | observer | 12 | +3.66% | +16.29% | 12 | not_established |
| 2 | True | dormant_timing | 12 | +10.11% | +13.60% | None | not_established |
| 2 | True | enabled_timing | 12 | -5.72% | +0.39% | None | supported_below_reference |
| 2 | True | observer | 12 | +1.13% | +4.30% | 12 | supported_below_reference |

- dormant_timing：新版关闭/旧版关闭；enabled_timing：新版开启/关闭；observer：开启并观察/仅开启。
- 主计时为客户端等待完整 SQL 调用完成的经过时间，含消息处理与本地往返，不使用内部计时测自身成本。
- 每场景12个独立新环境块，每镜像块预热一次；正式4条件，全部重复与失败保留。
- 单侧上界针对配对比值的总体中位数，假定各块独立；12对的实际覆盖率约98.1%，不是每次运行的最大开销。
- 宿主仍可能存在相关负载，样本与并行拓扑有波动；不把本机结果推广到生产。
- supported_below_reference 仅支持对应场景；not_established 表示不能证明低于门限，不自动认定一定有回归。
- 所有比较是逐场景判定，不给出跨12项比较的联合置信保证。观察器连接准备时间在建索引计时外。
- insufficient_observation_coverage 表示至少一次未采到构建阶段；即便耗时很小，也不支持完整观察的开销结论。
- smoke 仅每场景1块；上述12块统计要求只适用于正式实验。
