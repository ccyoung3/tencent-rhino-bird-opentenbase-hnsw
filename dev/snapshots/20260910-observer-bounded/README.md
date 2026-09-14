# 2026-09-10 只读观察与有限验证快照

这是 9/10 GloVe 轮次之后的独立增量，不覆盖之前的快照或原始结果。
C/TAP 与 9/6 候选相同；没有重跑历史 632 个断言，也没有 Git 提交或远端写入。

## 开跑身份

- `start-manifest.json` 与 `tooling-at-start.tar.gz`：正式召回前记录的完整工具、
  单元测试和预先约定的协议。`python-tests.log` 为 78/78、0 skip。
- `help-amendment.json` 与 `overhead-help-amendment.tar.gz`：正式召回已经开始、
  正式开销尚未开始时发现系统 Python 缺少可选依赖会导致 `--help` 失败。
  唯一修改是将开销入口中的 psycopg 导入移到参数解析之后；记录器逐字核对
  仅这一处搬移，没有改测量逻辑。原始快照不重写。
- 正式目录的 `protocol.json` 记录各自真正运行的工具哈希。当前文档会随着结果
  更新；归档内是开跑时协议，不能把当前说明与归档时点混为一谈。

## 离线复核

`audit.py` 不启动数据库、不重跑索引、不修改 Git。完成正式实验后，指定三份
结果目录，独立反算逐查询 Recall、分位数、配对开销比值与置信上界，并检查
选择顺序、新验证集不泄漏、实际镜像与清理结果。它不调用实验汇总函数计算
这些数值，也不是独立人类 Review。

它还会运行单元测试并生成测试日志与 `audit.json`。不要使用 `python -O`
关闭断言，不要重新执行 `--freeze` 覆盖已冻结输入。原始实验、失败小测和旧
GloVe 证据均保留；数据缓存、连接密码和本地虚拟环境不纳入仓库。

方案与结果入口：[工作留痕](../../../docs/2026-09-10-observer-recall-overhead.md)。

## 本轮收尾

- [观察器](../../../experiments/hnsw_build/results/20260910T073830Z-observe-e2e/summary.json)：
  11 项真实受限账号检查通过，全部 Python 测试 78/78；系统 Python 72 通过、6 skip。
- [召回](../../../experiments/hnsw_build/results/20260910T074253Z-bounded-recall/report.md)：
  两档全量构建、一次预检，选中 m16/efc128/ef1000；新1000查询平均 Recall@10=95.47%，
  p50/p95=29.00/44.95ms，16,200 条测量已反算。
- [开销](../../../experiments/hnsw_build/results/20260910T075739Z-bounded-overhead/report.md)：
  192 次正式 + 96 次预热，12 个对比逐项复核。spill下开启计时与观察的4项增量
  有低于5%的支持；其余8项未建立。默认关闭新版有待定位的变慢信号，不能
  将整个项目写成“性能验收通过”。48 次带观察构建均采到进度。
- [audit.json](audit.json)：通过表示来源、原始计算与统计口径一致，不表示
  所有业务/性能目标都达成，也不替代人工 Review。它记录本轮最终文档哈希。
- 正式测量后仅更新文档与离线审计脚本；实验入口未再修改。全部临时实例/卷
  已清理，没有 Git 提交、推送或上游改动。下一步优先定位默认关闭路径的风险。

复算命令（会更新本目录的审计结果和测试日志；若只检查快照身份，先核对已有哈希）：

```bash
.venv-glove/bin/python dev/snapshots/20260910-observer-bounded/audit.py \
  --recall 20260910T074253Z-bounded-recall \
  --overhead 20260910T075739Z-bounded-overhead \
  --observer 20260910T073830Z-observe-e2e
```
