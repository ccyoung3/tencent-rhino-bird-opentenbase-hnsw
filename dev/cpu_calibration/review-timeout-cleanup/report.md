# create 超时后的身份恢复修复

运行后的独立审查发现：若 Docker daemon 已创建容器，但 create 客户端超时未返回 ID，原 runner 的 finally 会因 container 仍为 None 而跳过清理。该路径未在本轮真实校准中触发；本轮两容器和匿名卷均已确认不存在。

当前 run.py 已在 create 前落盘唯一 name、nonce 与锁定 image ID，并在 finally 对该唯一 name 做只读 inspect。只有 name、nonce、image ID、64 位十六进制 container ID 全部符合才恢复并清理；身份不符或存在性不能明确判断时保留对象并报告失败。明确 not-found 才记为 absent。不会搜索其他容器。

3 项离线 mock 测试通过，均覆盖 main 的实际 create 抛出 TimeoutExpired 后 finally 分支：已创建自有对象成功恢复并删除；对象不属于本任务时无删除；对象明确不存在时无删除。此外核验 image/name/nonce/ID/多对象异常和 daemon 不可达不被当作不存在。测试禁止真实 subprocess，未启动任何 CPU probe 或 Docker 负载。

run-before.py 与已完成校准的 source/run.py 摘要一致；run-after.py、run.diff、tests.txt 与 manifest.json 保存修复和证据。旧校准源码、二进制、协议、12 个结果全部保持不变。本修复取代旧校准 report.md 最后一段中针对“工具复用限制”的描述；不改变任何测量结论。
