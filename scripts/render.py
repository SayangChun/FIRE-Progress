"""README 与 SVG 曲线渲染。

所有输出都是纯字符串拼接，不依赖绘图库——CI 里少一个依赖就少一个故障点。
"""

from __future__ import annotations

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

    out.append(
        "> `月开销 = 上表逐项相加`，`FIRE 目标 = 月开销 × 12 ÷ 提取率`。"
        "每项金额的依据见 [config.yaml](config.yaml) 与 "
        "[docs/FIRE-LIFE-PLAN.md](docs/FIRE-LIFE-PLAN.md)。"
    )
    out.append(">")
    out.append(
        "> 一次性支出**不摊进月开销**——它不产生永续现金流，"
        "摊进去会同时虚增月开销与 FIRE 目标。"
    )
    if plan.get("target_with_one_off"):
        out.append(">")
        out.append(
            f"> 含一次性支出的资金需求：**{money(plan['target_with_one_off'], cfg)}**"
            f"（= FIRE 目标 + 一次性支出）。"
        )
    out.append("")
    out.append("</details>")
    out.append("")
    return "\n".join(out)


def render_block(data: dict, cfg, history: list[dict]) -> str:
    fire = data["fire"]
    assets = data["assets"]
    btc = assets["btc"]
    sp500 = assets["sp500"]
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

    if cfg.display.get("show_progress_bar", True):
        out.append("![FIRE 完成度](reports/progress.svg)")
        out.append("")
        out.append(
            "> 完成度 = 当前资产 ÷ FIRE 目标。**分子看行情，分母看口径**——"
            "月开销或提取率一调整，这个百分比就会跟着变，"
            "所以它变了不一定代表资产涨跌。"
        )
        out.append("")

    out.append("| 指标 | 数值 |")
    out.append("| --- | ---: |")
    out.append(f"| 🎯 FIRE 目标资产 | {money(fire['target_cny'], cfg)} |")
    out.append(f"| 💰 当前资产 | {money(assets['total_cny'], cfg)} |")
    out.append(f"| 📈 完成度 | **{pct:.3f}%** |")
    out.append(f"| ⏳ 距离目标 | {money(assets['remaining_cny'], cfg)} |")
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
    out.append(f"| 比特币 | {money(btc['value_cny'], cfg)} | {btc_share:.1f}% |")
    out.append(f"| 标普500基金 | {money(sp500['value_cny'], cfg)} | {sp_share:.1f}% |")
    out.append(f"| **合计** | **{money(assets['total_cny'], cfg)}** | 100.0% |")
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

    basis = data.get("cost_basis") or {}
    if basis.get("total_cny") is not None:
        out.append("### 投入与盈亏")
        out.append("")
        out.append("| 指标 | 数值 |")
        out.append("| --- | ---: |")
        out.append(f"| 累计投入本金 | {money(basis['total_cny'], cfg)} |")
        out.append(f"| 当前市值 | {money(assets['total_cny'], cfg)} |")
        out.append(f"| 累计盈亏 | {money(basis['profit_cny'], cfg)} |")
        out.append("")
        if basis.get("btc_estimated"):
            out.append(
                "> 比特币本金按持仓备注中的「均价 $xx/BTC」推算，并按**当前汇率**折算成人民币，"
                "与真实买入成本存在偏差；标普500本金取自 sp500-dca 的累计投入。"
            )
            out.append("")

    if cfg.display.get("show_curve") and history:
        out.append("### 进度曲线")
        out.append("")
        out.append("![FIRE 进度曲线](reports/curve.svg)")
        out.append("")
        out.append(
            "> 曲线是**每日完成度快照**，按 `data/history.json` 里当天记录的原值连线，不回填、不重算。"
        )
        out.append(">")
        out.append(
            "> 图中竖虚线处是**口径调整**——FIRE 目标（分母）变了，不是资产变了，"
            "所以曲线会出现台阶。每天的目标值都记在 `data/history.json` 里，这个台阶可追溯，不是数据错误。"
        )
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
                f"按近 {proj['window_days']} 天的平均增速（日均 +{money(proj['daily_gain_cny'], cfg)}）"
                f"线性外推，{horizon}后达到目标（{proj['eta']}）。"
            )
            out.append("")
            out.append("> 这是线性外推，不是预测。它把近期的增速直接铺到未来，")
            out.append("> 而实际增速会随行情、定投额度与生活开销的变化而改变。")
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
        f"[{cfg.sources.sp500.repo}](https://github.com/{cfg.sources.sp500.repo})（基金持仓）· "
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


def default_readme(block: str, cfg, monthly: float) -> str:
    rate = float(cfg.fire.withdrawal_rate)
    return f"""# FIRE-Progress

> 我的 FIRE 进度看板。只统计**比特币**与**标普500基金**两项资产，
> 由 GitHub Actions 自动更新。

{block}
## 计算口径

| 参数 | 取值 |
| --- | ---: |
| 月开销 | ¥{monthly:,.0f} |
| 提取率 | {rate * 100:.1f}% |
| **FIRE 目标资产** | **¥{monthly * 12 / rate:,.2f}** |

公式：`FIRE 目标 = 月开销 × 12 ÷ 提取率`，`完成度 = 当前资产 ÷ FIRE 目标`。
月开销由 [config.yaml](config.yaml) 的 `life_plan` 逐项推导，见
[docs/FIRE-LIFE-PLAN.md](docs/FIRE-LIFE-PLAN.md)。

## 计入范围

- ✅ [0.1BTC](https://github.com/{cfg.sources.btc.repo}) 仓库中的比特币持仓
- ✅ [sp500-dca](https://github.com/{cfg.sources.sp500.repo}) 仓库中的标普500基金市值
- ❌ 法币、其他币种、其他一切资产

## 数据节奏

- **比特币持仓**：在 [0.1BTC](https://github.com/{cfg.sources.btc.repo}) 仓库中**每周手动更新一次**，
  因此持仓数量存在延迟，**不是实时数据**；但估值会按最新行情实时折算。
- **标普500基金**：QDII 净值通常 T+1 晚间披露，周末与节假日不产生净值，
  因此看板可能连续 2~3 天没有新提交，属正常现象。

---

*本仓库为个人资产记录，不构成任何投资建议。数据为个人口径，可能与实际存在偏差。*
"""
