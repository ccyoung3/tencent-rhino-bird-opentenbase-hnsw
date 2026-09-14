# 固定预算开销验证

流程状态：passed

三个来源分开比较。5% 是本轮工程参考线，不是官方标准；不是证明零开销。

| worker | spill | 对比来源 | 配对数 | 中位变化 | 中位比值的单侧上界 | 低于5%的证据 |
|---:|---|---|---:|---:|---:|---|
| 0 | False | dormant_timing | 1 | +8.16% | 无有限上界 | not_established |
| 0 | False | enabled_timing | 1 | -12.52% | 无有限上界 | not_established |
| 0 | False | observer | 1 | +2.61% | 无有限上界 | not_established |
| 0 | True | dormant_timing | 1 | +0.25% | 无有限上界 | not_established |
| 0 | True | enabled_timing | 1 | -1.13% | 无有限上界 | not_established |
| 0 | True | observer | 1 | +0.77% | 无有限上界 | not_established |
| 2 | False | dormant_timing | 1 | +1.54% | 无有限上界 | not_established |
| 2 | False | enabled_timing | 1 | +5.46% | 无有限上界 | not_established |
| 2 | False | observer | 1 | -6.96% | 无有限上界 | not_established |
| 2 | True | dormant_timing | 1 | +0.19% | 无有限上界 | not_established |
| 2 | True | enabled_timing | 1 | +7.70% | 无有限上界 | not_established |
| 2 | True | observer | 1 | -3.29% | 无有限上界 | not_established |

- dormant_timing：新版关闭/旧版关闭；enabled_timing：新版开启/关闭；observer：开启并观察/仅开启。
- 主计时为客户端等待完整 SQL 调用完成的经过时间，含消息处理与本地往返，不使用内部计时测自身成本。
- 每场景12个独立新环境块，每镜像块预热一次；正式4条件，全部重复与失败保留。
- 单侧上界针对配对比值的总体中位数，假定各块独立；12对的实际覆盖率约98.1%，不是每次运行的最大开销。
- 宿主仍可能存在相关负载，样本与并行拓扑有波动；不把本机结果推广到生产。
- supported_below_reference 仅支持对应场景；not_established 表示不能证明低于门限，不自动认定一定有回归。
- 所有比较是逐场景判定，不给出跨12项比较的联合置信保证。观察器连接准备时间在建索引计时外。
