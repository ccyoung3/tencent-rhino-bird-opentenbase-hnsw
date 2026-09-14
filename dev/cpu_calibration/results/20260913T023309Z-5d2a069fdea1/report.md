# 固定工作量 CPU 微校准（探索性）

2026-09-13，北京时间 10:33:09–10:33:14；12 个固定 probe 全部完成。每个 probe 三个进程各执行 50,000,000 次 32 维 L2 风格计算，共 36 个进程记录；每个进程 checksum 均为 `86303660579`，与独立整数参考一致。

仅一次 5M/进程 sizing 的 outer wall 为 0.02120388 秒。预先规定按时长推算、限制在 20M–50M，得到正式 50M。正式时长仍只有 0.191527220–0.310739095 秒，低于原建议 1–3 秒；这是本轮的实际限制，未再调整工作量或追加 probe。

| Probe | Outer wall（秒） | 三进程 CPU 合计（秒） |
| ---: | ---: | ---: |
| 1 | 0.191527220 | 0.570818 |
| 2 | 0.212183182 | 0.618884 |
| 3 | 0.211226219 | 0.622211 |
| 4 | 0.310739095 | 0.911764 |
| 5 | 0.214140773 | 0.636849 |
| 6 | 0.205077027 | 0.604946 |
| 7 | 0.222416142 | 0.649845 |
| 8 | 0.212082764 | 0.628247 |
| 9 | 0.226519825 | 0.664735 |
| 10 | 0.222724101 | 0.649591 |
| 11 | 0.215299783 | 0.635970 |
| 12 | 0.197213710 | 0.581809 |

全部 12 个值保留。Outer wall 的 max/min 为 1.622427846026，中位数为 0.213161977 秒；三进程 CPU 合计的 max/min 为 1.597293708327，中位数为 0.6321085 秒。

第 4 个 probe 的三个进程 CPU 分别为 0.298488、0.304800、0.308476 秒；第 1 个为 0.190746、0.189986、0.190086 秒。同一二进制、输入、循环次数与校验和下，固定算术工作依然观察到 CPU 计时和 wall 的变化，说明此类变化可以在没有 HNSW 随机图或图锁的任务中出现。它不能证明旧 HNSW 某次波动的原因，不能把变化归因于硬件频率，也不能用来归一化旧性能结果。

计时范围：每进程 getrusage 与 CLOCK_MONOTONIC 围住固定循环；进程创建、输入初始化和整数参考在范围外。Outer wall 从释放两个已就绪 worker 起，直到 leader 计算结束、收集 worker 结果并 wait 完成，包含少量同步和回收开销。核函数使用固定 1024 对向量，数据约 256 KiB；它不代表 HNSW 的内存、缓存、锁、扫描或最终 flush 行为。较短 probe 对瞬时调度与环境变化更敏感。

环境：锁定的 compiler/runtime 基镜像已在构建前后校验；gcc 12.2.0，沿用 -O2 -march=native -ftree-vectorize -fassociative-math -fno-signed-zeros -fno-trapping-math。反汇编中 calculate 的循环保留每次 distance32 调用，distance32 使用 16 字节 SIMD，未发现循环被提升或消除。输入/循环没有 RNG，没有逐次 volatile 存储。

运行容器是任务自有 nonce 容器，network=none、只读根文件系统、postgres 用户、capabilities 全去除、no-new-privileges、Linux guest CPU 0–9、512 MiB 内存。26 个 sizing/formal 前后边界均为 AC，cpu.max=max、cpu throttling 计数与 memory.events 均为零，无 major fault。cpu.pressure 在该 guest 不提供，按 unavailable 保留。CPU affinity 是 guest 约束，不能据此声称独占宿主核；其他容器和宿主设置均未改动。

首个 attempt 在任何计算前因 cpu.pressure 缺失中止。原始记录完整保留；只修改采集器对可选文件缺失和清理输出大小写的处理后，在独立目录执行本轮。两次编译的 C 和二进制 SHA256 相同。首个容器实际 rm -f -v 成功，但原工具将小写 not-found 错判为 cleanup failed；后续只读补证确认该容器与其匿名卷均不存在。第二个容器及匿名卷清理已在本轮命令日志中明确验证。

这是固定工作量的探索性诊断，不是 5% 性能验收。没有 p 值、没有丢弃第 4 个 probe、没有补跑，也不提供候选版本性能通过结论。

C SHA256: `d4acc2836325f114841204c313fd1c503dfb026004a6dce3dfe9df933adf206e`
Binary SHA256: `f98e7d5e0174a84c3152d6521b82b98ae19595cadf7ecce7719e2a6296eb1eb2`
Summary SHA256: `5cd65d579bf9665052ee5ce16880ddae4c64c455ed239a04c40e6a5b0f71dcba`
Protocol SHA256: `152350bbbb4f3ca9bfbad9db23733b88f568478edb5c8a21c23ff4d9fb92d427`

原始命令、stdout/stderr、每进程计数、CPU/wall、资源边界、镜像、容器和卷身份见本目录 JSON；源代码和反汇编见 source/ 与 binary/。完整值见 summary.json；独立整数核对与产物摘要见 artifact-audit.json。

工具复用限制：本轮 create/start 均已成功并存证。若未来 docker create 已在 daemon 端成功但客户端超时，当前 runner 尚无按预存 name/nonce 恢复 container ID 的通用逻辑；不得将本轮成功清理等同于该未触发失败路径已验证。
