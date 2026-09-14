#import "@preview/diagraph:0.3.7" as dg

#let red = rgb("#b60b2d")
#let ink = rgb("#5a0718")
#let blue = rgb("#004f71")
#let gray = rgb("#62666c")

#let label(title, body, color: ink) = [
  #text(size: 20pt, weight: "bold", fill: color, title)\
  #text(size: 16pt, body)
]

#let contribution-layers() = {
  layout(size => dg.render(read("graphs/contributions.dot"),
    width: size.width, height: 230pt, stretch: false, math-mode: false,
    labels: (
      foundation: [#text(size: 17pt, fill: gray)[复用上游基础]\
        #text(size: 19pt)[HNSW 构建与查询 · 基本进度视图 · 原有 spill 告警]],
      process: label([细化过程], [四类阶段 · 并行发布\ spill 上下文]),
      timing: label([解释耗时], [八段内部计时\ 默认关闭、按需启用]),
      verify: label([支持复验], [只读观察 · 诊断报告\ 参数收益与代价对照], color: blue),
    ),
    clusters: (cluster_new: [],),
  ))
}

#let requirement-story() = {
  set text(font: "Source Han Sans SC", fill: rgb("#243b49"))
  set par(spacing: 0pt, leading: 0.3em)
  let docs = "https://github.com/pgvector/pgvector/blob/v0.8.6/README.md"
  let issue = "https://github.com/pgvector/pgvector/issues/969"
  let question(title, pain) = box(width: 190pt)[#align(left)[
    #text(size: 23pt, weight: "bold", fill: ink, title)\
    #text(size: 15pt, fill: gray, pain)
  ]]
  let answer(title, method) = box(width: 210pt)[#align(left)[
    #text(size: 22pt, weight: "bold", fill: blue, title)\
    #text(size: 15pt, fill: gray, method)
  ]]
  text(size: 14pt, fill: gray)[聚焦 HNSW 建索引与调参]
  v(14pt)
  layout(size => dg.render(read("graphs/user-questions.dot"),
    width: size.width, height: 264pt, stretch: false, math-mode: false,
    labels: (
      user: box(width: 118pt)[#align(center)[
        #text(size: 13pt, fill: gray)[主要使用者]\
        #text(size: 19pt, weight: "bold", fill: ink)[数据库工程师]\
        #text(size: 23pt, weight: "bold", fill: ink)[DBA]
      ]],
      slow: question([慢在哪里？], [阶段粗，难定位]),
      tune: question([该怎样调整？], [内存不足，收益待验证]),
      quality: question([调整后有效吗？], [召回提升有延迟代价]),
      timing: answer([拆解构建耗时], [4 类阶段 · 8 段计时]),
      compare: answer([复验参数建议], [对照时间收益与内存代价]),
      validate: answer([验证召回与延迟], [用独立查询检验质量]),
    ),
  ))
  v(17pt)
  text(size: 12pt, fill: gray)[问题依据：#link(docs)[pgvector 0.8.6 官方文档 [S16]]；#link(issue)[2026 年用户调参反馈 \#969 [S17]]（已关闭）。]
  v(5pt)
  text(size: 10.5pt, fill: gray)[目标人群为项目定位；公开个例不代表普遍性。异常验证与六类要求映射见讲稿。]
}

#let verification-evidence() = {
  grid(columns: (1.25fr, 0.85fr, 0.85fr), column-gutter: 28pt,
    [
      #text(size: 20pt, weight: "bold", fill: ink)[C 功能与兼容性]
      #v(8pt)
      #text(size: 44pt, weight: "bold", fill: blue)[632]\
      #text(size: 17pt)[个断言 / 每个环境]
      #v(8pt)
      #text(size: 15pt)[Debian / CentOS ARM64\ 各 28 个 TAP 文件、4 项 SQL 回归]
      #v(12pt)
      #line(length: 100%, stroke: 0.7pt + blue)
      #v(6pt)
      #text(size: 17pt)[其中：#text(weight: "bold", fill: blue)[221] 个计时专项断言\ 已包含在 632 中]
    ],
    [
      #text(size: 20pt, weight: "bold", fill: ink)[Python 工具]
      #v(8pt)
      #text(size: 44pt, weight: "bold", fill: blue)[120]\
      #text(size: 17pt)[项测试通过]
      #v(8pt)
      #text(size: 16pt)[解析与诊断报告\ 观察与实验工具]
    ],
    [
      #text(size: 20pt, weight: "bold", fill: ink)[本地只读观察]
      #v(8pt)
      #text(size: 44pt, weight: "bold", fill: blue)[11 / 11]\
      #text(size: 17pt)[项实际检查通过]
      #v(8pt)
      #text(size: 16pt)[受限账号、中途接入\ 停止观察不取消构建]
    ],
  )
}

#let delivery-progress() = {
  layout(size => dg.render(read("graphs/delivery-progress.dot"),
    width: size.width, height: 150pt, stretch: false, math-mode: false,
    labels: (
      current: label([已有候选], [C / TAP · 工具\ 案例与汇报材料], color: blue),
      scope: label([待确认], [接收标准\ 仓库与目录], color: gray),
      review: label([待 Review], [维护者检查\ 明确补证范围], color: gray),
      integration: label([待集成验证], [目标目录\ 干净构建与回归], color: gray),
      submit: label([待正式提交], [按确认形式\ 整理交付], color: gray),
    ),
  ))
}

#let technical-decisions() = {
  layout(size => dg.render(read("graphs/technical-decisions.dot"),
    width: size.width, height: 248pt, stretch: false, math-mode: false,
    labels: (
      scope: [#text(size: 23pt, weight: "bold", fill: ink)[请确认\ 技术接收边界]],
      interface: label([接口：名称与字段是否可接受？],
        [建议以四类阶段、现有字段\ 和默认关闭计时作为 Review 起点]),
      overhead: label([门槛：约束哪些模式、多少开销？],
        [5% 为自设参考，三项未证明；建议分别约定\ 关闭 / 开启 / 观察的指标与统计口径]),
      validation: label([补证：还需要什么机器和负载？],
        [本地已有证据，尚无业务库试用；\ 建议先做代码 Review，再限定补证范围]),
    ),
  ))
}

#let delivery-route() = {
  layout(size => dg.render(read("graphs/delivery-route.dot"),
    width: size.width, height: 145pt, stretch: false, math-mode: false,
    labels: (
      candidate: label([当前候选], [外置 pgvector 0.8.6\ 补丁、工具与证据], color: blue),
      location: label([接收位置？], [仓库 · 分支 · 目录]),
      integration: label([集成与回归], [按目标目录\ 重新构建验证], color: gray),
      submit: label([正式交付], [按确认入口\ 提交成果], color: gray),
    ),
  ))
}

#let mechanism-reasoning() = {
  layout(size => dg.render(read("graphs/mechanism-reasoning.dot"),
    width: size.width, height: 220pt, stretch: false, math-mode: false,
    labels: (
      counts: [#text(size: 17pt, weight: "bold", fill: ink)[机制计数]\
        #text(size: 15pt)[距离计算次数不足以\ 解释全部时间波动]],
      bridge: [#text(size: 17pt, weight: "bold", fill: ink)[插桩桥接]\
        #text(size: 15pt)[计数存在测量扰动\ 不能直接替代普通构建]],
      review: [#text(size: 17pt, weight: "bold", fill: ink)[C 热路径审查]\
        #text(size: 15pt)[有待检验假说\ 尚无定位后的修复]],
      judgment: [#text(size: 14pt, fill: gray)[当前判断]\
        #text(size: 18pt, weight: "bold", fill: blue)[尚未定位\ 确定的 C 回归]],
    ),
  ))
}
