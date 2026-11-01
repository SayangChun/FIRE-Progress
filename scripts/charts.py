"""图表渲染：进度条、进度曲线、收益曲线。

所有输出都是纯字符串拼接，不依赖绘图库——CI 里少一个依赖就少一个故障点。
"""

from __future__ import annotations

import math

from .fmt import money


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


# ---------------------------------------------------------------- 双线进度条


def dual_progress_svg(data: dict, cfg) -> str | None:
    """双线进度条：出发门槛 / 不工作门槛。没有 departure 数据时返回 None。

    为什么是两条
    ------------
    2026-10-31 起，阶段 A 有全职工作，现金流为正，
    「攒够 ¥205,953 才能走」不再成立——那是「靠资产覆盖净支出」的永续要求。

    真正卡住出发的是三笔钱（医疗应急 + 搬家 + 空窗），
    而 ¥205,953 回答的是另一个问题：能不能不工作。

    两条线画在同一张图里，是为了避免任何一条被当成「唯一标准」：
    只看上面那条会以为「到了就能躺平」，只看下面那条会以为「永远走不了」。
    """
    dep = data.get("departure")
    if not dep:
        return None

    assets = data["assets"]
    fire = data["fire"]
    cur = float(assets.get("total_cny") or 0.0)

    rows = [
        ("出发门槛", float(dep["low_cny"]), float(dep.get("progress_low") or 0.0), "#2563eb", "#60a5fa"),
        ("不工作门槛", float(fire["target_cny"]), float(assets.get("progress") or 0.0), "#d97706", "#f0b429"),
    ]

    width, height = 680, 140
    track_h = 10
    parts: list[str] = []
    for i, (name, target, ratio, color, color_dark) in enumerate(rows):
        top = 8 + i * 62
        ratio = max(min(ratio, 1.0), 0.0)
        pct = ratio * 100
        fill_w = max(width * ratio, 1.0) if ratio > 0 else 0.0
        fill_r = min(track_h / 2, fill_w / 2) if fill_w else 0.0
        remain = max(target - cur, 0.0)
        cls = "fill-a" if i == 0 else "fill-b"
        parts.append(
            f'  <text class="fg-muted" x="0" y="{top + 12}" font-size="12">{name}</text>\n'
            f'  <text class="fg" x="{width}" y="{top + 14}" text-anchor="end" font-size="18" font-weight="600">{pct:.1f}%</text>\n'
            f'  <rect class="track" x="0" y="{top + 24}" width="{width}" height="{track_h}" rx="{track_h / 2}"/>\n'
            f'  <rect class="{cls}" x="0" y="{top + 24}" width="{fill_w:.1f}" height="{track_h}" rx="{fill_r:.1f}"/>\n'
            f'  <text class="fg-muted" x="0" y="{top + 52}" font-size="11">目标 {money(target, cfg)}</text>\n'
            f'  <text class="fg-muted" x="{width}" y="{top + 52}" text-anchor="end" font-size="11">'
            f'已积累 {money(cur, cfg)} · 还差 {money(remain, cfg)}</text>'
        )

    body = "\n".join(parts)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-label="出发门槛与不工作门槛的双线进度">
  <title>出发门槛 {rows[0][2] * 100:.1f}% · 不工作门槛 {rows[1][2] * 100:.1f}%</title>
  <desc>两条线回答两个不同问题：出发门槛 {money(rows[0][1], cfg)}（能不能走），不工作门槛 {money(rows[1][1], cfg)}（能不能不工作）。当前资产 {money(cur, cfg)}。</desc>
  <style>
    .fg {{ fill: #1f2328; font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif; }}
    .fg-muted {{ fill: #57606a; font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif; }}
    .track {{ fill: #e7ebef; }}
    .fill-a {{ fill: #2563eb; }}
    .fill-b {{ fill: #d97706; }}
    @media (prefers-color-scheme: dark) {{
      .fg {{ fill: #e6edf3; }}
      .fg-muted {{ fill: #8b949e; }}
      .track {{ fill: #21262d; }}
      .fill-a {{ fill: #60a5fa; }}
      .fill-b {{ fill: #f0b429; }}
    }}
  </style>
{body}
</svg>
"""


# ---------------------------------------------------------------- 曲线 SVG


def curve_svg(history: list[dict], cfg, departure_cny: float | None = None) -> str:
    """进度曲线：两条线，回答两个不同问题。

    - **不工作门槛**完成度 = 资产 ÷ FIRE 目标（`target_cny`，逐日留档）
    - **出发门槛**完成度   = 资产 ÷ 出发门槛（`departure_cny`，2026-10-31 起）

    为什么画两条
    ------------
    阶段 A 有工作后，「攒够 ¥205,953 才能走」不再成立。两条线的距离就是
    「离能走还有多远」与「离能不工作还有多远」的差——只画一条会把两者混成一个数。

    ⚠️ 出发门槛是 2026-10-31 才定义的概念，此前的记录里没有 `departure_cny`，
    这段按**当前门槛**折算，不是当时记录的值。图注里会写明。
    门槛只由医疗应急、搬家、月开销决定，不含行情，所以折算段是一条平滑线；
    而 FIRE 目标逐日留档，因此有台阶——**两条线形状的差异本身就是信息**。
    """
    width, height = 680, 262
    pad_l, pad_r, pad_t, pad_b = 58, 62, 48, 34

    rows: list[dict] = []
    for row in history:
        if not row.get("date") or row.get("progress_pct") is None:
            continue
        total = float(row.get("total_cny") or 0.0)
        gate = row.get("departure_cny") or departure_cny
        rows.append(
            {
                "date": row["date"],
                "target": row.get("target_cny"),
                "fire": float(row["progress_pct"]),
                "dep": (total / float(gate) * 100.0) if gate else None,
            }
        )

    if len(rows) < 2:
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
            f'width="{width}" height="{height}" role="img">'
            f'<title>进度曲线</title>'
            f'<rect x="0" y="0" width="{width}" height="{height}" fill="none"/>'
            f'<text x="{width / 2}" y="{height / 2}" text-anchor="middle" font-size="13" '
            f'font-family="ui-sans-serif,system-ui,sans-serif" fill="#57606a">'
            f"进度曲线数据积累中（至少需要 2 天记录）</text>"
            f"</svg>"
        )

    rows.sort(key=lambda r: r["date"])
    has_dep = all(r["dep"] is not None for r in rows)
    # 出发门槛折算的起点：第一条自带 departure_cny 的记录（没有则视为全程折算）
    derived_from = next(
        (r["date"] for r in history if r.get("departure_cny")), None
    )

    values = [r["fire"] for r in rows]
    if has_dep:
        values += [r["dep"] for r in rows]
    y_max = max(values) if values else 0.0
    y_max = y_max * 1.15 if y_max > 0 else 1.0

    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b

    def x_at(i: int) -> float:
        return pad_l + (plot_w * i / (len(rows) - 1))

    def y_at(v: float) -> float:
        return pad_t + plot_h * (1 - v / y_max)

    def path_of(key: str) -> tuple[str, tuple[float, float] | None]:
        pts = [(x_at(i), y_at(r[key])) for i, r in enumerate(rows) if r[key] is not None]
        if not pts:
            return "", None
        d = " ".join(
            f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(pts)
        )
        return d, pts[-1]

    fire_path, fire_end = path_of("fire")
    dep_path, dep_end = path_of("dep") if has_dep else ("", None)

    grid: list[str] = []
    for step in range(5):
        ratio = step / 4
        y = pad_t + plot_h * ratio
        grid.append(
            f'<line class="grid" x1="{pad_l}" y1="{y:.1f}" x2="{pad_l + plot_w}" y2="{y:.1f}"/>'
        )
        grid.append(
            f'<text class="fg-muted" x="{pad_l - 8}" y="{y + 4:.1f}" text-anchor="end" '
            f'font-size="10">{y_max * (1 - ratio):.2f}%</text>'
        )

    # 口径调整点：相邻两天的 target_cny 不同，说明 FIRE 目标（分母）变了。
    # 这类台阶不是资产涨跌造成的，必须在图上标出来，否则会被误读。
    # 出发门槛只在月开销变化时才动，历史上没有对应的台阶可标。
    marks: list[str] = []
    for i in range(1, len(rows)):
        prev_t, cur_t = rows[i - 1]["target"], rows[i]["target"]
        if prev_t is None or cur_t is None or prev_t == cur_t:
            continue
        mx = x_at(i)
        marks.append(
            f'<line class="mark" x1="{mx:.1f}" y1="{pad_t}" '
            f'x2="{mx:.1f}" y2="{pad_t + plot_h:.1f}"/>'
        )

    legend = (
        f'<rect x="{pad_l}" y="12" width="10" height="10" rx="2" fill="#2563eb"/>'
        f'<text class="fg-muted" x="{pad_l + 16}" y="21" font-size="11">出发门槛</text>'
        f'<rect x="{pad_l + 86}" y="12" width="10" height="10" rx="2" fill="#d97706"/>'
        f'<text class="fg-muted" x="{pad_l + 102}" y="21" font-size="11">不工作门槛</text>'
    )

    end_labels = ""
    if fire_end:
        end_labels += (
            f'<circle cx="{fire_end[0]:.1f}" cy="{fire_end[1]:.1f}" r="3.5" fill="#d97706"/>'
            f'<text class="fg-muted" x="{fire_end[0] + 7:.1f}" y="{fire_end[1] + 4:.1f}" '
            f'font-size="11" font-weight="500" fill="#d97706">{rows[-1]["fire"]:.2f}%</text>'
        )
    if dep_end:
        end_labels += (
            f'<circle cx="{dep_end[0]:.1f}" cy="{dep_end[1]:.1f}" r="3.5" fill="#2563eb"/>'
            f'<text class="fg-muted" x="{dep_end[0] + 7:.1f}" y="{dep_end[1] + 4:.1f}" '
            f'font-size="11" font-weight="500" fill="#2563eb">{rows[-1]["dep"]:.2f}%</text>'
        )

    note = "竖虚线处为 FIRE 目标变化（分母变了），不是资产变动。"
    if has_dep and derived_from:
        note += (
            f" 出发门槛自 {derived_from} 起逐日记录，之前按当前门槛折算，"
            "因此那一段是平滑线——它不是历史记录，是反事实。"
        )
    extra = str(cfg.display.get("capital_change_note") or "").strip()
    if extra:
        note = f"{note} {extra}".strip()

    dep_desc = f"，出发门槛 {rows[-1]['dep']:.2f}%" if has_dep else ""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-label="进度曲线：出发门槛与不工作门槛">
  <title>进度曲线：出发门槛与不工作门槛</title>
  <desc>从 {rows[0]['date']} 到 {rows[-1]['date']}，不工作门槛完成度 {rows[-1]['fire']:.2f}%{dep_desc}。{note}</desc>
  <defs>
    <style>
      .fg-muted {{ fill: #57606a; font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif; }}
      .grid {{ stroke: #d8dee4; stroke-width: 1; stroke-dasharray: 3 4; }}
      .mark {{ stroke: #b9c0c8; stroke-width: 1; stroke-dasharray: 2 3; }}
      .line-dep {{ fill: none; stroke: #2563eb; stroke-width: 2; stroke-linejoin: round; stroke-linecap: round; }}
      .line-fire {{ fill: none; stroke: #d97706; stroke-width: 2; stroke-linejoin: round; stroke-linecap: round; }}
      @media (prefers-color-scheme: dark) {{
        .fg-muted {{ fill: #8b949e; }}
        .grid {{ stroke: #30363d; }}
        .mark {{ stroke: #4d545c; }}
        .line-dep {{ stroke: #60a5fa; }}
        .line-fire {{ stroke: #f0b429; }}
      }}
    </style>
  </defs>
  {legend}
  {''.join(grid)}
  {''.join(marks)}
  {f'<path d="{dep_path}" class="line-dep"/>' if dep_path else ''}
  <path d="{fire_path}" class="line-fire"/>
  {end_labels}
  <text class="fg-muted" x="{pad_l}" y="{height - 12}" font-size="10">{rows[0]['date']}</text>
  <text class="fg-muted" x="{pad_l + plot_w}" y="{height - 12}" text-anchor="end" font-size="10">{rows[-1]['date']}</text>
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
