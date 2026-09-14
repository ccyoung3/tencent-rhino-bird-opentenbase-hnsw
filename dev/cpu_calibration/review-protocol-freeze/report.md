# 协议摘要保护的补充测试

复核确认实际 construction 批次的 source/run.py 已在 protocol.json 写定后立即计算并保存内存摘要；所有计算完成、容器清理之后，会将文件摘要与该原始摘要比较。不一致会将 summary 标为 failed。此前认为缺少这些检查的判断源于读取了较早开发版本，现已纠正。

本次没有运行代码修复。run.py 与真实批次归档、review-construction-profile 的冻结版本完全相同，SHA256 为 3f33019bf61457be3569981b32e19acbac81e9acdb0fcd59eb16d472fca1d299。只新增一个离线实际 main 测试：计算 probe 中仅向 protocol.json 追加换行，原输入、源代码、方法文件和解析后的协议内容都保持不变。测试确认既有末尾摘要检查拒绝该字节变动，原冻结 SHA 不被替换，summary=failed，13 个已尝试记录和 12 个正式记录仍全部保留，自有容器清理状态 verified。

7 项 profile/解析器测试通过；Docker 和计算 probe 全部使用 mock。解析器测试仅运行不含距离循环和 fork 的 C 参数验证函数。没有启动真实校准、HNSW 或 Docker 负载；原始批次、原协议及既有 review-construction-profile 均未修改。

before/after 的 run.py 完全相同；changes.diff 仅包含测试变化。manifest.json 与 tests.log 保存摘要和测试证据。内存冻结摘要在首次 probe 的 finally 写入磁盘 summary；本测试不声称在首次 probe 前已有磁盘 summary 摘要。
