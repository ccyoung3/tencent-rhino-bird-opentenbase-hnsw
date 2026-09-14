# 使用方法与最小复现

返回[仓库首页](../README.md) · [效果与限制](results.md) · [实现与证据索引](README.md)

## 1. 准备运行环境

已验证的运行平台是 Linux ARM64：开发机为 Apple Silicon Mac，通过 OrbStack
运行容器；CentOS Stream 9 ARM64 另有功能兼容性验证。当前 Compose 固定
`linux/arm64`。x86_64 的原生构建与性能没有在本项目中验证。

准备 Git、Python 3.11+、Docker 和 Docker Compose。最小合成数据案例只使用 Python
标准库；容器内的编译依赖由 Dockerfile 安装。首次构建会从网络下载源码与软件包。
数据库端口为本机 `127.0.0.1:55432`，同一时间只运行一个本项目示例；若端口占用，
先查明已有服务归属，不停止其他项目的数据库。

在新 clone 的项目根目录执行：

```bash
python3 dev/prepare_sources.py
python3 dev/prepare_sources.py --check

docker build --platform linux/arm64 --target runtime \
  -t opentenbase-pg18-pgvector:review-arm64 -f dev/Dockerfile .
```

脚本使用 [9/6 冻结清单](../dev/snapshots/20260906-build-timing/validated-manifest.json)
指定的 OpenTenBase 和 pgvector commit，核对补丁与新增 TAP 文件，再重建候选。
新增 `049_hnsw_build_timing.pl` 不在 tracked patch 中，脚本会单独补齐。
成功后本地生成 `.hnsw-source-provenance.json`；`--check` 只核对源码、不修改文件。

如果根目录已经有 `OpenTenBase/` 或 `pgvector/`，脚本拒绝覆盖，请使用新的 clone。
上游代码保留各自许可和版权文件；本项目补丁、工具和测试的具体入口见[索引](README.md)。

这里新构建的 `review-arm64` 镜像用于首次功能复现。历史 benchmark 的镜像 ID
与执行协议原样保留，新构建镜像的字节身份和运行耗时可能不同；不要把它改名成
历史镜像并据此宣称重现了原实验环境。

## 2. 跑一次低内存诊断

```bash
python3 experiments/hnsw_build/run.py \
  --isolated --image opentenbase-pg18-pgvector:review-arm64 \
  --build-timing --rows 10000 --dimensions 32 \
  --maintenance-work-mem 1MB --parallel-workers 0 \
  --statement-timeout-ms 180000 --label review-low
```

工具会创建本次专属的容器、数据卷和合成数据，运行 HNSW 构建，验证查询计划
使用 HNSW，再保存报告和清理隔离环境。`--statement-timeout-ms` 限制构建语句时间；
超时或中断会保留失败记录，不输出完整构建通过结论。

命令结束后会打印 `experiments/hnsw_build/results/<UTC 时间>-review-low/` 的实际路径。
打开其中的 `diagnostic.md`，按这个顺序阅读：

1. 确认运行状态与输入参数，检查是否发生内存不足后的落盘（spill）。
2. 看 **Internal build timing**：哪个实际区间占据大部分耗时。
3. 看诊断依据与建议，决定是否值得提高内存预算后复验。

完整命令耗时与八段内部耗时采用不同范围，不能混为一项；`flush` 是页面物化
阶段，不能解释为设备 fsync 延迟。短阶段可能没有被轮询采到，内部计时仍可记录。
报告不会仅凭耗时区间或等待事件就断定 CPU/I/O 根因。

| 输出 | 用途 |
|---|---|
| `diagnostic.md` | 可读诊断、阶段耗时、建议和解释边界 |
| `summary.json` | 参数、运行与清理状态、镜像身份和机器可读结果 |
| `progress.csv` | 阶段、tuple 进度、采样时间与容器内存 |
| `build.stderr.txt` | 构建日志、NOTICE 和内部计时原文 |
| `recall.csv` | 启用 Recall 时保存逐查询结果；未启用时为空表头 |

容器内存是数据库容器的近似整体用量，包含缓存，不等于 HNSW 私有内存。

## 3. 保持其他参数不变，提高内存后复验

```bash
python3 experiments/hnsw_build/run.py \
  --isolated --image opentenbase-pg18-pgvector:review-arm64 \
  --build-timing --rows 10000 --dimensions 32 \
  --maintenance-work-mem 64MB --parallel-workers 0 \
  --statement-timeout-ms 180000 --label review-high
```

并排看两份报告：落盘是否减少、构建时间怎样变化、容器峰值增加多少。
这两次小案例用于理解工具行为，每档仅一次，不作为稳定性能收益的统计证明。
若要复现会议中的 5 万条示例，两次都改为 `--rows 50000 --dimensions 64`，
低内存改成 `8MB`，高内存保持 `64MB`；运行时间依本机环境变化。

已有的手动案例原文：[8MB 报告](../presentations/hnsw-diagnostics/evidence/user-experience/manual-low/diagnostic.md)
与 [64MB 报告](../presentations/hnsw-diagnostics/evidence/user-experience/manual-high/diagnostic.md)。
它们是既有结果，不是执行上述新命令后预设应得到的时间。

`compare.py` 用于匹配参数的版本对照，会拒绝内存配置不同的输入。
内存调整的首次试用直接比较上述字段；正式多次内存对照见[效果说明](results.md)。

## 4. 在另一个终端查看实时进度

构建命令执行期间，另开终端找出本次隔离容器：

```bash
docker ps --filter 'name=hnswdiag-' --format '{{.Names}}'
```

把下面的 `本次容器名` 替换为刚刚那次运行的容器名：

```bash
docker exec -it 本次容器名 psql -U postgres -d postgres \
  -c 'SELECT pid, phase, tuples_done FROM pg_stat_progress_create_index;' \
  --watch=1
```

`Ctrl+C` 停止这条查看命令。构建命令会继续运行；构建结束并清理后，容器会消失。
最终诊断报告在构建结束后生成，这个 SQL 视图是运行中的进度入口。

## 5. 按需检查检索质量与延迟

```bash
python3 experiments/hnsw_build/run.py \
  --isolated --image opentenbase-pg18-pgvector:review-arm64 \
  --build-timing --rows 10000 --dimensions 32 \
  --maintenance-work-mem 64MB --parallel-workers 0 \
  --recall-queries 20 --recall-k 10 \
  --ef-search 40 --ef-search 100 --ef-search 200 \
  --statement-timeout-ms 180000 --label review-recall
```

工具以独立合成查询对照精确扫描结果，验证近似查询使用 HNSW。
这组 20 查询用于快速体验；完整 GloVe 独立验证结果见[效果说明](results.md)。
提高 `ef_search` 可能提高召回，也会增加延迟；这里没有指定业务合格线。

## 6. 观察已有构建任务

`observe.py` 是独立只读入口，不创建、取消或清理业务数据库对象。本地已验证
OpenTenBase 18.6 / PG18。先安装该入口需要的连接依赖：

```bash
python3 -m venv .venv-glove
.venv-glove/bin/pip install 'psycopg[binary]==3.3.3'
```

由数据库管理方配置 libpq service、连接权限和观察目标会话的统计权限，再执行
下面的示例；`your_service`、`12345`、输出路径都要按实际情况设置：

```bash
.venv-glove/bin/python experiments/hnsw_build/observe.py \
  --service your_service --pid 12345 \
  --interval 1 --duration 60 --output /tmp/hnsw-observation-example
```

输出目录必须尚不存在；凭据放在个人连接配置中。输出包括 `samples.jsonl`、
`summary.json` 和 `report.md`。中途加入不能恢复此前阶段；停止观察不会取消构建；
任务从视图消失也不能单独证明构建成功。完整行为与本地 11 项验证见
[只读观察说明](../experiments/hnsw_build/README.md#已有构建任务只读观察2026-09-10)。

## 7. 测试与深入复现

本页三个小案例和源码重建步骤已通过[独立目录复现](../dev/validation/20260914-repository/README.md)。
本轮复现使用 Python 3.14.7；发行版与历史测试分别报告。

以下离线测试不启动数据库；GloVe 测试需要完整可选依赖，缺少时会明确 skip：

```bash
python3 -m unittest discover -s experiments/hnsw_build -p 'test_*.py' -v
```

如需全部 Python 测试，使用 `experiments/hnsw_build/requirements-glove.txt` 安装冻结依赖。
C 专项回归可从同一批已准备源码构建测试镜像：

```bash
docker build --platform linux/arm64 --target test \
  -t opentenbase-pg18-pgvector:review-test-arm64 -f dev/Dockerfile .
docker run --rm --entrypoint make opentenbase-pg18-pgvector:review-test-arm64 \
  prove_installcheck PROVE_TESTS=test/t/049_hnsw_build_timing.pl
```

旧 GloVe / 开销执行器固定了当时镜像 ID 和有界协议，用于追查历史实验，不是新
镜像的通用一键入口。首次评审可核对已有报告、配置、原始记录及分析方法；在新环境
重新运行正式实验时，应另记镜像、环境与完整新批次，不改旧脚本的锁定值冒充同批复验。

更多历史协议与命令见[工具参考](../experiments/hnsw_build/README.md)。
