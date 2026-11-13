"""README 组装：把各小节拼成自动区块，再替换进手写 README。

图表在 charts.py，小节文案在 blocks.py，这里只负责顺序和拼接。
"""

from __future__ import annotations

from .blocks import (
    _freshness,
    _fulltime_block,
    _life_plan_block,
    _passive_income_block,
    _positions_table,
    _stablecoin_block,
    _warnings_block,
)
from .charts import curve_svg, dual_progress_svg, progress_svg, profit_svg
from .fmt import money

START_MARK = "<!-- FIRE:START -->"
END_MARK = "<!-- FIRE:END -->"


def _horizon(days) -> str:
    """把天数说成人话。None 表示算不出来。"""
    if days is None:
        return "—"
    if days < 365:
        return f"约 {days} 天"
    if days < 3650:
        return f"约 {days / 365:.1f} 年"
    return "超过 10 年"


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
    freshness = _freshness(btc, sp500, assets.get("stablecoin"))
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
            "> 三条线回答三个问题：**出发门槛**（能不能走，主进度）= 医疗应急 + 空窗期月开销；"
            "**咖啡师 FIRE**（有兼职）= (月开销 − 兼职净收入) × 12 ÷ 提取率；"
            "**完全 FIRE**（完全不工作）= 月开销 × 12 ÷ 提取率。别把它们混成一个百分比。"
        )
        out.append(">")
        out.append(
            "> 每个点是当天的完成度原值，按 `data/history.json` 连线，不回填、不重算。"
            "竖虚线是口径调整日——那天目标变了，所以出现台阶。"
        )
        out.append(">")
        out.append(
            "> ⚠️ 出发门槛不含行情，只由医疗应急、空窗期月开销决定；"
            "没有对应字段的早期记录按当前门槛折算，是**反事实**，不是历史实测。"
        )
        cap_note = str(cfg.display.get("capital_change_note") or "").strip()
        if cap_note:
            out.append(">")
            out.append(f"> ⚠️ {cap_note}")
        out.append("")

    if cfg.display.get("show_progress_bar", True):
        if data.get("goals"):
            out.append("![三级门槛进度](reports/progress.svg)")
        elif data.get("departure"):
            out.append("![双线进度](reports/progress.svg)")
        else:
            out.append("![FIRE 完成度](reports/progress.svg)")
            out.append("")
            out.append(
                "> 完成度 = 当前资产 ÷ FIRE 目标。资产随行情走，目标随口径走；"
                "月开销、提取率或兼职收入改一项，百分比就会变，未必是资产涨跌。"
            )
        out.append("")

    out.append("| 指标 | 数值 |")
    out.append("| --- | ---: |")
    dep = data.get("departure")
    goals = (data.get("goals") or {}).get("items") or []
    if goals:
        # 三级门槛并列（2026-11-05）：出发门槛 / 咖啡师 FIRE / 完全 FIRE。
        # 主进度那一行加 ★ 标记，由 display.primary_progress 决定，改配置即换。
        icon = {"departure": "🚪", "coffee_fire": "☕", "full_fire": "🎯"}
        for g in goals:
            name = g["label"] + ("（★ 主进度）" if g.get("is_primary") else "")
            out.append(
                f"| {icon.get(g['key'], '🎯')} {name} · {g['subtitle']} | "
                f"{money(g['target_cny'], cfg)} |"
            )
        if dep:
            out.append(
                f"| 🚪 出发门槛上沿（更保守） | {money(dep['high_cny'], cfg)} |"
            )
        out.append(f"| 💰 当前资产 | {money(assets['total_cny'], cfg)} |")
        for g in goals:
            name = g["label"] + "完成度" + ("（★ 主进度）" if g.get("is_primary") else "")
            out.append(f"| 📈 {name} | **{g['progress_pct']:.3f}%** |")
    else:
        # 旧快照没有 goals 时，退回单门槛展示，行为与旧版一致。
        if dep:
            out.append(
                f"| 🚪 出发门槛（能不能走） | {money(dep['low_cny'], cfg)}–{money(dep['high_cny'], cfg)} |"
            )
            out.append(f"| 🎯 咖啡师 FIRE 门槛（能不能不工作） | {money(fire['target_cny'], cfg)} |")
            out.append(f"| 📈 出发门槛完成度 | **{dep['progress_low'] * 100:.3f}%** |")
            out.append(f"| 📈 咖啡师 FIRE 门槛完成度 | **{pct:.3f}%** |")
        else:
            out.append(f"| 🎯 FIRE 目标资产 | {money(fire['target_cny'], cfg)} |")
            out.append(f"| 📈 完成度 | **{pct:.3f}%** |")
        out.append(f"| 💰 当前资产 | {money(assets['total_cny'], cfg)} |")
    labor = fire.get("labor_income")
    if labor:
        out.append(f"| ☕ 兼职净收入（月） | {money(labor['net_monthly_cny'], cfg)} |")
        out.append(f"| 🧾 组合需覆盖（月，咖啡师 FIRE） | {money(fire['net_monthly_expense'], cfg)} |")
    out.append(f"| ⏳ 距离咖啡师 FIRE 门槛 | {money(assets['remaining_cny'], cfg)} |")
    if goals:
        primary = next((g for g in goals if g.get("is_primary")), goals[0])
        out.append(f"| ⏳ 距离主进度（{primary['label']}） | {money(primary['remaining_cny'], cfg)} |")
    pi = data.get("passive_income")
    if pi:
        out.append(
            f"| ⏱️ 每小时被动收入（按预期年化） | {money(pi['hourly_cny'], cfg, decimals=2)} |"
        )
    out.append("")
    if goals:
        out.append(
            "> **三个门槛别混成一个百分比。** 出发门槛答「能不能动身」（阶段 A 有工作，"
            "只需医疗应急 + 空窗期月开销）；咖啡师 FIRE 答「能不能只做兼职」"
            "（资产覆盖 ¥731/月）；**完全 FIRE 答「能不能完全不工作」"
            "（资产覆盖全额 ¥1,454/月，不依赖任何劳动收入）**。"
            "主进度由 `display.primary_progress` 指定，改一行即可切换。"
        )
        out.append("")

    ft_block = _fulltime_block(data, cfg)
    if ft_block:
        out.append(ft_block.strip())
        out.append("")

    ft_block_mdj = _fulltime_block(data, cfg, key="fulltime_mudanjiang", primary=False)
    if ft_block_mdj:
        out.append(ft_block_mdj.strip())
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
    stable = assets.get("stablecoin") or {}
    cash = assets.get("cash_cny") or {}
    stable_share = (stable.get("value_cny") or 0.0) / total * 100 if assets["total_cny"] else 0.0
    cash_share = (cash.get("value_cny") or 0.0) / total * 100 if assets["total_cny"] else 0.0
    # 清仓后主界面不再列出比特币这一行（零值行没有信息量，还容易让人以为忘了清）。
    # ⚠️ 只是展示层隐藏：assets.btc 仍是分子里的一块，口径和历史曲线都不变。
    if btc["qty"]:
        out.append(f"| 比特币 | {money(btc['value_cny'], cfg)} | {btc_share:.1f}% |")
    out.append(f"| 标普500基金 | {money(sp500['value_cny'], cfg)} | {sp_share:.1f}% |")
    if ndx100.get("value_cny"):
        out.append(f"| 纳指100基金 | {money(ndx100['value_cny'], cfg)} | {ndx_share:.1f}% |")
    if stable.get("value_cny"):
        out.append(f"| 稳定币（USDT + USDC） | {money(stable['value_cny'], cfg)} | {stable_share:.1f}% |")
    if cash.get("value_cny"):
        out.append(f"| 人民币活钱（余额宝） | {money(cash['value_cny'], cfg)} | {cash_share:.1f}% |")
    out.append(f"| **合计** | **{money(assets['total_cny'], cfg)}** | 100.0% |")
    out.append("")
    out.append(
        "> 计入分子的是上面这几项：权益基金、稳定币与人民币活钱。"
        "比特币已清仓（持仓 0），不再列出。稳定币按实时 USD/CNY 折算，"
        "所以汇率波动会真实改变完成度；两项现金的明细见下方折叠块。"
    )
    out.append("")

    if not masked and btc["qty"]:
        out.append(
            f"比特币计价：**{btc['qty']:.8f} BTC** × {money(btc['price_cny'], cfg)} = "
            f"{money(btc['value_cny'], cfg)}"
        )
        out.append("")
    if btc["qty"] and btc["positions"]:
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

    sc_block = _stablecoin_block(data, cfg)
    if sc_block:
        out.append(sc_block.strip())
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
                "> ⚠️ 资产离开计入范围时（如清仓），市值和本金会**同时**退出统计，"
                "上面板出现台阶不代表亏损，只是口径边界。稳定币与活钱按面值计入本金，"
                "不产生浮盈浮亏；稳定币折算值还会随汇率小幅起伏。"
            )
            out.append(">")
            out.append(
                "> 上面板纵轴不从 0 起，否则缺口会被压成一条线，斜率也不代表涨跌幅。"
                "下面板含 0，正负可以直接读。"
            )
            out.append(">")
            out.append(
                f"> 起点 {first_day}。早期数据由两个持仓仓库的历史文件重建，"
                "当时的比特币本金按当时汇率折算，绝对值和真实本金有误差，趋势可信；"
                "之后每天由 Actions 记录。"
            )
            out.append("")

    # 被动收入与外推都是「往前看」的内容，放在一起。
    # 被动收入在**前**：它是当前持仓的直接推论，比外推更硬；
    # 外推依赖「近期增速会延续」这个更弱的假设。
    pi_block = _passive_income_block(data, cfg)
    if pi_block:
        out.append(pi_block.strip())
        out.append("")

    proj = data.get("projection")
    if proj:
        out.append("### 外推")
        out.append("")
        days = proj.get("days_to_target")
        if days is not None:
            scen = proj.get("scenarios") or {}
            low = scen.get("low") or {}
            base_sc = scen.get("base") or {}
            high = scen.get("high") or {}
            out.append(
                f"按「定投 + 资产增值」外推：日投 **{money(proj['daily_cny'], cfg)}**"
                f"（月 {money(proj['monthly_cny'], cfg)}，标普500 "
                f"{money(proj['sp500_cny_per_day'], cfg)}/天），"
                f"叠加当前持仓按加权预期年化 **{proj['weighted_rate'] * 100:.2f}%** 增长，"
                f"**{_horizon(days)}**后达到**咖啡师 FIRE 门槛**（{proj['eta']}）。"
            )
            out.append("")
            out.append(
                f"> 区间：悲观{_horizon(low.get('days'))}"
                f"（加权 {low.get('rate', 0) * 100:.2f}%）"
                f" · 基准{_horizon(base_sc.get('days'))}"
                f" · 乐观{_horizon(high.get('days'))}"
                f"（加权 {high.get('rate', 0) * 100:.2f}%）。"
            )
            out.append(">")
            out.append(
                "> 这不再是线性外推：定投按天累加，已有持仓按年化复利。差距全部来自收益率假设——"
                "权益类资产的「平均收益率」只是假设，真实路径先涨还是先跌会改变结果，上沿只能当参考。"
                "稳定币的 10% 与活钱的 1% 也都进了加权年化：前者是限额活动利率，"
                "悲观档按 0% 记，所以区间下沿明显更慢。"
            )
            out.append(">")
            out.append(
                "> 定投额用真实值、不用近 30 天增速：那段增速由行情主导，"
                "涨得快不等于进度快，跌的时候还会被推成「永远达不到」。"
            )
            if days >= 3650:
                out.append(">")
                out.append("> 在这个尺度上外推结果已无参考意义——真正决定进度的是月定投额，不是等待。")
            # 全职情景的第二条外推。口径与上面完全一致，只换了定投额，
            # 所以两条可以直接比。细节在「阶段 A 工作情景」那个折叠块里。
            ft = data.get("fulltime") or {}
            ftp = ft.get("projection") or {}
            if ftp.get("days_to_target"):
                out.append(">")
                out.append(
                    f"> **阶段 A 若有全职收入**（净 {money(ft['net_monthly_cny'], cfg)}/月，"
                    f"盈余 {money(ft['surplus_monthly_cny'], cfg)} 并入定投 → 月投 "
                    f"{money(ftp['monthly_cny'], cfg)}），同一口径下 **{_horizon(ftp['days_to_target'])}**"
                    f"（{ftp['eta']}）。这是敏感性测算，不是承诺——它假设这份工作从现在就有。"
                )
                ftm = data.get("fulltime_mudanjiang") or {}
                ftmp = ftm.get("projection") or {}
                if ftmp.get("days_to_target"):
                    out.append(">")
                    out.append(
                        f"> **备选情景：云南省内轻松工作**（净 {money(ftm['net_monthly_cny'], cfg)}/月，"
                        f"盈余 {money(ftm['surplus_monthly_cny'], cfg)} 并入定投 → 月投 "
                        f"{money(ftmp['monthly_cny'], cfg)}），同一口径下 **{_horizon(ftmp['days_to_target'])}**"
                        f"（{ftmp['eta']}）。工资取 ¥17/h 保守占位，按实际岗位改。"
                    )
        else:
            out.append(f"暂不可外推：{proj.get('reason') or '数据不足'}")
        out.append("")

    warn_block = _warnings_block(data.get("warnings", []))
    if warn_block:
        out.append(warn_block.strip())
        out.append("")

    out.append(
        f"<sub>数据源："
        f"[{cfg.sources.sp500.repo}](https://github.com/{cfg.sources.sp500.repo})（标普500 持仓）、"
        f"东方财富（纳指100 净值，份额固定）、"
        f"[{cfg.sources.btc.repo}](https://github.com/{cfg.sources.btc.repo})（比特币持仓，已清仓）· "
        f"稳定币与人民币活钱由本人手动报数 · "
        f"汇率：{data['price']['fx_source']}"
        f"{' · 行情：' + data['price']['btc_source'] if data['price'].get('btc_usdt') else ''}</sub>"
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
    block: str,
    cfg,
    monthly: float,
    net_monthly: float | None = None,
    departure: dict | None = None,
) -> str:
    rate = float(cfg.fire.withdrawal_rate)
    # 组合需覆盖 = 月开销 − 兼职净收入。没传就退回全部月开销，与旧口径一致。
    net = monthly if net_monthly is None else net_monthly
    # 出发门槛是 2026-10-31 新增的第二条线；缺数据时不写这一行，行为与旧版一致。
    gate_rows = ""
    gate_note = ""
    if departure:
        gate_rows = (
            f"| **出发门槛**（能不能走） | **¥{departure['low_cny']:,.0f} – ¥{departure['high_cny']:,.0f}** |\n"
        )
        gate_note = (
            "\n出发门槛 = 医疗专项应急金 + 空窗期月开销（**不含**搬家/押金等一次性支出）。"
            "阶段 A 有工作、有现金流，出发不需要资产覆盖生活费。\n"
        )
    return f"""# FIRE-Progress

> 我的 FIRE 进度看板。计入分子的资产：标普500基金、纳指100基金、稳定币、人民币活钱
> （比特币已清仓）。基金持仓来自两个公开仓库 + 东方财富的公开净值接口，
> 稳定币与活钱由本人手动报数，稳定币按实时汇率折算。
> 由 GitHub Actions 每小时更新，不需要任何密钥。

{block}
## 计算口径

| 参数 | 取值 |
| --- | ---: |
{gate_rows}| 月开销 | ¥{monthly:,.0f} |
| 组合需覆盖（月开销 − 兼职净收入） | ¥{net:,.0f} |
| 提取率 | {rate * 100:.1f}% |
| **咖啡师 FIRE 门槛**（有兼职） | **¥{net * 12 / rate:,.2f}** |
| **完全 FIRE 门槛**（完全不工作） | **¥{monthly * 12 / rate:,.2f}** |

公式：`咖啡师 FIRE = (月开销 − 兼职净收入) × 12 ÷ 提取率`；
`完全 FIRE = 月开销 × 12 ÷ 提取率`，不扣任何劳动收入。
**「不工作」不能含糊地套在第一行的数字上，那一行是有兼职的口径**——
两条门槛并列，谁都不许混。
{gate_note}
月开销由 [config.yaml](config.yaml) 的 `life_plan` 逐项推导，依据见
[docs/FIRE-LIFE-PLAN.md](docs/FIRE-LIFE-PLAN.md)。

## 计入范围

- ✅ [sp500-dca](https://github.com/{cfg.sources.sp500.repo}) 仓库中的标普500基金市值
- ✅ 纳指100 场外基金（份额写在 `config.yaml`）
- ✅ 稳定币（USDT / USDC，按实时 USD/CNY 折算）
- ✅ 人民币活钱（余额宝，手动报数）
- ✅ [0.1BTC](https://github.com/{cfg.sources.btc.repo}) 仓库中的比特币持仓（已清仓，当前为 0）
- ❌ 其他一切未列出的资产

纳入标准是「属于这个资产池」，不是「能不能变现」。上面几项都计入分子，
所以它们之间的划转不产生进度变化；只有外部资金进出、行情和汇率才会改变完成度。

| 情形 | 进度 | 是否真实 |
| --- | --- | --- |
| 工资入金 / 外部买入 | ↑ | 真实增长 |
| 池内互换（稳定币买标普500） | → 不变 | 正常 |
| 把钱花掉 / 转出池外 | ↓ | 真实减少 |
| 人民币升值（稳定币折人民币变少） | ↓ | 真实：以人民币计的购买力变了 |

> 稳定币按实时汇率折算，所以汇率波动会直接反映在进度上；
> 这不是数据错误，是本看板以人民币计价的结果。

## 数据节奏

- **标普500基金**：QDII 净值通常 T+1 晚间披露，周末和节假日没有净值，
  看板可能连续 2~3 天没有新提交，属正常。
- **稳定币 / 人民币活钱**：由本人手动报数，不是实时余额；活钱会因日常花销与
  ¥20/天 定投小幅变化，不定期更新。

---

*本仓库为个人资产记录，不构成任何投资建议。数据为个人口径，可能与实际存在偏差。*
"""
