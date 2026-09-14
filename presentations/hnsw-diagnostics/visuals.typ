#import "@preview/diagraph:0.3.7" as dg
#import "@preview/lilaq:0.6.0" as lq

#let red = rgb("#b60b2d")
#let ink = rgb("#5a0718")
#let blue = rgb("#004f71")
#let gray = rgb("#62666c")
#let pale = rgb("#d8bdc5")
#let fmt(x, digits: 2) = str(calc.round(x, digits: digits))
#let signed(x) = (if x >= 0 { "+" } else { "−" }) + fmt(calc.abs(x)) + "%"
#let fixed(x, digits: 2) = {
  let value = str(calc.round(x, digits: digits))
  let places = if value.contains(".") { value.split(".").last().len() } else { 0 }
  value + (if places == 0 and digits > 0 { "." } else { "" }) + "0" * (digits - places)
}
#let signed-fixed(x) = (if x >= 0 { "+" } else { "−" }) + fixed(calc.abs(x)) + "%"
#let chart-label(body, color: ink, size: 15pt) = box(fill: white, inset: (x: 2pt, y: 0.5pt),
  text(size: size, weight: "bold", fill: color, body))
#let axis = (mirror: false, subticks: none, exponent: 0, offset: 0, stroke: 0.6pt + gray)

#let workflow(height: 170pt) = {
  set text(size: 18pt)
  layout(size => dg.render(read("graphs/diagnostic.dot"),
    width: size.width, height: height, stretch: false, math-mode: false,
    labels: (
      observe: [观察构建\ 阶段与等待],
      diagnose: [诊断瓶颈\ 耗时与内存],
      choose: [人工选参\ 资源与质量预算],
      verify: [复验结果\ 召回与延迟],
    ),
    edges: (verify: (diagnose: text(size: 14pt)[仍未满足目标时，由使用者决定是否继续]),),
  ))
}

#let architecture() = {
  set text(size: 17pt)
  layout(size => dg.render(read("graphs/architecture.dot"),
    width: size.width, height: 218pt, stretch: false, math-mode: false,
    labels: (
      hnsw: [本次 C 增强\ 外置 pgvector\ HNSW 构建],
      progress: [复用进度 / 活动视图\ 新增阶段发布],
      logs: [增强 spill 上下文\ 新增可选计时],
      observer: [observe.py\ 已有任务只读观察],
      runner: [run.py / timing.py\ 实验采样与解析],
      reports: [诊断报告\ Markdown / JSON],
    ),
    clusters: (cluster_db: [OpenTenBase PG18], cluster_tools: [Python 工具]),
  ))
}

#let phase-chart(d) = {
  set text(size: 15pt)
  let names = ("setup", "memory_build", "spill_drain", "flush", "disk_insert", "finalize", "wal", "cleanup")
  let colors = (gray, blue.lighten(55%), gray, red.lighten(20%), blue, gray, ink, gray)
  let starts = ()
  let bars = ()
  let t = 0.0
  for (i, name) in names.enumerate() {
    starts.push(t)
    let elapsed = d.example.phase_seconds.at(name)
    bars.push(lq.hbar((t + elapsed,), (0,), base: t, width: 0.5, fill: colors.at(i)))
    t += elapsed
  }
  let phase-label(name, title, color: ink) = chart-label([
    #title\ #fixed(d.example.phase_seconds.at(name)) s · #fixed(d.example.phase_seconds.at(name) / d.example.total_s * 100, digits: 1)%
  ], color: color, size: 16pt)
  let flush-mid = starts.at(3) + d.example.phase_seconds.flush / 2
  let wal-mid = starts.at(6) + d.example.phase_seconds.wal / 2
  lq.diagram(width: 100%, height: 0% + 185pt, xlim: (0, 1465), ylim: (-1.95, 1.8),
    xlabel: [内部构建累计时间 / s], grid: none,
    xaxis: axis + (ticks: (0, 500, 1000, 1400)),
    yaxis: axis + (ticks: none, stroke: none),
    ..bars,
    lq.place(210, 1.06, phase-label("memory_build", [内存构建])),
    lq.place(920, 1.06, phase-label("disk_insert", [磁盘路径插入], color: blue)),
    lq.place(t, 0.45, align: right + bottom, text(size: 12pt, fill: gray)[#fixed(t, digits: 3) s]),
    lq.line((flush-mid, -0.25), (flush-mid, -0.58), stroke: 0.8pt + red),
    lq.line((flush-mid, -0.58), (330, -0.94), stroke: 0.8pt + red),
    lq.place(300, -1.37, phase-label("flush", [图写成索引页])),
    lq.line((wal-mid, -0.25), (wal-mid, -0.58), stroke: 0.8pt + ink),
    lq.line((wal-mid, -0.58), (1190, -0.94), stroke: 0.8pt + ink),
    lq.place(1160, -1.37, phase-label("wal", [WAL])),
  )
}

#let memory-chart(d) = {
  set text(size: 14pt)
  let ys = (1, 0)
  let med = d.memory.map(x => x.median_s)
  lq.diagram(width: 100%, height: 0% + 185pt, xlim: (0, 2100), ylim: (-0.55, 1.8),
    xlabel: [完整构建命令耗时 / s], grid: none,
    xaxis: axis + (ticks: (0, 1000, 2000)),
    yaxis: axis + (ticks: ((1, [1024MB\ spill 3/3]), (0, [1792MB\ spill 0/3])), stroke: none),
    lq.place(1050, 1.66, text(size: 17pt, weight: "bold", fill: ink)[构建时间]),
    lq.hbar(med, ys, fill: pale, width: 0.23),
    ..d.memory.enumerate().map(((i, row)) => lq.plot(row.times_s, (ys.at(i), ys.at(i), ys.at(i) - 0.17),
      stroke: none, color: blue, mark: "o", mark-size: 7pt)),
    ..d.memory.enumerate().map(((i, row)) => lq.place(0, ys.at(i) + 0.31, align: left,
      chart-label([中位数 #fixed(row.median_s, digits: 1) s]))),
    ..d.memory.enumerate().map(((i, row)) => lq.place(0, ys.at(i) - 0.34, align: left,
      text(size: 12pt, fill: gray)[范围 #fixed(row.min_s, digits: 1)–#fixed(row.max_s, digits: 1) s])),
  )
}

#let resource-chart(d) = {
  set text(size: 14pt)
  let ys = (1, 0)
  lq.diagram(width: 100%, height: 0% + 185pt, xlim: (0, 4500), ylim: (-0.55, 1.8),
    xlabel: [容器峰值中位数 / MiB], grid: none,
    xaxis: axis + (ticks: (0, 2000, 4000)),
    yaxis: axis + (ticks: none, stroke: none),
    lq.place(2250, 1.66, text(size: 17pt, weight: "bold", fill: ink)[资源代价]),
    lq.hbar(d.memory.map(row => row.peak_mib_median), ys, fill: blue, width: 0.23),
    ..d.memory.enumerate().map(((i, row)) => lq.place(0, ys.at(i) + 0.31, align: left,
      chart-label([#fixed(row.peak_mib_median, digits: 1) MiB]))),
  )
}

#let recall-chart(d) = {
  set text(size: 15pt)
  let xs = d.recall.map(x => x.p50_execution_ms)
  let ys = d.recall.map(x => x.mean_recall * 100)
  lq.diagram(width: 100%, height: 0% + 180pt, xlim: (0, 34), ylim: (90, 97),
    xlabel: [查询 p50 / ms], ylabel: [平均 Recall\@10 / %], grid: none,
    xaxis: axis + (ticks: (0, 10, 20, 30)),
    yaxis: axis + (ticks: (90, 92, 94, 96)),
    lq.line((0, 95), (34, 95), stroke: (paint: gray, thickness: 0.8pt, dash: "dashed")),
    lq.place(1, 95.23, align: left + bottom,
      box(fill: white, inset: 1pt, text(size: 13pt, fill: gray)[自设平均目标 95%])),
    lq.plot((xs.at(0),), (ys.at(0),), stroke: none, mark: "o", mark-size: 9pt, color: blue),
    lq.plot((xs.at(1),), (ys.at(1),), stroke: none, mark: "s", mark-size: 9pt, color: red),
    lq.place(xs.at(0) + 1.4, ys.at(0) + 0.05, align: left + bottom,
      chart-label([ef=400\ #fixed(ys.at(0))% · #fixed(xs.at(0)) ms], color: blue, size: 14pt)),
    lq.place(xs.at(1) - 1.1, ys.at(1) + 0.28, align: right + bottom,
      chart-label([ef=1000\ #fixed(ys.at(1))% · #fixed(xs.at(1)) ms], color: red, size: 14pt)),
  )
}

#let latency-chart(d) = {
  set text(size: 14pt)
  let low = d.recall.at(0)
  let high = d.recall.at(1)
  let xs-low = (low.p50_execution_ms, low.p95_execution_ms)
  let xs-high = (high.p50_execution_ms, high.p95_execution_ms)
  let ys = (1, 0)
  lq.diagram(width: 100%, height: 0% + 180pt, xlim: (0, 53), ylim: (-0.58, 2.05),
    xlabel: [服务器执行耗时 / ms], grid: none,
    xaxis: axis + (ticks: (0, 25, 50)),
    yaxis: axis + (ticks: ((1, [p50]), (0, [p95])), stroke: none),
    lq.place(0, 1.8, align: left, text(size: 13pt, fill: blue)[● ef=400]),
    lq.place(28, 1.8, align: left, text(size: 13pt, fill: red)[■ ef=1000]),
    lq.plot(xs-low, ys, stroke: none, mark: "o", mark-size: 8pt, color: blue),
    lq.plot(xs-high, ys, stroke: none, mark: "s", mark-size: 8pt, color: red),
    ..xs-low.enumerate().map(((i, x)) => lq.place(x, ys.at(i) + 0.22, align: bottom,
      chart-label([#fixed(x)], color: blue, size: 14pt))),
    ..xs-high.enumerate().map(((i, x)) => lq.place(x, ys.at(i) + 0.22, align: bottom,
      chart-label([#fixed(x)], color: red, size: 14pt))),
  )
}

#let overhead-chart(d) = {
  set text(size: 15pt)
  let groups = d.formal.groups.filter(g => g.verdict != "supported")
  let ys = (2, 1, 0)
  let labels = ([并行无 spill / 关闭计时], [并行无 spill / 开启计时], [并行 spill / 开启计时])
  let plots = ()
  for base in (0, 14) {
    plots.push(lq.line((base, -0.35), (base, 2.4), stroke: 0.5pt + pale))
    plots.push(lq.line((base + 5, -0.35), (base + 5, 2.4),
      stroke: (paint: gray, thickness: 0.8pt, dash: "dashed")))
    plots.push(lq.place(base + 5, 2.55, text(size: 12pt, fill: gray)[自设 5%]))
    plots.push(lq.line((base - 2, -0.35), (base + 10, -0.35), stroke: 0.6pt + gray))
    for tick in (-2, 0, 5, 10) {
      plots.push(lq.line((base + tick, -0.35), (base + tick, -0.43), stroke: 0.6pt + gray))
      plots.push(lq.place(base + tick, -0.6, text(size: 13pt, fill: gray)[#tick]))
    }
  }
  lq.diagram(width: 100%, height: 0% + 190pt, xlim: (-2, 25), ylim: (-0.9, 3.4),
    xlabel: [相对原版的时间变化 / %], grid: none,
    xaxis: axis + (ticks: none, stroke: none),
    yaxis: axis + (ticks: ys.zip(labels), stroke: none),
    ..plots,
    lq.place(4, 3.12, text(size: 17pt, weight: "bold", fill: blue)[中位点估计]),
    lq.place(18, 3.12, text(size: 17pt, weight: "bold", fill: red)[联合单侧上界]),
    lq.plot(groups.map(g => g.median_change), ys, stroke: none, mark: "o", mark-size: 8pt, color: blue),
    lq.plot(groups.map(g => 14 + g.upper_change), ys, stroke: none, mark: "^", mark-size: 8pt, color: red),
    ..groups.enumerate().map(((i,g)) => lq.place(g.median_change + 0.35, ys.at(i),
      align: left, chart-label(signed-fixed(g.median_change), color: blue))),
    ..groups.enumerate().map(((i,g)) => lq.place(14 + g.upper_change + 0.35, ys.at(i),
      align: left, chart-label(signed-fixed(g.upper_change), color: red))),
  )
}

#let performance-method() = {
  set text(size: 17pt)
  layout(size => dg.render(read("graphs/performance-method.dot"),
    width: size.width, height: 165pt, stretch: false, math-mode: false,
    labels: (
      build: [统一构建\ 原版与候选\ 同一工具链],
      run: [固定实验\ 4 场景 × 24 面板\ 正逆序平衡],
      aggregate: [面板内聚合\ 每条件两次\ 几何均值与配对比值],
      judge: [联合判定\ 12 项单侧上界\ 均须低于自设 5%],
    ),
  ))
}

#let cpu-chart(d) = {
  set text(size: 14pt)
  let xs = range(1, d.cpu.values.len() + 1)
  let min-index = d.cpu.values.position(x => x == d.cpu.min) + 1
  let max-index = d.cpu.values.position(x => x == d.cpu.max) + 1
  lq.diagram(width: 100%, height: 0% + 205pt, xlim: (0.4, 12.7), ylim: (0, 11.8),
    xlabel: [正式运行序号], ylabel: [耗时 / s], grid: none,
    xaxis: axis + (ticks: (1, 4, 8, 12)), yaxis: axis + (ticks: (0, 5, 10)),
    lq.place(6.5, 11.1, text(size: 16pt, weight: "bold", fill: ink)[固定 CPU 工作 · 12 次]),
    lq.plot(xs, d.cpu.values, stroke: none, color: blue, mark: "o", mark-size: 7pt),
    lq.place(min-index + 0.15, d.cpu.min - 0.85, align: left + top,
      chart-label([#fixed(d.cpu.min, digits: 3) s], color: blue, size: 14pt)),
    lq.place(max-index - 0.1, d.cpu.max + 0.75, align: right + bottom,
      chart-label([#fixed(d.cpu.max, digits: 3) s], color: blue, size: 14pt)),
  )
}

// Each mode is a separate 0–10% scale, translated by the same column spacing.
// hbar takes endpoint coordinates; adding the column base preserves bar length.
#let overhead-matrix(d) = {
  set text(size: 16pt)
  let modes = (("off", [关闭计时]), ("on", [开启计时]), ("observed", [开启并观察]))
  let scenarios = ((0, false), (0, true), (2, false), (2, true))
  let rows = (3, 2, 1, 0)
  let labels = ([串行无 spill], [串行 spill], [并行无 spill], [并行 spill])
  let plots = ()
  for (col, (mode, title)) in modes.enumerate() {
    let base = col * 12
    let groups = scenarios.map(((workers, spill)) => d.formal.groups.find(g =>
      g.workers == workers and g.spill == spill and g.condition == mode))
    let colors = groups.map(g => if g.verdict == "supported" { blue } else { red })
    plots.push(lq.place(base + 4.5, 4.03, text(size: 18pt, weight: "bold", fill: ink, title)))
    plots.push(lq.line((base, -0.4), (base, 3.4), stroke: 0.5pt + pale))
    plots.push(lq.line((base + 5, -0.4), (base + 5, 3.4),
      stroke: (paint: gray, thickness: 0.8pt, dash: "dashed")))
    plots.push(lq.place(base + 5, 3.57, text(size: 12pt, fill: gray)[5%]))
    plots.push(lq.line((base, -0.4), (base + 10, -0.4), stroke: 0.6pt + gray))
    for tick in (0, 5, 10) {
      plots.push(lq.line((base + tick, -0.4), (base + tick, -0.48), stroke: 0.6pt + gray))
      plots.push(lq.place(base + tick, -0.62, text(size: 13pt, fill: gray)[#tick]))
    }
    plots.push(lq.hbar(groups.map(g => base + g.upper_change), rows,
      base: base, fill: colors, width: 0.34))
    for (row, g) in groups.enumerate() {
      let value = str(calc.round(g.upper_change, digits: 2))
      let digits = if value.contains(".") { value.split(".").last().len() } else { 0 }
      let label = "+" + value + (if digits == 0 { "." } else { "" }) + "0" * (2 - digits) + "%"
      plots.push(lq.place(base + g.upper_change + 0.25, rows.at(row), align: left,
        box(fill: white, inset: (x: 2pt, y: 0.5pt),
          text(size: 15pt, weight: "bold", fill: colors.at(row), label))))
    }
  }
  lq.diagram(width: 100%, height: 0% + 195pt, xlim: (0, 34.5), ylim: (-0.94, 4.45),
    xlabel: [相对原版的联合单侧上界 / %], grid: none,
    xaxis: axis + (ticks: none, stroke: none),
    yaxis: axis + (ticks: rows.zip(labels), stroke: none),
    ..plots,
  )
}
