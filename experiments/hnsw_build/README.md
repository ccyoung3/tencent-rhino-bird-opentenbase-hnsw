# HNSW 构建基线与诊断工具

这个工具在现有 Mac `linux/arm64` Compose 环境中自动完成：

1. 生成带固定 SQL 随机种子的向量数据；
2. 异步执行 `CREATE INDEX ... USING hnsw`；
3. 轮询 `pg_stat_progress_create_index`；
4. 采集容器级 `memory.current`；
5. 验证查询计划确实使用 HNSW；
6. 保存参数、版本、耗时、大小、NOTICE、进度 CSV、JSON 摘要与可读诊断报告。

按需启用 Recall@K 后，还会生成固定种子的独立 synthetic holdout 查询，以精确
顺序扫描作为 ground truth，验证近似查询确实使用 HNSW，并记录服务器侧查询
执行时间。该功能默认关闭，不影响已有构建实验。

它用于功能诊断和同一台机器上的相对对比，不用于宣称生产服务器绝对性能。

## 轻量冒烟

从项目根目录执行：

```bash
python3 experiments/hnsw_build/run.py \
  --rows 2000 \
  --dimensions 8 \
  --maintenance-work-mem 64MB \
  --parallel-workers 0 \
  --label smoke \
  --stop-after
```

`--image` 可选择不可变的基线/修改版镜像；结果同时记录实际 image ID。例如：

```bash
python3 experiments/hnsw_build/run.py \
  --image opentenbase-pg18-pgvector:baseline-0.8.6-arm64 \
  --rows 50000 --dimensions 64 \
  --maintenance-work-mem 8MB \
  --label baseline-serial-disk \
  --stop-after
```

正式对照应再加 `--isolated`。它为单次运行创建唯一的 Compose project 和
全新数据卷，并在证据写入后只删除该临时 project 的容器与数据卷，避免 WAL、
checkpoint 和历史页面状态污染下一次实验。默认命名卷不会被触碰：

```bash
python3 experiments/hnsw_build/run.py \
  --isolated \
  --image opentenbase-pg18-pgvector:baseline-0.8.6-arm64 \
  --rows 50000 --dimensions 64 \
  --maintenance-work-mem 8MB \
  --label isolated-baseline-disk
```

## 建议的首轮对照

先固定除内存外的全部变量，分别运行内存内和低内存构建：

```bash
python3 experiments/hnsw_build/run.py \
  --rows 100000 --dimensions 64 \
  --maintenance-work-mem 256MB \
  --m 16 --ef-construction 64 \
  --parallel-workers 0 \
  --label serial-memory

python3 experiments/hnsw_build/run.py \
  --rows 100000 --dimensions 64 \
  --maintenance-work-mem 8MB \
  --m 16 --ef-construction 64 \
  --parallel-workers 0 \
  --label serial-disk \
  --stop-after
```

并行路径应作为第二组对照，保持相同数据与参数，只改变
`--parallel-workers`。正式结果每个配置至少重复三次；首次运行仅用于验证规模和
耗时是否适合本机。

## Recall@K 与参数诊断

下面的示例把 `0.95` 明确作为本次运行的实验目标；它不是项目方或 pgvector 的
通用阈值：

```bash
python3 experiments/hnsw_build/run.py \
  --isolated \
  --image opentenbase-pg18-pgvector:diagnostics-v2-seed42-arm64 \
  --rows 50000 --dimensions 64 \
  --maintenance-work-mem 256MB \
  --m 16 --ef-construction 64 \
  --recall-queries 30 --recall-k 10 \
  --ef-search 40 --ef-search 80 --ef-search 160 --ef-search 320 \
  --minimum-mean-recall 0.95 \
  --query-seed 20260903 \
  --label params-m16-efc64
```

精确结果禁用 HNSW/index scan，近似结果禁用 seq scan；工具会逐查询验证计划，
而不是仅比较两组未确认来源的 ID。查询计时取 PostgreSQL
`EXPLAIN ANALYZE` 的 `Execution Time`。

SQL `setseed()` 只固定数据生成，不会固定 pgvector 使用的
`pg_global_prng_state`。需要测量补丁本身的微小开销时，可为 baseline 与
candidate 同时用 `--build-arg PGVECTOR_CPPFLAGS=-DHNSW_MEMORY` 构建专用
benchmark 镜像；该宏会把串行 HNSW 构建 seed 固定为 42。此类镜像只用于
受控对照，不作为正常功能交付镜像。

## 输出

每次运行在 `results/<UTC 时间>-<label>/` 下生成：

| 文件 | 内容 |
|---|---|
| `summary.json` | 工作负载、固定参数、版本、架构、耗时、内存、表/索引大小、阶段与当前工具哈希 |
| `progress.csv` | 每次采样看到的 phase、block/tuple 进度、tuple 百分比和容器内存 |
| `recall.csv` | 可选 Recall@K 的逐查询精确/近似邻居与服务器执行时间；未启用时只有表头 |
| `diagnostic.md` | 阶段采样跨度、进度区间、spill 上下文、建议与解释边界 |
| `build.stdout.txt` | `psql` 标准输出 |
| `build.stderr.txt` | NOTICE、WARNING 或构建错误 |

默认在记录元数据后删除实验 schema，以免连续实验占满磁盘；使用
`--keep-data` 可保留。`--stop-after` 会停止容器，但保留 Compose 命名卷。
`--isolated` 则始终清理本次运行专属的临时卷，因此不要和 `--keep-data` 组合。

## 内部阶段计时（2026-09-06 候选）

新候选支持默认关闭的会话设置 `hnsw.build_timing`。工具通过 `--build-timing`
启用并要求收到有效摘要；旧镜像缺少摘要时会明确失败，不静默退回采样计时。

```bash
python3 experiments/hnsw_build/run.py \
  --isolated --image opentenbase-pg18-pgvector:timing-v1-arm64 \
  --build-timing --rows 10000 --dimensions 32 \
  --maintenance-work-mem 1MB --parallel-workers 0 \
  --label timing-spill
```

`summary.json` 的 `internal_timing` 与 `diagnostic.md` 的内部计时表分别保存
setup、memory_build、spill_drain、flush、disk_insert、finalize、wal、cleanup。
未发生的落盘/等待/WAL 阶段是 null / N/A；它们不是耗时 0，也不是采样漏掉。
各阶段采用同一起点的微秒边界，不重复计算并行 worker 时间。

口径限定为一次 HNSW 内部构建调用，不包括完整 SQL 命令的所有阶段、事务提交
或摘要自身的输出耗时。内存阶段含扫描/worker 启动；排空等待含尚在执行的内存
插入与协调；落盘阶段含剩余扫描与等待；flush 是页面物化，不是存储设备 fsync
耗时。报告识别最大的实际时间区间，不据此直接判定 CPU/I/O 瓶颈。

`--statement-timeout-ms 100` 可用于有意取消测试。命令失败、用户中断、摘要缺失、
重复、损坏、时间倒退或覆盖不完整都不能作为完整计时通过；报告保留失败证据，
不生成瓶颈建议。工具中断时只取消本次命名的构建后端，再清理本次隔离环境；
清理动作的结果另记在 `summary.json.cleanup`。

真实端到端验证及小规模三次重复开销筛查：

```bash
python3 dev/verify_build_timing.py
python3 dev/benchmark_build_timing.py
python3 -m unittest discover -s experiments/hnsw_build -p 'test_*.py' -v
```

开销脚本轮换旧候选关闭、新候选关闭、新候选开启三种顺序，覆盖串行/并行与
低/高内存，总计 36 次；需先停止其他重负载实验。HNSW_MEMORY 只固定串行拓扑，
并行仍受调度影响。该轻量筛查不是统计等价证明，不能据此宣称绝对“零开销”。

至少三次匹配实验完成后，可汇总中位数、范围、内存增量、索引大小、spill
次数和阶段覆盖：

```bash
python3 experiments/hnsw_build/compare.py \
  --baseline results/<baseline-1> \
  --baseline results/<baseline-2> \
  --baseline results/<baseline-3> \
  --candidate results/<candidate-1> \
  --candidate results/<candidate-2> \
  --candidate results/<candidate-3> \
  --output results/comparison.json
```

工具自身的纯本地单元测试不需要启动容器：

```bash
python3 -m unittest -v experiments/hnsw_build/test_tools.py
python3 -m unittest -v experiments/hnsw_build/test_recall.py
python3 -m unittest -v experiments/hnsw_build/test_summarize_sweep.py
```

如果构建快到没有采集到任何进度样本，阶段单调性会记录为 `null`（未知），
不会把“没有证据”误记为 `true`。

## 测量限制

- `memory.current` 是整个数据库容器的内存，不是 HNSW 私有内存；报告时应使用
  初始值、峰值和增量，并称为近似值；
- 当前 pgvector 并行构建会预留 1MiB allocation safety margin，spill 条件是
  `memoryUsed + margin >= memoryTotal`；工具在诊断报告中解释这一点，避免把
  “used 低于 nominal limit”误判为日志矛盾；
- 轮询会产生轻微开销，因此只比较采样间隔相同的实验；
- 很快的构建可能在第一次轮询前结束，导致进度样本为零；
- 采样时间线是轮询得到的 sampled span，内部计时须单独启用；tuple 百分比只对本工具
  生成的全非空数据按 `tuples_done / requested rows` 计算；
- `opentenbase_source`/`pgvector_source` 描述运行时宿主 checkout，不是所选
  Docker image 的 build-source attestation；镜像源码归属需另用 image label
  或 build manifest 证明；
- Mac、OrbStack、ARM64、容器资源和冷/暖缓存条件必须随结果一起报告。
