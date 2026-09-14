# HNSW 构建基线与诊断工具

**首次使用：[当前快速开始](../../docs/usage.md) · [效果与限制](../../docs/results.md)。**
本页是完整工具参考，保留各轮执行协议和历史镜像命令。新 clone 先准备固定源码、
构建 `review-arm64` 镜像，再运行快速开始中的隔离案例；不要直接依赖作者本机的
旧镜像标签。历史 GloVe 与开销执行器的镜像身份校验保持原样。

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

## 当前性能证据入口（2026-09-13）

性能状态仍是未全部验收。9/12新固定协议的完整对照已完成768测量+384预热，
9/12项支持低于5%，三项并行条件尚未建立支持；旧A/A结果保持原样。
见[完整结果与限制](../../docs/2026-09-12-development-closeout.md)及
[新协议](../../docs/2026-09-12-performance-method-review.md)。

后续已新增75次独立机制构建：9次预检、54次进程工作量诊断、12次原镜像/插桩
桥接。它们只用于解释波动，不并入正式验收；插桩镜像不能作为普通产品镜像使用。
见[机制结论](../../docs/2026-09-13-parallel-mechanism-results.md)和
[内部复现工具](../../dev/mechanism_diagnostic/README.md)。

## 统一环境的总成本验收（2026-09-11历史协议）

[acceptance.py](acceptance.py) 只操作自己的本地测试库，比较原版 pgvector 与诊断
关闭/开启/开启并观察三个条件。先通过 `aa` 同版本稳定性检查才能运行 `formal`；
不能把 `smoke` 或常规版功能检查当成性能验收。本轮已结束，三个完整 A/A 均未
整体通过，未启动正式对照、不继续换配置加测，详见
[协议、失败留痕与剩余项](../../docs/2026-09-11-overhead-acceptance.md)。

要求 Mac 接电、开盖；默认客体 CPU 0–3、端口 55432–55435，仅回环地址、临时密码。
端口占用即拒绝，不与其他建索引实验并发。脚本保存预登记顺序和源码归档；运行中
不得修改测量脚本。休眠/供电变化会使本轮失败，不能删除失败后把剩余样本当完整结果。
首次 Review 可先读结果，不必重新运行约数小时的全套实验。

`verify_acceptance.py` 仅做常规编译版的 16 次构建/查询/观察功能检查。
`audit_acceptance.py --checkpoint` 只能生成 `performance_pending` 留痕；只有正式对照
和 A/A 均满足全部门槛且原始证据核验通过，`--formal` 才生成验收 `passed`。
检查点可重复传入 `--aa <完整 A/A 目录>`，离线复核并保留失败筛查，而不把它改判通过。
最新收尾检查点为 `dev/snapshots/20260911-overhead-acceptance/checkpoint-after-approved-window.json`；
所有审计输出都要求新路径，不能覆盖旧检查点。
9/12复核确认窗口后的复验仍未通过；先Review测量方法，不自动再次运行相同协议。

## 已有构建任务只读观察（2026-09-10）

独立入口 [observe.py](observe.py) **不会创建、重建、取消或清理数据库对象**，
也不导入带有上述操作的实验入口。它适用于已明确授权访问的 PG18 数据库，
通过预先配置的 libpq service 连接，只读取当前数据库中指定 PID 的系统状态。
本机已验证 OpenTenBase 18.6；其他主版本直接拒绝，尚未接入真实业务实例。

先由数据库管理方配置专用账号及连接配置，确认该账号能观察目标构建会话。
本地测试账号只有连接权与 `pg_read_all_stats`，没有业务表读取权；这个预定义角色
本身能看到比本工具更多的统计信息，是否允许应由管理方决定，工具不会自行授权。
建议连接配置放在项目目录之外的个人受保护文件中，不把密码放进命令或报告。

下面只是使用示例；`opentenbase_review` 需先配置，PID 需替换成真实目标：

```bash
.venv-glove/bin/python experiments/hnsw_build/observe.py \
  --service opentenbase_review --pid 12345 \
  --interval 1 --duration 300 --output /tmp/hnsw-observation-example
```

输出目录必须尚不存在。默认 1 秒采样、60 秒上限；可选间隔 .25–60 秒、时长
.1–3600 秒。连接默认只读，每个样本单独短事务、2 秒语句超时及 .5 秒锁超时。
输出 `samples.jsonl`、`summary.json` 和 `report.md`，包含阶段、状态与等待事件；
不保存 SQL 正文、向量、密码或服务器文件内容。采样本身有成本，不能保证零影响。

遇到问题先按状态处理：连接失败时核对个人服务配置、网络与凭据；
`insufficient_visibility` 请管理方核对目标会话的可见权限，不自行提权；
`not_found` 核对数据库与 PID；`not_building` 表示当前未看到该会话正在构建。
输出有意不回显连接错误的详细文本，以免把连接信息带入报告。首次尝试可先用
下面的本地受限账号测试理解报告，再考虑已授权的实际连接。

- 中途加入不补算之前阶段；阶段百分比不是整个索引百分比，也不编造 ETA。
- “没有进展样本”不等于死锁；等待事件不是 CPU/I/O 瓶颈的充分证明。
- PID 被重用或变成另一条语句时不合并；无权限与无任务分开表示。
- 被观察任务消失后 `build_outcome=unknown`：成功和失败都可能消失。
- 停止观察只断开观察连接，不取消被观察任务。
- 另一个连接不能自动取得构建会话的 NOTICE，也不能替它事后开启内部计时。
  如用户已有本地日志，可明确添加 `--timing-log /absolute/path/build-excerpt.log`；
  只读取至多 1MiB 的片段，另存 `timing-log.json`，不自动合并或判定构建成功。
  仅 PID 相同不构成“同一次调用”的充分证据。

真实受限账号测试会**另外创建并清理自己的本地测试库**，不是生产观察命令：

```bash
.venv-glove/bin/python experiments/hnsw_build/verify_observe.py
```

已覆盖 11 项检查，包括真实 service/CLI、权限拒绝、受控锁等待、中途接入、
观察器停止后构建继续、构建取消及正常结束均不冒充观察器已确认成功。

## 有限召回改进与固定预算开销验证（2026-09-10）

本轮增加独立脚本，旧 GloVe 脚本、结果和 C 补丁保持原样。先读
[协议与当前进度](../../docs/2026-09-10-observer-recall-overhead.md)。所有实验
只使用自己的本地隔离库，端口 55432 被占用时拒绝启动，不能同时运行：

```bash
.venv-glove/bin/python experiments/hnsw_build/bounded_recall.py --smoke
.venv-glove/bin/python experiments/hnsw_build/bounded_overhead.py --smoke
```

去掉 `--smoke` 才是正式协议，并非首轮 Review 必须重跑。召回最多三个构建配置，
只在调参集未达标时推进；新验证查询与历史查询隔离，小规模测试不碰新验证集。
开销四场景各 12 个新环境块，192 次正式构建及 96 次预热；不根据结果增减次数。
分别测默认关闭、开启计时及同时只读观察的成本，5% 仅为本轮工程参考线。
样本中位比值的置信上界不等于最坏运行开销，也不是生产 SLA 保证。

### 默认关闭成本的后续定位

上述旧协议后来发现执行位置与版本/前一操作混杂：旧版每环境只有一次正式
构建，新版有三次；循环排列也未覆盖全部顺序。保留原始结果与统计，但不要
把三个比值直接解释成各项功能自身的纯因果成本。后续看
[定位留痕](../../docs/2026-09-10-default-off-triage.md)。

新增入口只操作自己的本地测试库，不是业务库观察命令：

```bash
.venv-glove/bin/python experiments/hnsw_build/triage_overhead.py --smoke
```

smoke 是30次构建、6个新环境，只验证流程。去掉 `--smoke` 是固定180次构建
（108正式、72预热）、36个环境，包含两版相同位置对照及新版全部六种排列；
耗时按本机实际负载变化，不与其他构建实验并行运行。完整协议不是首次Review
必须重跑的步骤。开始时核对镜像并归档脚本，结束后各环境独立记录清理结果。
统计单位是每场景6个配对块，不把块内三次当成18个独立样本。
比较对象是两版诊断候选，不是“全部改动相对原始pgvector”的总开销。

## GloVe 外部向量案例（2026-09-09）

新入口与本页原 synthetic 入口分开，复用构建、计时和清理逻辑。它不是已有业务
数据库的观察器：只操作自己新建的本地隔离实例。占用 55432 时直接拒绝启动。
当前只接收固定指纹的 GloVe 文件，不声称支持任意业务 HDF5 数据。

9/10 已完成两档内存各三次与同索引召回案例，先看
[正式结果与图](results/20260909T135759Z-glove-formal-cases/report.md) 和
[中文结论](../../docs/2026-09-09-glove-validation.md)。协议 passed 表示实验成功完成，
不代表检索目标已达标；本轮没有候选达到平均 Recall@10=0.95，选中参数为 null。

```bash
python3 -m venv .venv-glove
.venv-glove/bin/pip install -r experiments/hnsw_build/requirements-glove.txt
mkdir -p data/cache/glove-100-angular
curl -fL --retry 3 -o data/cache/glove-100-angular/glove-100-angular.hdf5.partial \
  https://ann-benchmarks.com/glove-100-angular.hdf5
shasum -a 256 data/cache/glove-100-angular/glove-100-angular.hdf5.partial
```

预期 SHA-256 为 `544af1d5e84e112cd4749571dcfd8ca109818a572f850af75a3a09e093a953c4`。
这是本项目对实际下载文件记录的内容指纹，不是维护方发布的签名。确认匹配且
目标文件不存在后，再将 `.partial` 文件改名为 `glove-100-angular.hdf5`；不要覆盖
已有下载。约 463MiB 的 HDF5 与虚拟环境留在本地，不进入 Git。

本轮严格使用已验证的 `timing-v1-arm64` 镜像及固定 image ID；启动时会核对。
个人仓库不包含上游 checkout，也不分发镜像，因此“新 clone 后直接启动”还需要
先按 9/6 冻结快照准备并验证运行镜像，不能仅修改 image ID 绕过校验。
本机现有镜像可直接运行：

```bash
.venv-glove/bin/python experiments/hnsw_build/glove_run.py \
  --rows 10000 --maintenance-work-mem 64MB \
  --evaluate --tuning-queries 10 --validation-queries 20 \
  --query-repetitions 1 --label glove-personal-smoke
```

全量正式协议（仅在小规模/资源预检通过后执行，非首轮阅读必做）：

```bash
.venv-glove/bin/python experiments/hnsw_build/glove_cases.py \
  --rows 1183514 --low-memory 1024MB --high-memory 1792MB
```

- 六次构建顺序 H1/L1/L2/H2/H3/L3，各次新卷；H3 的同一个索引用于召回案例。
- 每次容器 6GiB 上限、无额外 swap，2GiB 共享内存；构建超时 30 分钟。
- 宿主以临时 SCRAM 密码连接，只允许本地新实例网桥 gateway 的单一地址；密码
  不写结果文件。所有新增规则随本次临时卷清理，不影响其他项目实例。
- 全量使用提供的 Top-K 答案，抽查 SQL 精确扫描，并逐查询校验答案距离；子集
  对每个查询重算精确答案。SQL ID 为原 HDF5 行 ID + 1。
- 200 个调参 query 与 1000 个验证 query 不重叠，split seed=20260909；候选
  `10/40/100/200/400`，平均 Recall@10 参考目标 .95。验证结果不回流选参。
- 三次查询重复用于计时，不冒充三倍独立查询。每次先取结果，再执行同一查询的
  EXPLAIN ANALYZE；配置/查询/重复随机排列。p50/p95 是暖缓存服务器执行时间，
  不含网络，不代表冷缓存、业务端到端延迟或 QPS。
- 构建后的基础检查核对 EXPLAIN 计划；召回案例另执行真实查询和 EXPLAIN ANALYZE。
  共用参数结构中的 seed 不控制 GloVe 输入或 HNSW 图，输入靠内容指纹和行序固定。
  0.5s 是轮询等待设置，实际样本间隔包含查询开销，以进度 CSV 的时间戳为准。
- Recall 使用严格 ID 重合；SQL 答案抽查仅允许边界并列距离误差 2e-6。该容差
  不用于给近似检索的 Recall 加分。零向量/非有限值直接拒绝，不静默漏索引。
- `glove_report.py` 拒绝失败、重复输入及混合数据、工具、环境、实际并行度的比较。
  正式报告有全部构建重复的阶段图、查询取舍图与原始目录链接；不混入预检。

每次 `*-glove-*` 目录保存 summary、进度、构建日志、认证规则（无密码）；启用
查询时增加 `tuning/` 和 `validation/`，包含答案核验、逐条 `measurements.jsonl`
和汇总。中断保留已完成记录，未完整完成的查询集不生成通过汇总。
所有这些新证据在 ignore 规则中明确保留。方案、限制和进度见
[GloVe 留痕](../../docs/2026-09-09-glove-validation.md)。

```bash
.venv-glove/bin/python -m unittest discover -s experiments/hnsw_build -p 'test_*.py' -v
# 真实小规模成功、预期超时与主动中断；不能与其他本项目实验同时运行
.venv-glove/bin/python experiments/hnsw_build/verify_glove.py
```

不用可选依赖的系统 Python 仍能运行原测试，HDF5 专项会明确 skip；完整验收应使用
上述虚拟环境，不能把 skip 当作已覆盖。9/10 结果为 59/59 单元测试和 3/3 真实
端到端。历史 C 回归不在本轮重跑：C 输入哈希未变。

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
- 采样时间线是轮询得到的 sampled span，内部计时须单独启用；tuple 百分比按
  `tuples_done / requested rows` 计算，要求输入全非空且可索引；GloVe 入口额外拒绝零向量；
- `opentenbase_source`/`pgvector_source` 描述运行时宿主 checkout，不是所选
  Docker image 的 build-source attestation；镜像源码归属需另用 image label
  或 build manifest 证明；
- Mac、OrbStack、ARM64、容器资源和冷/暖缓存条件必须随结果一起报告。
