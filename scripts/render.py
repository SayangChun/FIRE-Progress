"""README 与 SVG 曲线渲染。

所有输出都是纯字符串拼接，不依赖绘图库——CI 里少一个依赖就少一个故障点。
"""

from __future__ import annotations

import math

START_MARK = "<!-- FIRE:START -->"
END_MARK = "<!-- FIRE:END -->"

# ---------------------------------------------------------------- 基础格式化


def money(value, cfg, *, decimals: int = 2, symbol: str | None = None) -> str:
    if value is None:
        return "—"
    if cfg.privacy.get("mode") == "masked":
        return "已隐藏"
    symbol = symbol if symbol is not None else cfg.fire.get("currency_symbol", "¥")
    return f"{symbol}{value:,.{decimals}f}"


# ---------------------------------------------------------------- 进度条 SVG
#
# 为什么不用「█░▎」拼文本进度条：
# 这些块字符（U+2588 全块 / U+2591 浅阴影 / U+258E 左四分之一块）在
# Unicode 里的 East Asian Width 是 Ambiguous —— 中文环境下会被渲染成
# 全角（2 倍宽），英文环境下是半角；一旦两端 fallback 到不同字体，
# 整条进度条就会宽度错乱、看起来「不对」，且不同平台表现不一致。
# SVG 按坐标绘制，与字体无关，跨平台完全一致。
#
# 同理不再使用 shields.io 徽章：它是不可控的外部服务，大陆网络下
# 时通时不通（本地实测直连与代理均不可达），且 label 含中文时若不
# URL 编码会直接返回「404 badge not found」。进度标识改为自绘。


def progress_svg(data: dict, cfg) -> str:
    """自绘 FIRE 完成度进度条。"""
    assets = data["assets"]
    fire = data["fire"]

    ratio = max(min(float(assets.get("progress") or 0.0), 1.0), 0.0)
    pct = ratio * 100

    width, height = 680, 92
    track_y, track_h = 40, 14
    track_r = track_h / 2

    # 极小进度也留 1px，避免「有资产却完全看不见」
    fill_w = max(width * ratio, 1.0) if ratio > 0 else 0.0
    fill_r = min(track_r, fill_w / 2) if fill_w else 0.0

    current = money(assets.get("total_cny"), cfg)
    target = money(fire.get("target_cny"), cfg)
    remaining = money(assets.get("remaining_cny"), cfg)

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-label="FIRE 完成度 {pct:.3f}%">
  <title>FIRE 完成度 {pct:.3f}%</title>
  <desc>当前资产 {current}，FIRE 目标 {target}，完成度 {pct:.3f}%，距离目标还差 {remaining}。</desc>
  <style>
    .fg {{ fill: #1f2328; font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif; }}
    .fg-muted {{ fill: #57606a; font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif; }}
    .track {{ fill: #e7ebef; }}
    .fill {{ fill: #d97706; }}
    @media (prefers-color-scheme: dark) {{
      .fg {{ fill: #e6edf3; }}
      .fg-muted {{ fill: #8b949e; }}
      .track {{ fill: #21262d; }}
      .fill {{ fill: #f0b429; }}
    }}
  </style>
  <text class="fg-muted" x="0" y="18" font-size="12">FIRE 完成度</text>
  <text class="fg" x="{width}" y="20" text-anchor="end" font-size="19" font-weight="600">{pct:.3f}%</text>
  <rect class="track" x="0" y="{track_y}" width="{width}" height="{track_h}" rx="{track_r}"/>
  <rect class="fill" x="0" y="{track_y}" width="{fill_w:.1f}" height="{track_h}" rx="{fill_r:.1f}"/>
  <text class="fg-muted" x="0" y="82" font-size="11">已积累 {current}</text>
  <text class="fg-muted" x="{width}" y="82" text-anchor="end" font-size="11">目标 {target} · 还差 {remaining}</text>
</svg>
"""


# ---------------------------------------------------------------- 曲线 SVG


def curve_svg(history: list[dict], cfg) -> str:
    width, height = 680, 240
    pad_l, pad_r, pad_t, pad_b = 58, 20, 26, 34

    points = [
        (row["date"], float(row.get("progress_pct") or 0.0), row.get("target_cny"))
        for row in history
        if row.get("date") and row.get("progress_pct") is not None
    ]

    if len(points) < 2:
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
            f'width="{width}" height="{height}" role="img">'
            f'<title>FIRE 进度曲线</title>'
            f'<rect x="0" y="0" width="{width}" height="{height}" fill="none"/>'
            f'<text x="{width / 2}" y="{height / 2}" text-anchor="middle" font-size="13" '
            f'font-family="ui-sans-serif,system-ui,sans-serif" fill="#57606a">'
            f"进度曲线数据积累中（至少需要 2 天记录）</text>"
            f"</svg>"
        )

    points.sort(key=lambda item: item[0])
    y_max = max(p[1] for p in points)
    y_max = y_max * 1.15 if y_max > 0 else 1.0

    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b

    def x_at(index: int) -> float:
        return pad_l + (plot_w * index / (len(points) - 1))

    def y_at(value: float) -> float:
        return pad_t + plot_h * (1 - value / y_max)

    line_pts = [(x_at(i), y_at(v)) for i, (_, v, _t) in enumerate(points)]
    line_path = " ".join(
        f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(line_pts)
    )
    area_path = (
        f"{line_path} L{line_pts[-1][0]:.1f},{pad_t + plot_h:.1f} "
        f"L{line_pts[0][0]:.1f},{pad_t + plot_h:.1f} Z"
    )

    grid: list[str] = []
    for step in range(5):
        ratio = step / 4
        y = pad_t + plot_h * ratio
        grid.append(
            f'<line class="grid" x1="{pad_l}" y1="{y:.1f}" x2="{pad_l + plot_w}" y2="{y:.1f}"/>'
        )
        grid.append(
            f'<text class="fg-muted" x="{pad_l - 8}" y="{y + 4:.1f}" text-anchor="end" '
            f'font-size="10">{y_max * (1 - ratio):.3f}%</text>'
        )

    last_x, last_y = line_pts[-1]

    # 口径调整点：相邻两天的 target_cny 不同，说明 FIRE 目标（分母）变了。
    # 这类台阶不是资产涨跌造成的，必须在图上标出来，否则会被误读。
    marks: list[str] = []
    for i in range(1, len(points)):
        prev_target, cur_target = points[i - 1][2], points[i][2]
        if prev_target is None or cur_target is None or prev_target == cur_target:
            continue
        mx = x_at(i)
        marks.append(
            f'<line class="mark" x1="{mx:.1f}" y1="{pad_t}" '
            f'x2="{mx:.1f}" y2="{pad_t + plot_h:.1f}"/>'
        )
        right = mx > pad_l + plot_w * 0.7
        anchor = "end" if right else "start"
        tx = mx - 4 if right else mx + 4
        marks.append(
            f'<text class="fg-muted" x="{tx:.1f}" y="{pad_t - 9}" '
            f'text-anchor="{anchor}" font-size="9">口径调整</text>'
        )

    note = "竖虚线处为口径调整（FIRE 目标变化），不是资产变动。" if marks else ""
    # 分子（资产构成）变化不会被自动标注——那会在曲线上留一个无标记的跳升，
    # 看起来像一天赚了钱。人工说明写在 config 的 display.capital_change_note。
    extra = str(cfg.display.get("capital_change_note") or "").strip()
    if extra:
        note = f"{note} {extra}".strip()

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-label="FIRE 进度曲线">
  <title>FIRE 进度曲线</title>
  <desc>从 {points[0][0]} 到 {points[-1][0]} 的完成度变化，最新 {points[-1][1]:.3f}%。{note}</desc>
  <defs>
    <linearGradient id="fireArea" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#d97706" stop-opacity="0.30"/>
      <stop offset="100%" stop-color="#d97706" stop-opacity="0.02"/>
    </linearGradient>
    <style>
      .fg-muted {{ fill: #57606a; font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif; }}
      .grid {{ stroke: #d8dee4; stroke-width: 1; stroke-dasharray: 3 4; }}
      .mark {{ stroke: #b9c0c8; stroke-width: 1; stroke-dasharray: 2 3; }}
      .line {{ fill: none; stroke: #d97706; stroke-width: 2; stroke-linejoin: round; stroke-linecap: round; }}
      @media (prefers-color-scheme: dark) {{
        .fg-muted {{ fill: #8b949e; }}
        .grid {{ stroke: #30363d; }}
        .mark {{ stroke: #4d545c; }}
        .line {{ stroke: #f0b429; }}
      }}
    </style>
  </defs>
  {''.join(grid)}
  {''.join(marks)}
  <path d="{area_path}" fill="url(#fireArea)"/>
  <path d="{line_path}" class="line"/>
  <circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="3.5" fill="#d97706"/>
  <text class="fg-muted" x="{pad_l}" y="{height - 12}" font-size="10">{points[0][0]}</text>
  <text class="fg-muted" x="{pad_l + plot_w}" y="{height - 12}" text-anchor="end" font-size="10">{points[-1][0]}</text>
  <text class="fg-muted" x="{last_x:.1f}" y="{last_y - 10:.1f}" text-anchor="end" font-size="11" font-weight="500">{points[-1][1]:.3f}%</text>
</svg>
"""


# ---------------------------------------------------------------- 收益曲线 SVG
#
# 「投入与盈亏」的时序版，两块面板共用一条时间轴：
#   上面板：累计投入（本金）与当前市值，缺口即累计盈亏
#   下面板：累计收益率（盈亏 ÷ 本金），锚定 0%
#
# 为什么两块都要，而不是只画收益率：
#   每次加仓都会让收益率**台阶式下降**——分母（本金）变大、分子（盈亏）不变。
#   只画收益率会让人误以为「收益变差了」，配上本金/市值才看得出那是加仓。
#   反过来，只看金额又看不出「赚了几个点」。上面板回答「多少钱」，下面板回答「几个点」。
#
# 下面板纵轴**含 0**：正负是收益率图的头号信息，锚定 0 才不会被误读。
# 上面板纵轴**不从 0 起**：本金与市值挤在窄区间里，从 0 起缺口会被压成一条看不见的线。


def _nice_axis(lo: float, hi: float, max_ticks: int = 5) -> tuple[float, float, int]:
    """把纵轴取整到「好看的刻度」。

    不取整的话轴标会是 ¥15,402 / ¥14,239 这种读不出来的数字；
    取整到 1 / 2 / 2.5 / 5 × 10^n 的档位后是 ¥11,000 / ¥12,000…，一眼能读。
    区间数不固定，以能完整覆盖数据为准，避免裁掉首尾。
    """
    span = (hi - lo) or max(abs(hi) * 0.02, 1.0)
    raw = span / max_ticks
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    y_lo = math.floor(lo / step) * step
    ticks = max(math.ceil((hi - y_lo) / step), 1)
    return y_lo, y_lo + step * ticks, ticks


def profit_svg(history: list[dict], cfg) -> str:
    width, height = 680, 392
    pad_l, pad_r = 62, 22
    plot_w = width - pad_l - pad_r

    legend_y = 18
    a_title_y, a_top, a_bottom = 42, 52, 188
    b_title_y, b_top, b_bottom = 228, 238, 352
    x_label_y = 374

    rows: list[tuple[str, float, float, float]] = []
    for row in history:
        if not row.get("date"):
            continue
        basis = row.get("basis_cny")
        total = row.get("total_cny")
        if basis is None or total is None or float(basis) <= 0:
            continue
        b, v = float(basis), float(total)
        rows.append((row["date"], b, v, (v - b) / b * 100))

    if len(rows) < 2:
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
            f'width="{width}" height="{height}" role="img">'
            f'<title>FIRE 收益曲线</title>'
            f'<rect x="0" y="0" width="{width}" height="{height}" fill="none"/>'
            f'<text x="{width / 2}" y="{height / 2}" text-anchor="middle" font-size="13" '
            f'font-family="ui-sans-serif,system-ui,sans-serif" fill="#57606a">'
            f"收益曲线数据积累中（至少需要 2 天同时记录了本金与市值）</text>"
            f"</svg>"
        )

    rows.sort(key=lambda item: item[0])
    n = len(rows)

    def x_at(index: int) -> float:
        return pad_l + plot_w * index / (n - 1)

    def polyline(pts: list[tuple[float, float]]) -> str:
        return " ".join(
            f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(pts)
        )

    # ---- 上面板：金额（本金 vs 市值）
    amounts = [v for _, _, v, _ in rows] + [b for _, b, _, _ in rows]
    a_lo, a_hi, a_ticks = _nice_axis(min(amounts), max(amounts), max_ticks=3)
    a_h = a_bottom - a_top

    def ay(value: float) -> float:
        return a_top + a_h * (1 - (value - a_lo) / (a_hi - a_lo))

    basis_pts = [(x_at(i), ay(b)) for i, (_, b, _, _) in enumerate(rows)]
    value_pts = [(x_at(i), ay(v)) for i, (_, _, v, _) in enumerate(rows)]
    gap_path = (
        polyline(value_pts)
        + " "
        + " ".join(f"L{x:.1f},{y:.1f}" for x, y in reversed(basis_pts))
        + " Z"
    )

    # ---- 下面板：收益率（%），纵轴含 0
    rates = [r for _, _, _, r in rows]
    b_lo, b_hi, b_ticks = _nice_axis(min(0.0, min(rates)), max(0.0, max(rates)), max_ticks=5)
    b_h = b_bottom - b_top

    def by(value: float) -> float:
        return b_top + b_h * (1 - (value - b_lo) / (b_hi - b_lo))

    rate_pts = [(x_at(i), by(r)) for i, (_, _, _, r) in enumerate(rows)]
    zero_y = by(0.0)
    rate_path = polyline(rate_pts)
    rate_area = (
        rate_path
        + f" L{rate_pts[-1][0]:.1f},{zero_y:.1f} L{rate_pts[0][0]:.1f},{zero_y:.1f} Z"
    )

    basis_now, value_now, rate_now = rows[-1][1], rows[-1][2], rows[-1][3]
    profit = value_now - basis_now
    gap_class = "gap-up" if profit >= 0 else "gap-down"
    tone_class = "up" if rate_now >= 0 else "down"
    sign = "+" if profit >= 0 else "−"

    grid: list[str] = []
    for i in range(a_ticks + 1):
        value = a_hi - (a_hi - a_lo) * i / a_ticks
        y = a_top + a_h * i / a_ticks
        grid.append(
            f'<line class="grid" x1="{pad_l}" y1="{y:.1f}" x2="{pad_l + plot_w}" y2="{y:.1f}"/>'
        )
        grid.append(
            f'<text class="fg-muted" x="{pad_l - 8}" y="{y + 4:.1f}" text-anchor="end" '
            f'font-size="10">¥{value:,.0f}</text>'
        )
    for i in range(b_ticks + 1):
        value = b_hi - (b_hi - b_lo) * i / b_ticks
        y = b_top + b_h * i / b_ticks
        grid.append(
            f'<line class="grid" x1="{pad_l}" y1="{y:.1f}" x2="{pad_l + plot_w}" y2="{y:.1f}"/>'
        )
        grid.append(
            f'<text class="fg-muted" x="{pad_l - 8}" y="{y + 4:.1f}" text-anchor="end" '
            f'font-size="10">{value:.0f}%</text>'
        )

    last_x, last_y = value_pts[-1]
    last_bx, last_by = basis_pts[-1]
    last_rx, last_ry = rate_pts[-1]

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-label="FIRE 收益曲线">
  <title>FIRE 收益曲线</title>
  <desc>从 {rows[0][0]} 到 {rows[-1][0]}：累计投入 ¥{basis_now:,.2f}、市值 ¥{value_now:,.2f}、累计盈亏 {sign}¥{abs(profit):,.2f}、累计收益率 {rate_now:+.2f}%。上面板为金额（纵轴不从 0 起），下面板为收益率（纵轴含 0）。</desc>
  <style>
    .fg {{ fill: #1f2328; font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif; }}
    .fg-muted {{ fill: #57606a; font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif; }}
    .grid {{ stroke: #d8dee4; stroke-width: 1; stroke-dasharray: 3 4; }}
    .zero {{ stroke: #8c959f; stroke-width: 1.2; }}
    .basis {{ fill: none; stroke: #8c959f; stroke-width: 1.6; stroke-dasharray: 5 4; stroke-linejoin: round; }}
    .value {{ fill: none; stroke: #d97706; stroke-width: 2; stroke-linejoin: round; stroke-linecap: round; }}
    .rate {{ fill: none; stroke: #0969da; stroke-width: 2; stroke-linejoin: round; stroke-linecap: round; }}
    .gap-up {{ fill: #1a7f37; fill-opacity: 0.13; }}
    .gap-down {{ fill: #cf222e; fill-opacity: 0.13; }}
    .rate-up {{ fill: #1a7f37; fill-opacity: 0.13; }}
    .rate-down {{ fill: #cf222e; fill-opacity: 0.13; }}
    .up {{ fill: #1a7f37; }}
    .down {{ fill: #cf222e; }}
    .dot-value {{ fill: #d97706; }}
    .dot-basis {{ fill: #8c959f; }}
    .dot-rate {{ fill: #0969da; }}
    @media (prefers-color-scheme: dark) {{
      .fg {{ fill: #e6edf3; }}
      .fg-muted {{ fill: #8b949e; }}
      .grid {{ stroke: #30363d; }}
      .zero {{ stroke: #6e7681; }}
      .basis {{ stroke: #6e7681; }}
      .value {{ stroke: #f0b429; }}
      .rate {{ stroke: #58a6ff; }}
      .gap-up, .rate-up {{ fill: #3fb950; fill-opacity: 0.16; }}
      .gap-down, .rate-down {{ fill: #f85149; fill-opacity: 0.16; }}
      .up {{ fill: #3fb950; }}
      .down {{ fill: #f85149; }}
      .dot-value {{ fill: #f0b429; }}
      .dot-basis {{ fill: #6e7681; }}
      .dot-rate {{ fill: #58a6ff; }}
    }}
  </style>
  <line class="basis" x1="{pad_l}" y1="{legend_y}" x2="{pad_l + 18}" y2="{legend_y}"/>
  <text class="fg-muted" x="{pad_l + 24}" y="{legend_y}" font-size="11" dominant-baseline="middle">累计投入</text>
  <line class="value" x1="{pad_l + 104}" y1="{legend_y}" x2="{pad_l + 122}" y2="{legend_y}"/>
  <text class="fg-muted" x="{pad_l + 128}" y="{legend_y}" font-size="11" dominant-baseline="middle">当前市值</text>
  <text class="{tone_class}" x="{pad_l + plot_w}" y="{legend_y}" text-anchor="end" font-size="13" font-weight="600" dominant-baseline="middle">累计收益率 {rate_now:+.2f}%</text>
  <text class="fg-muted" x="{pad_l}" y="{a_title_y}" font-size="11" dominant-baseline="middle">金额（元）</text>
  {''.join(grid[: (a_ticks + 1) * 2])}
  <path d="{gap_path}" class="{gap_class}"/>
  <path d="{polyline(basis_pts)}" class="basis"/>
  <path d="{polyline(value_pts)}" class="value"/>
  <circle class="dot-basis" cx="{last_bx:.1f}" cy="{last_by:.1f}" r="3"/>
  <circle class="dot-value" cx="{last_x:.1f}" cy="{last_y:.1f}" r="3.5"/>
  <text class="fg-muted" x="{pad_l}" y="{b_title_y}" font-size="11" dominant-baseline="middle">累计收益率</text>
  {''.join(grid[(a_ticks + 1) * 2 :])}
  <path d="{rate_area}" class="{'rate-up' if rate_now >= 0 else 'rate-down'}"/>
  <line class="zero" x1="{pad_l}" y1="{zero_y:.1f}" x2="{pad_l + plot_w}" y2="{zero_y:.1f}"/>
  <path d="{rate_path}" class="rate"/>
  <circle class="dot-rate" cx="{last_rx:.1f}" cy="{last_ry:.1f}" r="3.5"/>
  <text class="fg-muted" x="{pad_l}" y="{x_label_y}" font-size="10">{rows[0][0]}</text>
  <text class="fg-muted" x="{pad_l + plot_w}" y="{x_label_y}" text-anchor="end" font-size="10">{rows[-1][0]}</text>
</svg>
"""


# ---------------------------------------------------------------- README 区块


def _warnings_block(warnings: list[str]) -> str:
    if not warnings:
        return ""
    lines = ["", "> ⚠️ **数据源告警**", ">"]
    lines += [f"> - {w}" for w in warnings]
    return "\n".join(lines) + "\n"


def _freshness(btc: dict, sp500: dict) -> str:
    """数据新鲜度：明确告诉读者「比特币不是实时数据」。"""
    parts = []
    if btc.get("snapshot_date"):
        stale = btc.get("stale_days")
        age = f"{stale} 天前" if isinstance(stale, int) and stale >= 0 else "—"
        parts.append(f"**比特币快照**：{btc['snapshot_date']}（{age}）")
    if sp500.get("latest_nav_date"):
        parts.append(f"**基金净值日**：{sp500['latest_nav_date']}")
    return "　|　".join(parts)


def _positions_table(positions: list[dict], cfg) -> str:
    if not positions:
        return "_（未读到比特币持仓）_\n"
    masked = cfg.privacy.get("mode") == "masked"
    rows = ["| 账户 | 数量 (BTC) | 均价 (USD) |", "| --- | ---: | ---: |"]
    for pos in positions:
        qty = "已隐藏" if masked else f"{pos['amount']:.8f}".rstrip("0").rstrip(".")
        avg = f"${pos['avg_usd']:,.2f}" if pos.get("avg_usd") else "—"
        rows.append(f"| {pos['venue']} | {qty} | {avg} |")
    return "\n".join(rows) + "\n"


def _life_plan_block(data: dict, cfg) -> str:
    """FIRE 后月开销明细：让「目标资产」的来历可追溯。

    分两层展示，避免「分类行和明细行长得一样、只靠加粗区分」：
      1. 分类汇总表 —— 先看清钱花在哪几个大类、各占多少
      2. 每类一张独立小表 —— 分类名单独成行，不再混进表格当行

    这里的金额不做隐私遮蔽——它是未来生活预算，不是持仓金额。
    """
    plan = data.get("life_plan")
    if not plan or not plan.get("groups"):
        return ""

    total = plan["monthly_expense"] or 1
    n_items = sum(len(g["items"]) for g in plan["groups"])
    out: list[str] = []

    title = plan.get("headline") or plan.get("profile") or "生活规划"
    out.append("<details>")
    out.append(f"<summary>FIRE 后月开销明细 · {title}</summary>")
    out.append("")
    out.append(f"共 **{n_items} 项**，合计 **{money(plan['monthly_expense'], cfg)}/月**。")
    out.append("")

    out.append("**分类汇总**")
    out.append("")
    out.append("| 分类 | 月支出 | 占比 |")
    out.append("| --- | ---: | ---: |")
    for group in plan["groups"]:
        out.append(
            f"| {group['group']} | {money(group['subtotal'], cfg)} | "
            f"{group['subtotal'] / total * 100:.1f}% |"
        )
    out.append(f"| **合计** | **{money(plan['monthly_expense'], cfg)}** | 100.0% |")
    out.append("")

    out.append("**逐项明细**")
    out.append("")
    for group in plan["groups"]:
        share = group["subtotal"] / total * 100
        out.append(
            f"**{group['group']}** · {money(group['subtotal'], cfg)}/月 · 占 {share:.1f}%"
        )
        out.append("")
        out.append("| 项目 | 月支出 | 占总计 |")
        out.append("| --- | ---: | ---: |")
        for item in group["items"]:
            out.append(
                f"| {item['label']} | {money(item['monthly'], cfg)} | "
                f"{item['monthly'] / total * 100:.1f}% |"
            )
        out.append("")

    labor = plan.get("labor_income")
    if labor:
        out.append(f"**兼职收入** · {labor['label']}")
        out.append("")
        out.append(
            f"{labor['hourly_wage']} 元/小时 × 每周 {labor['hours_per_week']:.0f} 小时"
            f" = {labor['hours_per_month']:.1f} 小时/月"
            f"（{labor['work_days_per_month']:.1f} 个工作日）"
        )
        out.append("")
        out.append("| 项目 | 金额 |")
        out.append("| --- | ---: |")
        out.append(f"| 毛收入 | {money(labor['gross_monthly_cny'], cfg)} |")
        out.append(f"| 减：交通（往返公交） | −{money(labor['transport_cny'], cfg)} |")
        out.append(f"| 减：餐食增量 | −{money(labor['meal_cny'], cfg)} |")
        out.append(f"| 减：装备摊销 | −{money(labor['gear_cny'], cfg)} |")
        out.append(f"| **净收入** | **{money(labor['net_monthly_cny'], cfg)}** |")
        out.append("")
        out.append(
            f"> 组合需要覆盖：{money(plan['monthly_expense'], cfg)} − "
            f"{money(labor['net_monthly_cny'], cfg)} = "
            f"**{money(plan['net_monthly_expense'], cfg)}/月**。"
        )
        out.append(">")
        out.append(
            "> 只扣上班多出来的开销：餐食算的是「在外面吃比在家做贵多少」，不是整顿饭钱，"
            "家里那顿已经算在食品里，全额扣等于把生活费算两遍。"
        )
        if labor.get("effective_hourly_cny"):
            out.append(">")
            out.append(
                f"> 通勤 {labor['commute_hours_per_day']:.1f} 小时不算工资，但要占时间："
                f"每月实际占用 {labor['occupied_hours_per_month']:.1f} 小时，"
                f"等效时薪 {money(labor['effective_hourly_cny'], cfg)}"
                f"（名义净时薪 {money(labor['net_hourly_cny'], cfg)}）。"
            )
        out.append("")

    if plan.get("override"):
        out.append(
            f"> ⚠️ 当前为**手工覆盖值**（`fire.monthly_expense`），"
            f"逐项预算推导值为 {money(plan.get('derived_monthly_expense'), cfg)}。"
        )
        out.append("")

    if plan.get("one_off"):
        out.append("**一次性支出**（不进入 FIRE 目标，落地那年发生一次）：")
        out.append("")
        out.append("| 项目 | 金额 |")
        out.append("| --- | ---: |")
        for row in plan["one_off"]:
            out.append(f"| {row['label']} | {money(row['amount'], cfg)} |")
        out.append(f"| **合计** | **{money(plan['one_off_total'], cfg)}** |")
        out.append("")

    formula = (
        "`FIRE 目标 = (月开销 − 兼职净收入) × 12 ÷ 提取率`"
        if labor
        else "`FIRE 目标 = 月开销 × 12 ÷ 提取率`"
    )
    out.append(
        f"> 月开销 = 上面各项相加；{formula}。"
        "每项的依据见 [config.yaml](config.yaml) 和 "
        "[docs/FIRE-LIFE-PLAN.md](docs/FIRE-LIFE-PLAN.md)。"
    )
    out.append(">")
    out.append(
        "> 一次性支出不摊进月开销：它不产生持续现金流，摊进去会同时抬高月开销和目标。"
    )
    if plan.get("target_with_one_off"):
        out.append(">")
        out.append(
            f"> 加上一次性支出，总共需要 **{money(plan['target_with_one_off'], cfg)}**。"
        )
    out.append("")
    out.append("</details>")
    out.append("")
    return "\n".join(out)


def _passive_income_block(data: dict, cfg) -> str:
    """每小时被动收入 = 当前持仓 × 预期年化回报 ÷ 8760。

    这一节的重点不是那个数字，而是它的边界，两句话必须跟着数字一起出现：
      1. 它是**假设**推出来的——换一组假设，加权年化能从 0.1% 摆到 24%；
      2. 它和提取率**不是一回事**——预期回报是「平均能涨多少」，
         提取率是「能安全花多少」，把前者当后者用会在第一个熊市击穿本金。
    否则读者只会记住那个偏大的数。
    """
    pi = data.get("passive_income")
    if not pi or not pi.get("assets"):
        return ""

    rows = pi["assets"]
    hourly = pi["hourly_cny"]
    rate = pi["weighted_rate"] or 0.0

    out: list[str] = []
    out.append("### 每小时被动收入")
    out.append("")
    out.append("| 资产 | 市值 | 权重 | 预期年化 | 每小时 |")
    out.append("| --- | ---: | ---: | ---: | ---: |")
    for row in rows:
        out.append(
            f"| {row['label']} | {money(row['value_cny'], cfg)} | "
            f"{row['weight'] * 100:.1f}% | {row['rate'] * 100:.1f}% | "
            f"{money(row['hourly_cny'], cfg, decimals=3)} |"
        )
    out.append(
        f"| **合计** | **{money(pi['total_value_cny'], cfg)}** | 100.0% | "
        f"**{rate * 100:.1f}%** | **{money(hourly, cfg, decimals=3)}** |"
    )
    out.append("")
    out.append(
        f"换算：每小时 **{money(hourly, cfg, decimals=2)}** · "
        f"每天 **{money(pi['daily_cny'], cfg)}** · "
        f"每月 **{money(pi['monthly_cny'], cfg)}** · "
        f"每年 **{money(pi['annual_cny'], cfg)}**"
    )
    out.append("")
    if pi.get("coverage") is not None:
        out.append(
            f"> 按当前持仓，这笔被动收入相当于月开销的 **{pi['coverage'] * 100:.1f}%**"
            f"（月开销 {money(pi['monthly_expense'], cfg)}）。"
        )
        out.append(">")

    out.append(
        "> 这是按假设算出来的数，不是承诺。"
        f"加权年化 {rate * 100:.1f}% 由各资产按市值加权得到，假设写在 "
        "`config.yaml` 的 `expected_return` 段，改它不影响 FIRE 目标。"
    )
    out.append(">")

    low_desc = "、".join(
        f"{r['label']} {r['rate_low'] * 100:.0f}%" for r in rows if r.get("rate_low") is not None
    )
    high_desc = "、".join(
        f"{r['label']} {r['rate_high'] * 100:.0f}%" for r in rows if r.get("rate_high") is not None
    )
    if pi.get("hourly_low_cny") is not None and pi.get("hourly_high_cny") is not None:
        # 权重要现算，不能写死——仓位结构一变，这句解释就跟着错。
        top = max(rows, key=lambda r: r["weight"])
        if top["weight"] >= 0.8:
            why = (
                f"因为 **{top['weight'] * 100:.0f}% 的仓位压在{top['label']}上**，"
                "这个数字的软肋是权重，不是回报率。"
            )
        else:
            why = (
                "因为各资产的回报率假设本身就宽：比特币没有可锚定的现金流，"
                "长期回报率只能猜。"
            )
        out.append(
            f"> 区间跨度大：悲观（{low_desc}）每小时 "
            f"{money(pi['hourly_low_cny'], cfg, decimals=3)}，乐观（{high_desc}）"
            f"{money(pi['hourly_high_cny'], cfg, decimals=3)}。{why}"
        )
        out.append(">")

    out.append(
        f"> 也别把 {rate * 100:.1f}% 当成能花的钱。预期回报是「平均能涨多少」，"
        f"提取率是「能安全花多少」：按 {pi['withdrawal_rate'] * 100:.1f}% 提取率算，"
        f"同样这笔资产每小时 {money(pi['hourly_at_withdrawal_cny'], cfg, decimals=3)}、"
        f"每月 {money(pi['monthly_at_withdrawal_cny'], cfg)}。"
    )
    out.append(">")
    out.append(
        "> 差额是给波动留的：平均回报为正，但路径上先腰斩一次，"
        "按平均回报安排支出就会在中途卖掉筹码。比特币单年 ±50% 是常态，两个数要一起看。"
    )
    out.append("")
    return "\n".join(out)


def render_block(data: dict, cfg, history: list[dict]) -> str:
    fire = data["fire"]
    assets = data["assets"]
    btc = assets["btc"]
    sp500 = assets["sp500"]
    ndx100 = assets.get("ndx100") or {}
    pct = assets["progress_pct"]
    masked = cfg.privacy.get("mode") == "masked"

    out: list[str] = []
    out.append(START_MARK)
    out.append("")

    out.append(f"**更新时间**：{data['as_of'].replace('T', ' ')}")
    out.append("")
    freshness = _freshness(btc, sp500)
    if freshness:
        out.append(freshness)
        out.append("")

    # 进度曲线放在最上方（元信息之后、完成度条之前）：
    # 它同时回答「现在到哪了」和「是怎么走到这里的」，右端还标着当前百分比，
    # 是这一页信息量最大的一张图，值得第一眼就看到。
    # 完成度条只回答「现在到哪了」，退到它后面当补充。
    # 收益曲线（金额 + 收益率）涉及本金，逻辑上属于「投入与盈亏」，仍留在那一节。
    if cfg.display.get("show_curve") and history:
        out.append("### 进度曲线")
        out.append("")
        out.append("![FIRE 进度曲线](reports/curve.svg)")
        out.append("")
        out.append(
            "> 每个点是当天的完成度原值，按 `data/history.json` 连线，不回填、不重算。"
        )
        out.append(">")
        out.append(
            "> 竖虚线是口径调整日：那天 FIRE 目标变了，曲线因此出现台阶。"
            "目标值逐日记在 `data/history.json` 里，可以查到。"
        )
        cap_note = str(cfg.display.get("capital_change_note") or "").strip()
        if cap_note:
            out.append(">")
            out.append(
                f"> ⚠️ **分子口径也有过变化**，但不会画竖线（竖线只标分母）：{cap_note}"
                "纳入后分子变大、进度跳升，那不是资产增长。"
            )
        out.append("")

    if cfg.display.get("show_progress_bar", True):
        out.append("![FIRE 完成度](reports/progress.svg)")
        out.append("")
        out.append(
            "> 完成度 = 当前资产 ÷ FIRE 目标。资产随行情走，目标随口径走；"
            "月开销、提取率或兼职收入改一项，百分比就会变，未必是资产涨跌。"
        )
        out.append("")

    out.append("| 指标 | 数值 |")
    out.append("| --- | ---: |")
    out.append(f"| 🎯 FIRE 目标资产 | {money(fire['target_cny'], cfg)} |")
    labor = fire.get("labor_income")
    if labor:
        out.append(f"| ☕ 兼职净收入（月） | {money(labor['net_monthly_cny'], cfg)} |")
        out.append(f"| 🧾 组合需覆盖（月） | {money(fire['net_monthly_expense'], cfg)} |")
    out.append(f"| 💰 当前资产 | {money(assets['total_cny'], cfg)} |")
    out.append(f"| 📈 完成度 | **{pct:.3f}%** |")
    out.append(f"| ⏳ 距离目标 | {money(assets['remaining_cny'], cfg)} |")
    pi = data.get("passive_income")
    if pi:
        out.append(
            f"| ⏱️ 每小时被动收入（按预期年化） | {money(pi['hourly_cny'], cfg, decimals=2)} |"
        )
    out.append("")

    if cfg.display.get("show_life_plan", True):
        plan_block = _life_plan_block(data, cfg)
        if plan_block:
            out.append(plan_block.strip())
            out.append("")

    out.append("### 资产构成")
    out.append("")
    out.append("| 资产 | 市值 | 占比 |")
    out.append("| --- | ---: | ---: |")
    total = assets["total_cny"] or 1
    btc_share = btc["value_cny"] / total * 100 if assets["total_cny"] else 0.0
    sp_share = sp500["value_cny"] / total * 100 if assets["total_cny"] else 0.0
    ndx_share = ndx100.get("value_cny", 0.0) / total * 100 if assets["total_cny"] else 0.0
    out.append(f"| 比特币 | {money(btc['value_cny'], cfg)} | {btc_share:.1f}% |")
    out.append(f"| 标普500基金 | {money(sp500['value_cny'], cfg)} | {sp_share:.1f}% |")
    if ndx100.get("value_cny"):
        out.append(f"| 纳指100基金 | {money(ndx100['value_cny'], cfg)} | {ndx_share:.1f}% |")
    out.append(f"| **合计** | **{money(assets['total_cny'], cfg)}** | 100.0% |")
    out.append("")
    out.append(
        "> 只算长期不动用的钱：比特币、标普500基金、纳指100基金。日常现金和活期不算。"
        "所以卖出后进度下跌未必是亏了，可能只是钱变成了现金，详见下方「计入范围」。"
    )
    out.append("")

    if not masked and btc["qty"]:
        out.append(
            f"比特币计价：**{btc['qty']:.8f} BTC** × {money(btc['price_cny'], cfg)} = "
            f"{money(btc['value_cny'], cfg)}"
        )
        out.append("")
    if btc["positions"]:
        out.append("<details>")
        out.append(f"<summary>比特币持仓明细（快照 {btc.get('snapshot_date') or '—'}，手动更新）</summary>")
        out.append("")
        out.append(_positions_table(btc["positions"], cfg))
        out.append("</details>")
        out.append("")

    if sp500.get("funds"):
        out.append("<details>")
        out.append("<summary>标普500基金持仓明细</summary>")
        out.append("")
        out.append("| 基金 | 市值 | 累计投入 | 持有份额 | 最新净值 |")
        out.append("| --- | ---: | ---: | ---: | ---: |")
        for fund in sp500["funds"]:
            out.append(
                f"| {fund['short_name']} | {money(fund['market_value'], cfg)} | "
                f"{money(fund['invested'], cfg)} | {fund['shares']:.2f} | {fund['latest_nav']:.4f} |"
            )
        out.append("")
        out.append("</details>")
        out.append("")

    if ndx100.get("funds"):
        out.append("<details>")
        out.append(
            f"<summary>纳指100基金持仓明细（净值日 {ndx100.get('latest_nav_date') or '—'}，"
            "份额固定，已停止定投）</summary>"
        )
        out.append("")
        out.append("| 基金 | 市值 | 累计投入 | 持有份额 | 最新净值 |")
        out.append("| --- | ---: | ---: | ---: | ---: |")
        for fund in ndx100["funds"]:
            out.append(
                f"| {fund.get('short_name') or fund.get('code')} | "
                f"{money(fund['market_value'], cfg)} | "
                f"{money(fund['invested'], cfg)} | {fund['shares']:.2f} | "
                f"{fund['latest_nav']:.4f} |"
            )
        out.append("")
        out.append("</details>")
        out.append("")

    basis = data.get("cost_basis") or {}
    if basis.get("total_cny") is not None:
        out.append("### 投入与盈亏")
        out.append("")
        out.append("| 指标 | 数值 |")
        out.append("| --- | ---: |")
        out.append(f"| 累计投入本金 | {money(basis['total_cny'], cfg)} |")
        out.append(f"| 当前市值 | {money(assets['total_cny'], cfg)} |")
        out.append(f"| 累计盈亏 | {money(basis['profit_cny'], cfg)} |")
        basis_total = float(basis.get("total_cny") or 0)
        profit_total = float(basis.get("profit_cny") or 0)
        rate_txt = f"{profit_total / basis_total * 100:+.2f}%" if basis_total else "—"
        out.append(f"| **累计收益率** | **{rate_txt}** |")
        out.append("")
        if basis.get("btc_estimated"):
            out.append(
                "> 比特币本金按持仓备注的「均价 $xx/BTC」推算，用当前汇率折成人民币，"
                "和真实买入成本有偏差；标普500本金取 sp500-dca 的累计投入。"
            )
            out.append("")

        curve_pts = sum(1 for r in history if r.get("basis_cny") is not None)
        if cfg.display.get("show_profit_curve", True) and curve_pts >= 2:
            first_day = next(r["date"] for r in history if r.get("basis_cny") is not None)
            out.append("### 收益曲线")
            out.append("")
            out.append("![FIRE 收益曲线](reports/profit.svg)")
            out.append("")
            out.append(
                "> 上面板：累计投入（虚线）和市值（实线），缺口就是盈亏。"
                "下面板：累计收益率，纵轴含 0。"
            )
            out.append(">")
            out.append(
                "> 加仓会让收益率下降，因为本金变大、盈亏不变。所以收益率掉了不一定是亏，"
                "可能只是又投了一笔。上面板能看出本金哪天跳升。"
            )
            out.append(">")
            out.append(
                "> 上面板纵轴不从 0 起，否则缺口会被压成一条线，斜率也不代表涨跌幅。"
                "下面板含 0，正负可以直接读。"
            )
            out.append(">")
            out.append(
                f"> 起点 {first_day}。早期数据由两个持仓仓库的历史文件重建，"
                "比特币统一按当前汇率折算，绝对值和真实本金有误差，趋势可信；"
                "之后每天由 Actions 记录。"
            )
            out.append("")

    # 被动收入与线性外推都是「往前看」的内容，放在一起。
    # 被动收入在**前**：它是当前持仓的直接推论，比外推更硬；
    # 外推依赖「近期增速会延续」这个更弱的假设。
    pi_block = _passive_income_block(data, cfg)
    if pi_block:
        out.append(pi_block.strip())
        out.append("")

    proj = data.get("projection")
    if proj:
        out.append("### 线性外推")
        out.append("")
        days = proj.get("days_to_target")
        if days:
            if days < 365:
                horizon = f"**约 {days} 天**"
            elif days < 3650:
                horizon = f"**约 {days / 365:.1f} 年**"
            else:
                horizon = "**超过 10 年**"
            out.append(
                f"按真实定投额线性外推：比特币 **{money(proj['btc_cny_per_day'], cfg)}/天**"
                f"（{proj['btc_usdt_per_day']:g} USDT × {proj['usd_cny']:.4f}）"
                f" + 标普500 **{money(proj['sp500_cny_per_day'], cfg)}/天**"
                f" = 合计 **{money(proj['daily_cny'], cfg)}/天**"
                f"（月 {money(proj['monthly_cny'], cfg)}），{horizon}后达到目标（{proj['eta']}）。"
            )
            out.append("")
            out.append(
                "> 只算投入，不算涨跌：假设定投不中断、价格不变。所以这个数是「还要投多久」，"
                "不是「多久能涨到」——行情好会更快，行情差会更慢。"
            )
            out.append(">")
            out.append(
                "> 不用近 30 天增速的原因：那段增速由行情主导，涨得快不等于进度快，"
                "跌的时候甚至会被推成「永远达不到」。定投额才是自己能控制的变量。"
            )
            if days >= 3650:
                out.append(">")
                out.append("> 在这个尺度上外推结果已无参考意义——真正决定进度的是月定投额，不是等待。")
        else:
            out.append(f"暂不可外推：{proj.get('reason') or '数据不足'}")
        out.append("")

    warn_block = _warnings_block(data.get("warnings", []))
    if warn_block:
        out.append(warn_block.strip())
        out.append("")

    out.append(
        f"<sub>数据源："
        f"[{cfg.sources.btc.repo}](https://github.com/{cfg.sources.btc.repo})（比特币持仓，每周手动更新）、"
        f"[{cfg.sources.sp500.repo}](https://github.com/{cfg.sources.sp500.repo})（标普500 持仓）、"
        f"东方财富（纳指100 净值，份额固定）· "
        f"行情：{data['price']['btc_source']} · 汇率：{data['price']['fx_source']}</sub>"
    )
    out.append("")
    out.append(END_MARK)
    return "\n".join(out) + "\n"


def merge_readme(existing: str, block: str) -> str:
    """把生成区块替换进 README，保留人工撰写的内容。"""
    if START_MARK in existing and END_MARK in existing:
        head = existing.split(START_MARK)[0]
        tail = existing.split(END_MARK, 1)[1].lstrip("\n")
        return f"{head}{block}\n{tail}" if tail else f"{head}{block}"
    return existing.rstrip() + "\n\n" + block


def default_readme(
    block: str, cfg, monthly: float, net_monthly: float | None = None
) -> str:
    rate = float(cfg.fire.withdrawal_rate)
    # 组合需覆盖 = 月开销 − 兼职净收入。没传就退回全部月开销，与旧口径一致。
    net = monthly if net_monthly is None else net_monthly
    return f"""# FIRE-Progress

> 我的 FIRE 进度看板。只统计三项长期不动用的资产：比特币、标普500基金、纳指100基金。
> 持仓来自两个公开仓库 + 东方财富的公开净值接口，由 GitHub Actions 每小时更新，不需要任何密钥。

{block}
## 计算口径

| 参数 | 取值 |
| --- | ---: |
| 月开销 | ¥{monthly:,.0f} |
| 组合需覆盖（月开销 − 兼职净收入） | ¥{net:,.0f} |
| 提取率 | {rate * 100:.1f}% |
| **FIRE 目标资产** | **¥{net * 12 / rate:,.2f}** |

公式：`FIRE 目标 = 组合需覆盖 × 12 ÷ 提取率`，`完成度 = 当前资产 ÷ FIRE 目标`。
组合需覆盖 = 月开销 − 兼职净收入（咖啡师 FIRE，见 `fire.labor_income`；关掉就退回传统 FIRE）。
月开销由 [config.yaml](config.yaml) 的 `life_plan` 逐项推导，依据见
[docs/FIRE-LIFE-PLAN.md](docs/FIRE-LIFE-PLAN.md)。

## 计入范围

- ✅ [0.1BTC](https://github.com/{cfg.sources.btc.repo}) 仓库中的比特币持仓
- ✅ [sp500-dca](https://github.com/{cfg.sources.sp500.repo}) 仓库中的标普500基金市值
- ❌ 日常现金、活期存款、其他币种、其他一切资产

划线的标准是「长期不动用」，不是「能不能变现」。日常现金要随时周转，所以不算。

由此有个推论：卖出资产不会让进度失真，卖出后钱离开这个范围才会。

| 情形 | 进度 | 是否真实 |
| --- | --- | --- |
| 工资入金 / 买入 | ↑ | 真实增长 |
| 池内互换（卖 BTC 买标普500） | → 不变 | 正常 |
| 卖出后把钱花掉 | ↓ | 真实减少 |
| 卖出后变成现金放着 | ↓ | 假信号：资产没少，只是换了形式 |

> 看到进度下跌，先看钱去哪了。变成现金的话，那是口径边界，不是资产减少。

## 数据节奏

- **比特币持仓**：在 [0.1BTC](https://github.com/{cfg.sources.btc.repo}) 仓库里**每周手动更新一次**，
  数量有延迟，不是实时数据；市值仍按最新行情折算。
- **标普500基金**：QDII 净值通常 T+1 晚间披露，周末和节假日没有净值，
  看板可能连续 2~3 天没有新提交，属正常。

---

*本仓库为个人资产记录，不构成任何投资建议。数据为个人口径，可能与实际存在偏差。*
"""
