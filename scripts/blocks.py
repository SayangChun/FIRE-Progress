"""README 自动区块里的各个小节。

每个函数只负责生成一段 markdown，不关心自己排在第几节；
顺序由 render_block() 决定。
"""

from __future__ import annotations

from .fmt import money


# ---------------------------------------------------------------- README 区块


def _warnings_block(warnings: list[str]) -> str:
    if not warnings:
        return ""
    lines = ["", "> ⚠️ **数据源告警**", ">"]
    lines += [f"> - {w}" for w in warnings]
    return "\n".join(lines) + "\n"


def _freshness(btc: dict, sp500: dict, stablecoin: dict | None = None) -> str:
    """数据新鲜度：明确告诉读者「持仓和稳定币都不是实时数据」。

    清仓后不再显示比特币快照——主界面不列已离场的资产；
    稳定币改由下面的「稳定币明细」自己标快照日期。
    """
    parts = []
    if btc.get("qty") and btc.get("snapshot_date"):
        stale = btc.get("stale_days")
        age = f"{stale} 天前" if isinstance(stale, int) and stale >= 0 else "—"
        parts.append(f"**比特币快照**：{btc['snapshot_date']}（{age}）")
    if sp500.get("latest_nav_date"):
        parts.append(f"**基金净值日**：{sp500['latest_nav_date']}")
    if stablecoin and stablecoin.get("snapshot_date"):
        parts.append(f"**稳定币快照**：{stablecoin['snapshot_date']}（手动报数）")
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


def _fulltime_block(data: dict, cfg, key: str = "fulltime", primary: bool = True) -> str:
    """全职情景：阶段 A 的现金流。

    ⚠️ 这一节不参与 FIRE 目标。全职净收入大于月开销，代进
    (月开销 − 净收入) × 12 ÷ 提取率 会得到负数——负数不是「超额完成」，
    是那个公式在这里没有答案。所以只展示：净收入、月盈余、达标会提前多久。

    变体不存在时返回空串，调用方跳过。
    """
    ft = data.get(key)
    if not ft:
        return ""

    out: list[str] = []
    out.append("<details>")
    prefix = "阶段 A 工作情景" if primary else "阶段 A 备选情景"
    out.append(f"<summary>{prefix} · {ft.get('label') or '全职'}</summary>")
    out.append("")
    out.append(
        f"**{money(ft['hourly_wage'], cfg, decimals=0)}/小时 × "
        f"{ft['hours_per_week']:.0f} 小时/周 = 毛收入 {money(ft['gross_monthly_cny'], cfg)}/月**，"
        f"扣交通 {money(ft['transport_cny'], cfg)}、餐食 {money(ft['meal_cny'], cfg)}、"
        f"装备 {money(ft['gear_cny'], cfg)}，净 **{money(ft['net_monthly_cny'], cfg)}/月**。"
        f"月开销 {money(ft.get('stage_a_monthly_expense') or ft['monthly_expense'], cfg)}，"
        f"**盈余 {money(ft['surplus_monthly_cny'], cfg)}**"
        f"（等效时薪 {money(ft['effective_hourly_cny'], cfg, decimals=2)}，"
        f"每月占用 {ft['occupied_hours_per_month']:.0f} 小时）。"
    )
    out.append("")

    proj = ft.get("projection")
    if proj and proj.get("eta"):
        out.append(
            f"> 盈余若从现在起并入定投（月投 {money(proj['monthly_cny'], cfg)}），"
            f"按基准年化 **{proj['weighted_rate'] * 100:.2f}%** 外推，约 "
            f"**{proj['days_to_target'] / 365:.2f} 年**后达到咖啡师 FIRE 门槛（{proj['eta']}）；"
            f"不做全职则 {data['projection']['days_to_target'] / 365:.2f} 年"
            f"（{data['projection']['eta']}）。"
        )
        out.append(">")
        out.append(
            "> ⚠️ 敏感性测算，不是承诺：假设这份工作今天就有、盈余全部存下"
            "（实际要到 2029-06 毕业才可能开始）。全职**不改变** FIRE 目标，只影响「多久到」。"
        )
        if not primary:
            out.append(">")
            out.append("> ⚠️ 这是备选情景，尚未取代主口径；工资取轻松岗的保守占位，按实际岗位改。")
    out.append("")
    out.append("</details>")
    return "\n".join(out)


def _life_plan_block(data: dict, cfg) -> str:
    """FIRE 后月开销明细：让「目标资产」的来历可追溯。

    一张表列完 17 项，分类只在每类第一行出现，不再分四张小表——
    同样的信息，行数少一半。
    金额不做隐私遮蔽：这是未来生活预算，不是持仓金额。
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
    out.append("| 分类 | 项目 | 月支出 |")
    out.append("| --- | --- | ---: |")
    for group in plan["groups"]:
        for i, item in enumerate(group["items"]):
            name = group["group"] if i == 0 else ""
            out.append(f"| {name} | {item['label']} | {money(item['monthly'], cfg)} |")
    out.append(f"| **合计** |  | **{money(plan['monthly_expense'], cfg)}** |")
    out.append("")

    labor = plan.get("labor_income")
    if labor:
        out.append(
            f"兼职 {money(labor['hourly_wage'], cfg, decimals=0)}/小时 × 每周 "
            f"{labor['hours_per_week']:.0f} 小时：毛 {money(labor['gross_monthly_cny'], cfg)} − "
            f"交通 {money(labor['transport_cny'], cfg)} − 餐食 {money(labor['meal_cny'], cfg)} − "
            f"装备 {money(labor['gear_cny'], cfg)} = 净 **{money(labor['net_monthly_cny'], cfg)}/月**，"
            f"组合需覆盖 **{money(plan['net_monthly_expense'], cfg)}/月**。"
        )
        out.append("")

    if plan.get("one_off"):
        parts = " + ".join(f"{row['label']} {money(row['amount'], cfg)}" for row in plan["one_off"])
        extra = (
            f"，含一次性支出共 **{money(plan['target_with_one_off'], cfg)}**"
            if plan.get("target_with_one_off")
            else ""
        )
        out.append(
            f"一次性支出（不摊进月开销）：{parts} = **{money(plan['one_off_total'], cfg)}**{extra}。"
        )
        out.append("")

    if plan.get("override"):
        out.append(
            f"> ⚠️ 当前为手工覆盖值（`fire.monthly_expense`），逐项推导值为 "
            f"{money(plan.get('derived_monthly_expense'), cfg)}。"
        )
        out.append("")

    formula = (
        "`FIRE 目标 = (月开销 − 兼职净收入) × 12 ÷ 提取率`"
        if labor
        else "`FIRE 目标 = 月开销 × 12 ÷ 提取率`"
    )
    out.append(
        "> 只扣上班多出来的开销：餐食算的是「在外面吃比在家做贵多少」，"
        "家里那顿已经算在食品里，全额扣等于把生活费算两遍。"
    )
    out.append(">")
    out.append(
        f"> 月开销 = 各项相加，{formula}。每项依据见 "
        "[config.yaml](config.yaml) 与 [docs/FIRE-LIFE-PLAN.md](docs/FIRE-LIFE-PLAN.md)。"
    )
    out.append("")
    out.append("</details>")
    out.append("")
    return "\n".join(out)


def _stablecoin_block(data: dict, cfg) -> str:
    """手动维护资产明细：稳定币（USD 计价）+ 人民币活钱，都计入分子。

    边界必须跟着数字一起出现：
      1. 稳定币以美元计价，按实时汇率折人民币——汇率波动会真实改变完成度；
      2. 活动年化不是长期保证收益，区间下沿按 0% 记；
      3. 两项都由本人手动报数，不是实时余额。
    """
    assets = data.get("assets") or {}
    sc = assets.get("stablecoin")
    cash = assets.get("cash_cny")
    if not sc and not cash:
        return ""

    out: list[str] = []
    out.append("<details>")
    out.append("<summary>手动维护资产明细 · 稳定币与人民币活钱（均计入分子）</summary>")
    out.append("")
    if sc:
        out.append("| 币种 | 数量 | 折人民币 |")
        out.append("| --- | ---: | ---: |")
        for row in sc["holdings"]:
            out.append(
                f"| {row['asset']} | {row['amount']:,.0f} | {money(row['value_cny'], cfg)} |"
            )
        out.append(
            f"| **稳定币合计** | **{sc['total_units']:,.0f}** | "
            f"**{money(sc['value_cny'], cfg)}** |"
        )
        out.append("")
        out.append(
            f"按 USD/CNY = {sc['usd_cny']:.4f} 折算（USDT / USDC 按 1:1 锚定美元，"
            f"未计脱锚与买卖价差；快照 {sc.get('snapshot_date') or '—'}，手动报数）。"
            "**汇率变动会真实改变完成度**，这是它和其他资产最大的不同。"
        )
        out.append("")
    if cash:
        out.append(
            f"人民币活钱（余额宝）：**{money(cash['value_cny'], cfg)}**"
            f"（快照 {cash.get('snapshot_date') or '—'}，手动报数）。"
        )
        out.append("")
    out.append(
        "> 稳定币放在交易所活期理财，限额活动年化按 **10%** 记，"
        "区间 0–10%：只覆盖限额内部分，限额会变、活动会结束，下沿 0% 就是活动结束。"
        "人民币活钱按 **1%** 保守取值（区间 1–1.5%）。"
    )
    out.append(">")
    out.append(
        "> 两笔钱都**计入分子**：已进上面的资产构成表、三个门槛、完成度、"
        "被动收入加权与达成年限外推。它们可随时变现，用于在标普500 显著回撤时"
        "场内加仓或场外申购额度放开时大额申购；真买入标普500 时只是分子内部换形式，"
        "进度不会因此跳升。"
    )
    out.append(">")
    out.append(
        "> 标普500 每日 ¥20 定投从人民币活钱里扣，属分子内部划转；"
        "活钱余额由本人不定期更新，所以短期看板读数会略滞后于实际扣款。"
    )
    notes = [sc.get("note") if sc else None, cash.get("note") if cash else None]
    for n in notes:
        if n:
            out.append(">")
            out.append(f"> {n}")
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
    # 清仓后主界面不列出零市值资产：口径不变（JSON 里仍保留该块），只是不展示。
    shown = [r for r in rows if r["value_cny"] > 0]
    hourly = pi["hourly_cny"]
    rate = pi["weighted_rate"] or 0.0

    out: list[str] = []
    out.append("### 每小时被动收入")
    out.append("")
    out.append("| 资产 | 市值 | 权重 | 预期年化 | 每小时 |")
    out.append("| --- | ---: | ---: | ---: | ---: |")
    for row in shown:
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
        f"{r['label']} {r['rate_low'] * 100:.0f}%" for r in shown if r.get("rate_low") is not None
    )
    high_desc = "、".join(
        f"{r['label']} {r['rate_high'] * 100:.0f}%" for r in shown if r.get("rate_high") is not None
    )
    if pi.get("hourly_low_cny") is not None and pi.get("hourly_high_cny") is not None:
        # 权重要现算，不能写死——仓位结构一变，这句解释就跟着错。
        top = max(shown, key=lambda r: r["weight"]) if shown else None
        if top and top["weight"] >= 0.8:
            why = (
                f"因为 **{top['weight'] * 100:.0f}% 的仓位压在{top['label']}上**，"
                "这个数字的软肋是权重，不是回报率。"
            )
        elif top and top["key"] == "stablecoin":
            why = (
                "因为 **10% 是交易所限额活动的活期理财利率**，只覆盖限额内部分："
                "活动一结束就落到 0%，悲观档几乎只剩权益和活钱在贡献，"
                "而乐观档也仍按 10% 封顶。这个区间的宽度来自活动本身，不是市场波动。"
            )
        else:
            why = (
                "因为各资产的回报率假设本身就宽：权益类没有可锚定的现金流，"
                "长期回报率只能给一个区间，不是能算出来的数。"
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
        "按平均回报安排支出就会在中途卖掉筹码。权益类单年大幅回撤并不罕见，两个数要一起看。"
    )
    out.append("")
    return "\n".join(out)
