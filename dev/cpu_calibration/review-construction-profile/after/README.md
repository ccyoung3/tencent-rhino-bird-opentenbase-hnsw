# 固定工作量 CPU 微校准

内部机制诊断工具：三个 Linux 进程执行同一份固定 32 维算术工作，独立整数参考
验证 checksum；无 HNSW、数据库、随机图或网络。它不执行 5% 验收，也不为旧
HNSW 数据提供归一化系数。

首轮 short 诊断已经完成，阅读[完整结果与短测试限制](results/20260913T023309Z-5d2a069fdea1/report.md)
即可，无需为 Review 重跑。首个计算前失败也保留在 results；原始源码、编译身份、
反汇编和二进制摘要都随每次运行保存。

默认 `short` 先做唯一一次 5M/进程量级预检，再仅按耗时选择固定 20M–50M/进程，写定
协议后执行 12 次，不按波动程度追加。当前机器在 50M 上限下仍仅约 0.2 秒，
不能用这一短探测代替构建量级的执行状态控制。输出 CPU 是各进程时间之和，
整体 wall 从释放已就绪 worker 到结果收集结束；不能相加三个 elapsed 当作 wall。

新增可选 `construction` 固定为每进程 1.5B 次、1 次预热及 12 次正式探测，没有 sizing。
该数量依据既有 short 时长事先选择；新预热的时长不改变工作量、计划或准入。
总预算 300 秒含构建，每次计算命令最多 30 秒，清理另计。它只补充算术任务的时间
尺度，仍不代表 HNSW，也不会触发新的开销验收。方法页在每次运行前复制为
`source/method.md`，随源码和协议存档；结束时检查原输入、归档源码及协议摘要未变。
方法详见[预定方案](../../docs/2026-09-13-construction-duration-calibration.md)。

若另行需要重复独立诊断，在项目根目录执行以下命令；仅支持本机已经锁定的
compiler/runtime 基镜像，每次创建新结果目录并限定总执行预算 180 秒：

```bash
.venv-glove/bin/python dev/cpu_calibration/run.py
```

另行执行 construction 时需要明确选择；此工具开发与离线测试本身不会启动它：

```bash
.venv-glove/bin/python dev/cpu_calibration/run.py --profile construction
```

两个 profile 都保存计算命令前后的宿主 realtime/monotonic 纳秒读数和各自 elapsed。
只有 construction 强制执行预定的 100 ms 绝对差阈值；超出时原样保存失败并停止，
不替换样本。命令错误、checksum 不符、断电、中断或超时同样停止；`attempts` 保留
所有已尝试记录，`records` 保留已尝试的正式记录（包括失败），`warmups` 单独保存。
只有全部成功才生成正式统计。短 profile 原有选量、时限与统计语义保持不变。

C 输入仅接受非空十进制数字、范围 1–4,000,000,000；负号、正号、空白、溢出都拒绝。
construction 在计算前调用实际容器二进制验证五个非法输入均退出 2，输出归档到
`invalid-input-checks.json`；这些调用不会初始化输入、fork 或进入 calculate。

容器使用唯一 nonce、guest CPU 0–9、512 MiB 内存、无网络、只读根文件系统和
普通用户，结束后清理自身容器及匿名卷。可选 `cpu.pressure` 缺失明确记 unavailable。
创建超时后按预存 name/nonce/image 恢复身份，不能验证归属的对象保留并报错。
不修改宿主电源策略、其他容器或既有数据库。

运行后修复与 3 项离线 mock 证据见[清理恢复修复](review-timeout-cleanup/report.md)。
测试直接覆盖 main 的超时 finally 路径，不调用真实 Docker 或运行计算负载：

```bash
.venv-glove/bin/python dev/cpu_calibration/test_cleanup.py -v
.venv-glove/bin/python dev/cpu_calibration/test_profiles.py -v
```

profile 测试用 mock 验证完整成功、预热失败、正式失败、中断、超时、时钟阈值、
全样本保留和源码变更失效；不会连接 Docker。C 参数测试只编译源文件中的实际
解析函数，并运行解析器边界用例，不含距离循环或 fork。
