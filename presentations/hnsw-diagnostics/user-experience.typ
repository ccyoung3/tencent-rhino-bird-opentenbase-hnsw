#let ink = rgb("#243b49")
#let blue = rgb("#005675")
#let gray = rgb("#6b7880")
#let terminal = rgb("#1d2b35")

// The report is a screenshot; progress is explicitly labelled as saved samples.
#let user-experience() = {
  set text(font: "Source Han Sans SC", size: 13pt, fill: ink)
  set par(spacing: 0pt, leading: 0.35em)
  let heading(number, title, surface) = grid(
    columns: (25pt, 1fr, auto), column-gutter: 3pt, align: horizon,
    text(size: 14pt, weight: "bold", fill: blue, number),
    text(size: 18pt, weight: "bold", title),
    text(size: 10.5pt, fill: gray, surface),
  )
  text(size: 13pt, fill: gray)[本地示例：5 万条、64 维模拟向量]
  v(16pt)
  grid(columns: (0.35fr, 0.65fr), column-gutter: 28pt,
    [
      #heading([01], [启动构建], [终端 A])
      #v(9pt)
      #block(width: 100%, fill: terminal, radius: 4pt, inset: 11pt)[
        #show raw: set text(font: "Menlo", size: 12pt, fill: rgb("#f0f4f6"))
        #set par(leading: 0.6em)
        #raw("--build-timing\n--rows 50000 --dimensions 64\n--maintenance-work-mem 8MB", block: true)
      ]
      #v(7pt)
      #text(size: 11.5pt, fill: gray)[命令节选 · 设置参数，开启内部计时]
      #v(20pt)
      #heading([02], [观察当前阶段], [终端 B · 可选])
      #v(9pt)
      #block(width: 100%, fill: terminal, radius: 4pt, inset: 11pt)[
        #text(font: "Menlo", size: 9pt, fill: rgb("#90a7b3"))[phase]
        #v(4pt)
        #text(font: "Menlo", size: 9.5pt, fill: rgb("#f0f4f6"))[building index: loading tuples on disk]
        #v(8pt)
        #text(font: "Menlo", size: 11pt, fill: rgb("#c2e6ef"))[tuples_done  18080 → 28031]
      ]
      #v(7pt)
      #text(size: 11.5pt, fill: gray)[另开终端查询，观察处理条数的变化]
    ],
    [
      #heading([03], [查看诊断报告], [自动生成 · diagnostic.md])
      #v(9pt)
      #image("assets/manual-low-report-crop.png", width: 100%)
      #v(12pt)
      #grid(columns: (55pt, 1fr), column-gutter: 8pt, row-gutter: 8pt, align: horizon,
        text(size: 11.5pt, fill: gray)[耗时位置],
        text(size: 15pt)[磁盘插入 #text(weight: "bold", fill: blue)[70.31 秒]，占内部耗时 #text(weight: "bold", fill: blue)[96.5%]],
        text(size: 11.5pt, fill: gray)[调整依据],
        text(size: 14pt)[已触发落盘，内存允许时增大构建预算],
      )
    ],
  )
  v(10pt)
  block(width: 100%, fill: rgb("#f1f6f8"), radius: 4pt, inset: (x: 14pt, y: 9pt))[
    #grid(columns: (1.05fr, 1.35fr, 0.95fr), column-gutter: 24pt,
      [
        #text(size: 13pt, weight: "bold")[#text(fill: blue)[04] #h(4pt) 使用者调整并复验]
        #v(8pt)
        #text(size: 21pt, weight: "bold", fill: blue)[8MB → 64MB]
      ],
      [
        #text(size: 11.5pt, fill: gray)[构建耗时]
        #v(8pt)
        #text(size: 23pt)[#text(fill: gray)[73.00 s] #text(size: 17pt, fill: gray)[→] #text(weight: "bold", fill: blue)[14.40 s]]
      ],
      [
        #text(size: 11.5pt, fill: gray)[落盘（spill）]
        #v(10pt)
        #text(size: 19pt)[#text(fill: gray)[发生] #text(size: 16pt, fill: gray)[→] #text(weight: "bold", fill: blue)[未发生]]
      ],
    )
  ]
  v(5pt)
  text(size: 10pt, fill: gray)[本机各一次体验；64MB 由使用者选择，其余参数一致。左侧为真实采样节选，终端截图待补 [S15]。]
}
