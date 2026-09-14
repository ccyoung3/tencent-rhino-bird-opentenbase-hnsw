# 诊断开销验收

流程状态：completed

正式协议比较整套诊断相对原版pgvector；A/A只检查测量稳定性。

| workers | spill | 条件 | 配对中位变化 | 单侧上界变化 | 判断 |
|---:|---|---|---:|---:|---|
| 0 | False | aa_b | -4.28% | +9.00% | not_established |
| 0 | True | aa_b | +2.78% | +37.81% | not_established |
| 2 | False | aa_b | +5.47% | +16.90% | not_established |
| 2 | True | aa_b | +8.07% | +30.80% | not_established |

- 正式12项采用Bonferroni控制单侧家族误差率≤5%，假定各配对面板独立；参考线5%。
- 置信上界针对配对比值总体中位数，不是最坏单次开销或生产SLA。A/A不属于这项正式保证。
- seed42为受控测试编译，固定串行随机数；并行拓扑仍可能变化。常规编译另外验功能。
- 每个面板新建实例，每个条件相同次数预热/正式构建，每次构建新连接且先CHECKPOINT。
- 仅使用本地测试实例，Linux客体CPU亲和性不是Mac物理核心独占；不保证所有宿主负载条件。
- 原始异常和失败保留，not_established不能改写为通过。
