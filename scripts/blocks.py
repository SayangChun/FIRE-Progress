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


def _fulltime_block(data: dict, cfg, key: str = "fulltime", primary: bool = True) -> str:
    """全职情景：阶段 A 首选/备选方案的现金流。

    ⚠️ 这一节**不参与 FIRE 目标**。全职净收入大于月开销，
    代进 (月开销 − 净收入) × 12 ÷ 提取率 会得到负数——
    负数不是「超额完成」，是那个公式在这里没有答案。

    所以这里只展示三件事：净收入多少、每月盈余多少、以及
    「若这笔盈余从今天起就并入定投，达标会提前多久」。

    key 指定读取 data 里的哪个全职变体（2026-11-05 起只有 "fulltime"，
    即牡丹江独自租房方案）；primary=False 时标题改为「备选变体」并追加
    一条「岗位数量待确认」的提示。变体不存在时返回空串，调用方跳过。
    """
    ft = data.get(key)
    if not ft:
        return ""

    out: list[str] = []
    out.append("<details>")
    prefix = "阶段 A 首选方案" if primary else "阶段 A 备选城市"
    out.append(f"<summary>{prefix} · {ft.get('label') or '全职'}</summary>")
    out.append("")
    out.append(
        f"**{money(ft['hourly_wage'], cfg, decimals=0)}/小时 × "
        f"{ft['hours_per_week']:.0f} 小时/周 = "
        f"毛收入 {money(ft['gross_monthly_cny'], cfg)}/月**，"
        f"扣掉工作增量消耗 {money(ft['cost_monthly_cny'], cfg)}"
        f"（交通 {money(ft['transport_cny'], cfg)} + 餐食 {money(ft['meal_cny'], cfg)}"
        f" + 装备 {money(ft['gear_cny'], cfg)}），"
        f"净收入 **{money(ft['net_monthly_cny'], cfg)}/月**。"
    )
    out.append("")
    out.append("| 项目 | 数值 |")
    out.append("| --- | ---: |")
    out.append(f"| 月净收入 | {money(ft['net_monthly_cny'], cfg)} |")
    if ft.get("room_and_board_covered"):
        out.append(
            f"| 阶段 A 个人月开销（包吃住，已扣房租/伙食） | {money(ft['stage_a_monthly_expense'], cfg)} |"
        )
    else:
        out.append(f"| 月开销 | {money(ft['monthly_expense'], cfg)} |")
    out.append(f"| **月盈余** | **{money(ft['surplus_monthly_cny'], cfg)}** |")
    out.append(f"| 等效时薪（含通勤） | {money(ft['effective_hourly_cny'], cfg, decimals=2)} |")
    out.append(f"| 每月占用工时 | {ft['occupied_hours_per_month']:.0f} 小时 |")
    out.append("")

    if not primary:
        out.append(
            "> ⚠️ 这是**备选变体**，尚未取代当前主方案；"
        )
        out.append(
            "> 工资取当地同类岗位的保守下限，岗位数量需实地确认。"
        )
        out.append(
            "> 外推仍沿用 ¥205,953.49 作对照尺（这是「牡丹江不工作」的口径，仅供对照）。"
        )
        out.append("")

    proj = ft.get("projection")
    if proj and proj.get("eta"):
        out.append(
            f"> 若这份盈余从现在起并入定投（月投 {money(proj['monthly_cny'], cfg)}），"
            f"按基准年化 **{proj['weighted_rate'] * 100:.2f}%** 外推，"
            f"约 **{proj['days_to_target'] / 365:.2f} 年**后达到不工作门槛（{proj['eta']}）；"
            f"不做全职则要 {data['projection']['days_to_target'] / 365:.2f} 年"
            f"（{data['projection']['eta']}）。"
        )
        out.append(">")
        out.append(
            "> ⚠️ 这是**敏感性测算**，不是承诺：它假设这份工作从今天就有、"
            "且盈余全部存下。实际要到 2029-06 毕业才可能开始。"
        )
        out.append(">")
        out.append(
            "> ⚠️ 全职**不改变**上面的 FIRE 目标。目标只由「月开销 − 兼职净收入」决定；"
            "全职只影响「多久到」，不影响「到多少」。"
        )
    out.append("")
    out.append("</details>")
    return "\n".join(out)


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
