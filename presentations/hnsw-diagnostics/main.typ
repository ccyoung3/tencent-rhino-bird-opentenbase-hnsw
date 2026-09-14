#import "@preview/touying:0.6.1": *
#import "@preview/touying-simpl-ecnu:0.0.1": *
#import "visuals.typ": workflow, architecture, phase-chart, memory-chart, resource-chart, recall-chart, latency-chart, overhead-chart, overhead-matrix, performance-method, cpu-chart, fixed

#import "logic.typ": contribution-layers, requirement-story, verification-evidence, delivery-progress, technical-decisions, delivery-route, mechanism-reasoning
#import "user-experience.typ": user-experience

#let d = json("data.json")
#let red = rgb("#b60b2d")
#let ink = rgb("#5a0718")
#let blue = rgb("#004f71")
#let gray = rgb("#62666c")

// Keep the supplied ECNU theme, its logo, watermark, header and footer.
// Source Han Sans SC and Libertinus Serif are the installed template fonts.
#show: ecnu-theme.with(
  lang: "zh",
  font: ((name: "Libertinus Serif", covers: "latin-in-cjk"), "Source Han Sans SC"),
  align: top,
  config-common(new-section-slide-fn: none),
  config-page(margin: (top: 4.6em, bottom: 2.2em, x: 2.5em)),
  config-info(
    title: [OpenTenBase HNSW\ 索引构建诊断与调参验证],
    subtitle: [腾讯犀牛鸟开源计划阶段汇报（初稿）],
    short-title: [HNSW 构建诊断],
    author: [CCYoung],
    institution: [华东师范大学],
    date: [2026 年 9 月 13 日],
  ),
)
#set heading(numbering: none)
#set par(leading: 0.55em)
#set list(marker: text(fill: red)[•], spacing: 0.65em)
#set enum(spacing: 0.7em)
#show raw: set text(font: "Menlo", size: 0.76em)

#let small(body) = text(size: 14pt, fill: gray, body)
#let source(body) = { v(0.6em); text(size: 10.5pt, fill: gray, body) }
#let takeaway(body) = { v(0.55em); text(fill: ink, weight: "bold", body) }
#let fmt(x, digits: 2) = str(calc.round(x, digits: digits))
#let signed(x) = (if x >= 0 { "+" } else { "−" }) + fmt(calc.abs(x)) + "%"
#let key(body, color: ink) = text(weight: "bold", fill: color, body)
#let tbl(columns, inset-y: 9pt, size: 17pt, ..cells) = {
  set text(size: size)
  table(
    columns: columns,
    stroke: (x: none, y: 0.5pt + rgb("#ded2d5")),
    inset: (x: 9pt, y: inset-y),
    fill: (x, y) => if y == 0 { rgb("#f5e8ec") } else { none },
    ..cells,
  )
}
#title-slide()

= 项目与实现

== 本次贡献：在已有构建能力上补充诊断与复验

#small[本次工作聚焦三个增量：过程更清楚，耗时可解释，参数建议有复验依据。]
#v(0.3em)
#contribution-layers()
#source[上层是本次增强，底层为复用的上游能力。参数调整与是否继续复验由使用者决定；未开发新的 HNSW 算法，OpenTenBase 核心源码未改 [S1–S3]。]

== 回答了哪些问题？

#requirement-story()

== 使用体验：构建诊断与参数复验

#user-experience()

== 实现架构：C 增强与诊断工具的分工

#small[OpenTenBase 18.6 / PG18 + 外置 pgvector 0.8.6，集中式 Linux。箭头表示诊断数据流。]
#v(0.35em)
#architecture()
#text(size: 17pt)[红色区域：构建端增强；蓝色区域：本次工具与报告。]
#source[C 改动在外置 pgvector，OpenTenBase 核心源码未改。observe.py 只读进度和活动视图，不读取构建日志；计时摘要由构建侧采集 [S1–S4]。]

== 两个工程难点：并行可见性与计时可靠性

#grid(columns: (1fr, 1fr), column-gutter: 30pt,
  [
    #text(size: 22pt, weight: "bold", fill: ink)[01 让使用者看到正确阶段]
    #v(0.35em)
    #set text(size: 18pt)
    #key([问题])\ worker 直接更新进度，不能替代 leader 的对外发布。

    #key([设计])\ worker 更新共享阶段，leader 统一发布；阶段只向前推进。

    #key([验证], color: blue)\ 覆盖串行 / 并行、spill 转换与阶段顺序。
  ],
  [
    #text(size: 22pt, weight: "bold", fill: ink)[02 让计时摘要可以解释]
    #v(0.35em)
    #set text(size: 18pt)
    #key([问题])\ 轮询会漏掉短阶段；共享内存释放后不能再读取计时。

    #key([设计])\ 默认关闭、按边界计时；释放 DSM 前复制所需数据。

    #key([验证], color: blue)\ 可选区间保留 null；失败或取消时，不输出完整摘要。
  ],
)
#source[对外四类阶段与内部八段计时粒度不同；完整名称和生命周期说明见讲解备注。记录一次内部构建调用的墙钟时间，不是 worker CPU 总和或事务提交延迟；不逐向量读取时钟 [S2–S3]。]

= 案例与结果

== 真实诊断输出：从一次 spill 到复验方案

#small[2026-09-09 既有报告节选：GloVe 1,183,514 × 100，1024MB，m=16，ef_construction=64，2 worker。]
#v(0.4em)
#grid(columns: (0.9fr, 1.6fr), column-gutter: 28pt,
  [
    #text(size: 17pt, weight: "bold", fill: ink)[报告中的实测字段]
    #v(0.35em)
    #block(fill: rgb("#edf4f7"), inset: 12pt, width: 100%)[
      #set text(size: 17pt)
      `Timing status: complete`\
      `disk_insert: 982.004717s`\
      `spill=True`

      #text(size: 30pt, weight: "bold", fill: blue)[69.4%]\ 占内部构建时间
    ]
  ],
  [
    #set text(size: 17pt)
    #set par(spacing: 0.65em)
    #key([证据])　磁盘路径插入是本次最大的耗时区间。

    #key([判断])　定位到构建路径，尚不能归因到 CPU 或 I/O。

    #key([建议])　内存余量允许时提高构建预算，其余条件固定。

    #key([复验], color: blue)　低 / 高内存各重复构建，同时检查 spill、总耗时和峰值内存。
  ],
)
#source[字段与右侧中文摘录来自同一实际诊断报告 [S5]；不是现场运行或产品界面截图。原文随包附在 evidence/glove-low-r1-diagnostic.md。单次报告只提出建议，下一页开始展示诊断依据及复验结果。]

== 案例一：spill 后的磁盘路径占主要耗时

#small[GloVe 1,183,514 × 100，1024MB，m=16，ef_construction=64，2 worker。]
#v(0.25em)
#phase-chart(d)
#takeaway[本次磁盘路径插入占内部时间 #fmt(d.example.disk_fraction * 100, digits: 1)%。]
#source[横条按八段边界累计，完整内部时间 1414.450s；四个主要区间直接标注，其余约 0.068s 保留原宽度。短阶段用引线标注，不放大条长。图写成页不等于设备 fsync，不能据此唯一定位 SSD 根因 [S5]。]

== 诊断建议复验：增加内存预算

#small[同一全量 GloVe、相同 m / ef_construction、实际 2 worker，每档三次独立构建。]
#v(0.2em)
#grid(columns: (1.5fr, 1fr), column-gutter: 30pt, memory-chart(d), resource-chart(d))
#takeaway[耗时中位数减少 #fixed(d.memory_reduction_percent, digits: 1)%；容器峰值中位数增加 #fixed((d.memory.at(1).peak_mib_median / d.memory.at(0).peak_mib_median - 1) * 100, digits: 1)%。]
#source[左右两图按相同预算行对齐，单位不同，各自从 0 起计。左图蓝点为六次实测，纵向轻微错位以分辨重叠；浅色条为中位数。收益来自内存调参，容器峰值包含数据库与缓存，并非 HNSW 私有内存 [S5]。]

== 案例二：低召回风险与调整代价

#text(size: 17pt)[固定最终索引 m=16 / ef_construction=128，复验两种查询参数的质量与延迟。]
#v(0.35em)
#grid(columns: (1.4fr, 1fr), column-gutter: 35pt, align: horizon,
  recall-chart(d), latency-chart(d),
)
#takeaway[平均召回提高 4.34 个百分点；查询 p50 约为原来的 7.75 倍。]
#source[ef=400 未达到自设平均 95% 目标。参数锁定后使用新的 1000 个验证查询；右图 p50 / p95 使用相同毫秒刻度。两组实测配置不表示连续拟合；暖缓存服务器时间不代表端到端延迟或业务最优配置 [S6]。]

== 功能验证：行为、兼容性与实际使用

#verification-evidence()
#source[C 回归来自 9/6，同一候选在两环境分别通过，本轮未重跑。632 包含上游复验和新增计时专项；三组证据单位不同，不相加。业务库尚未试用，功能通过不等于性能验收通过 [S3–S4、S13]。]

== 诊断开销：9 项支持，3 项尚未证明

#text(size: 17pt)[与未修改原版的 12 项比较中，9 项支持低于自设 5% 参考线。]

#v(0.2em)
#overhead-chart(d)
#text(size: 17pt)[每组 24 个统计单位，共 768 次正式构建、384 次预热。\ 没有一项建立超过 5% 的回归证据，不能据此判定 C 有缺陷。]
#source[上界采用 12 项联合校正，假设面板独立、可比较。仅适用于本地固定负载与 seed42 受控构建；5% 尚未确认是项目方硬门槛，整体低于 5% 未通过 [S7]。]

= 交付与讨论

== 已有本地候选，下一步是 Review 与集成

#small[蓝色实框标明当前已有成果；灰色虚框为后续步骤，不表示已经通过。]
#v(0.3em)
#delivery-progress()
#v(0.4em)
#text(size: 20pt, weight: "bold", fill: ink)[当前可供核对的材料]
#v(0.2em)
#text(size: 18pt)[C / TAP 候选与诊断工具；案例报告、环境说明和性能边界。\ 本次汇报包另附 PDF、可编辑源码、讲稿与关键报告原文。]
#source[接收标准、维护者 Review、最终集成和上游交付尚未完成。个人仓库于 9/8 初始化，后续仍有未提交内容。复验入口见 reproduction.md；本包不包含完整数据库镜像和大向量数据 [S1、S4、S8]。]

== 待向 cyrilwu 确认：技术接收边界

#align(center)[#box(width: 530pt)[#align(left)[#technical-decisions()]]]
#source[三条分支是需要确定的接收条件，不表示新增实验或已获认可的流程。建议先明确标准，再安排必要补测；现有本地功能和案例证据可作为代码 Review 的讨论起点 [S1、S4、S7]。]

== 待向 cyrilwu 确认：交付路径与入口

#small[建议先提供候选供 Review；目标位置确定后，按接收要求完成集成和提交。]
#v(0.3em)
#delivery-route()
#v(0.4em)
#text(size: 19pt)[#key([接收形式])　先送 patch Review，还是直接整理 PR？工具和证据放在哪里？]
#v(0.5em)
#text(size: 19pt)[#key([时间与入口])　9/14 的具体截止时刻、提交入口，以及必需演示和材料？]
#source[接收位置、形式与时间均尚未确认。原始会议提到 9/14 提交结果，不代表已获延期、豁免或维护者接收。本图为拟议交付顺序 [S1、S8]。]

= 技术附录

== 附录 A：12 项开销比较

#small[四个场景 × 三种模式。三列刻度相同，虚线均为自设 5% 参考线。]
#v(0.25em)
#overhead-matrix(d)
#text(size: 17pt)[#text(fill: blue, weight: "bold")[9 项支持低于 5%]；#text(fill: red, weight: "bold")[3 项尚未证明]，均在并行场景。]
#source[各条从 0 延伸至经 12 项校正的单侧上界，并非实测开销或双侧区间。估计对象为面板聚合后配对时间比值的中位数，不是单次最坏开销；观察组上界较低不代表观察会加速构建 [S7]。]

== 附录 B：正式性能方法

#small[诊断条件：关闭计时、开启计时、开启并观察；均与未修改原版比较。]
#v(0.35em)
#performance-method()
#text(size: 17pt)[#key([上界方法])：精确二项顺序统计量 + Bonferroni 校正。\ #key([证据前提])：面板独立、可比较；保留失败批与时序变异，不筛样本或事后扩量。]
#source[24 面板是每项的 24 个统计单位，不能将同实例内重复计为 48 个独立样本。旧 A/A 失败保留，新协议不声称旧协议通过 [S7]。]

== 附录 C：为什么尚不能归因于 C

#grid(columns: (1.25fr, 1fr), column-gutter: 25pt, align: horizon,
  mechanism-reasoning(), cpu-chart(d),
)
#takeaway[当前未定位确定的 C 回归；正式结论仍是 9 项支持、3 项未证明。]
#source[左图汇总补充检查的解释限制，不是因果证明。右图为全部 12 次正式 CPU 校准，不含预热；最大/最小约 1.305，不是产品开销，也不证明 5% 不可识别。产品 C 候选保持 9/6 版本 [S9]。]

== 附录 D：三类验证的环境配置对照

#small[宿主 Apple M4，10 核、24 GiB RAM；OrbStack 原生 ARM64。OpenTenBase 18.6 / PG18 + pgvector 0.8.6。]
#v(0.25em)
#tbl((0.65fr, 1.15fr, 1fr, 1.1fr), inset-y: 6pt, size: 15.5pt,
  [*配置维度*], [*功能 / 兼容性*], [*GloVe 内存对照*], [*正式开销对照*],
  key([运行环境]), [Debian 容器\ CentOS Stream 9 Machine], [Debian ARM64\ Docker], [Debian ARM64\ Docker],
  key([实例资源]), [分别按功能测试配置\ 不用于开销比较], [构建容器限 6 GiB\ 无额外 swap 配额], [每实例 2 GiB\ 无额外 swap 配额],
  key([并行与重复]), [覆盖串并行路径\ 同一候选分别回归], [实际 2 worker\ 每档三次独立构建], [0 / 2 worker\ 四场景 × 24 面板],
  key([控制条件]), [同一 9/6 C 候选], [1024MB / 1792MB\ 正常随机构建], [统一工具链\ seed42 受控构建],
)
#v(0.2em)
#text(size: 16pt)[复验入口：#link("reproduction.md")[reproduction.md]；镜像身份和完整配置见 #link("environment-summary.md")[environment-summary.md]。]
#source[GloVe 预检 Docker 可见 10 CPU / 约 11.7 GiB，宿主磁盘可用约 43 GiB；正式开销使用 Linux 客体 CPU 0–9。宿主非独占；磁盘剩余空间不是吞吐指标，存储型号 / IOPS 未归档 [S13]。]
