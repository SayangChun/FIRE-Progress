"""FIRE 计算核心。

口径（唯一权威定义，改口径只改这里 + config.yaml）：

    FIRE 目标资产 = 组合需覆盖月开销 × 12 ÷ 提取率
    组合需覆盖    = 月开销 − 兼职净收入
    当前资产      = 比特币市值 + 标普500基金市值
    完成度        = 当前资产 ÷ FIRE 目标资产

「月开销」默认由 life_plan（FIRE 生活规划）逐项推导而来，
每一项都在 config.yaml 里标注了依据，见 scripts/lifeplan.py。
若 config.yaml 里手工填了 fire.monthly_expense，则以手工值为准
（用于临时试算），并在结果里标记 override。

「兼职净收入」对应咖啡师 FIRE（fire.labor_income）：FIRE 之后仍做
低压力、可随时停的兼职，收入覆盖一部分开销，资产不必覆盖全部。
未启用时该项为 0，公式退化为传统的「月开销 × 12 ÷ 提取率」。

统计三项「长期不动用的可投资资产」：比特币、标普500基金、纳指100基金。
纳入标准是**长期不动用**，不是「能不能变现」——日常现金要参与周转，所以不计入。
比特币持仓数量来自 0.1BTC 仓库（每周手动更新，存在延迟），
标普500持仓来自 sp500-dca 仓库；纳指100 的份额写在 config.yaml，
净值抓东方财富公开接口（2026-10-27 加入，已停止定投）。
估值统一折算成人民币。
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from scripts import lifeplan as lifeplan_mod


def _now(tz_name: str = "Asia/Shanghai") -> datetime:
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo(tz_name))
    except Exception:
        # Windows 上可能没有 tzdata；北京无夏令时，直接用固定 +8 偏移
        if tz_name == "Asia/Shanghai":
            return datetime.now(timezone(timedelta(hours=8)))
        return datetime.now(timezone.utc).astimezone()


def target_cny(monthly_expense: float, withdrawal_rate: float) -> float:
    return monthly_expense * 12 / withdrawal_rate


# 一年的小时数。用 365 天而不是 365.25：这是个展示口径，差 0.07% 无意义。
HOURS_PER_YEAR = 365 * 24


def passive_income(
    cfg,
    *,
    btc_value: float,
    sp500_value: float,
    monthly_expense: float,
    ndx_value: float = 0.0,
    stablecoin_value: float = 0.0,
    cash_value: float = 0.0,
) -> dict | None:
    """按预期年化回报估算「每小时被动收入」。

    这是**假设性测算**，不是预测：它假设资产按一个恒定的年化回报连续复利增长，
    而现实里回报是波动的，且波动本身会吃掉一部分复利（波动拖累）。

    ⚠️ 必须和 FIRE 的提取率分开看，两者回答的不是同一个问题：
      - 预期年化回报 = 资产「平均」能涨多少（含亏损年份，是个算术平均）
      - 提取率 4.3%  = 每年能安全取出多少而不至于提前耗尽本金
    前者远高于后者是正常的。把前者当后者用，会在第一个熊市就击穿本金——
    所以结果里同时给出按提取率口径的那个数，供对照。

    口径全部来自 config.yaml 的 expected_return 段；缺失则返回 None（不猜默认值）。
    """
    spec = cfg.get("expected_return") or {}
    if spec.get("btc") is None or spec.get("sp500") is None:
        return None

    # 纳指100：只有实际持有、且配了回报假设时才纳入加权。
    # 缺假设就跳过这一项，而不是拿 0 或别的资产的值凑——
    # 拿错值会让「每小时被动收入」凭空变化，而看板上看不出来。
    include_ndx = float(ndx_value) > 0 and spec.get("ndx100") is not None
    # 手动维护的两项：只有实际持有、且配了回报假设时才纳入加权。
    include_stable = float(stablecoin_value) > 0 and spec.get("stablecoin") is not None
    include_cash = float(cash_value) > 0 and spec.get("cash_cny") is not None

    total = (
        float(btc_value)
        + float(sp500_value)
        + (float(ndx_value) if include_ndx else 0.0)
        + (float(stablecoin_value) if include_stable else 0.0)
        + (float(cash_value) if include_cash else 0.0)
    )

    specs = [
        ("btc", "比特币", btc_value, spec.get("btc"), spec.get("btc_low"), spec.get("btc_high")),
        ("sp500", "标普500基金", sp500_value, spec.get("sp500"), spec.get("sp500_low"), spec.get("sp500_high")),
    ]
    if include_ndx:
        specs.append(
            (
                "ndx100",
                "纳指100基金",
                ndx_value,
                spec.get("ndx100"),
                spec.get("ndx100_low"),
                spec.get("ndx100_high"),
            )
        )
    if include_stable:
        specs.append(
            (
                "stablecoin",
                "稳定币",
                stablecoin_value,
                spec.get("stablecoin"),
                spec.get("stablecoin_low"),
                spec.get("stablecoin_high"),
            )
        )
    if include_cash:
        specs.append(
            (
                "cash_cny",
                "人民币活钱",
                cash_value,
                spec.get("cash_cny"),
                spec.get("cash_cny_low"),
                spec.get("cash_cny_high"),
            )
        )

    rows: list[dict] = []
    for key, label, value, rate, low, high in specs:
        value, rate = float(value), float(rate)
        rows.append(
            {
                "key": key,
                "label": label,
                "value_cny": round(value, 2),
                "weight": value / total if total else 0.0,
                "rate": rate,
                "annual_cny": round(value * rate, 2),
                "hourly_cny": value * rate / HOURS_PER_YEAR,
                "rate_low": None if low is None else float(low),
                "rate_high": None if high is None else float(high),
            }
        )

    annual = sum(float(r["annual_cny"]) for r in rows)
    hourly = annual / HOURS_PER_YEAR
    monthly = annual / 12

    def weighted(pick) -> float | None:
        """按市值加权求一个比率；任一端缺值就整体返回 None，不拿默认值凑。"""
        if total <= 0:
            return 0.0
        acc = 0.0
        for row in rows:
            rate = pick(row)
            if rate is None:
                return None
            acc += float(row["value_cny"]) * float(rate)
        return acc / total

    rate_low = weighted(lambda r: r["rate_low"])
    rate_high = weighted(lambda r: r["rate_high"])

    withdrawal = float(cfg.fire.get("withdrawal_rate") or 0.0)

    return {
        "hours_per_year": HOURS_PER_YEAR,
        "total_value_cny": round(total, 2),
        "weighted_rate": weighted(lambda r: r["rate"]),
        "annual_cny": round(annual, 2),
        "monthly_cny": round(monthly, 2),
        "daily_cny": annual / 365,
        "hourly_cny": hourly,
        "rate_low": rate_low,
        "rate_high": rate_high,
        "hourly_low_cny": None if rate_low is None else total * rate_low / HOURS_PER_YEAR,
        "hourly_high_cny": None if rate_high is None else total * rate_high / HOURS_PER_YEAR,
        "monthly_expense": round(float(monthly_expense), 2),
        "coverage": (monthly / float(monthly_expense)) if monthly_expense else None,
        # 对照：同样这笔钱，按 FIRE 提取率能「安全取出」多少
        "withdrawal_rate": withdrawal,
        "monthly_at_withdrawal_cny": round(total * withdrawal / 12, 2),
        "hourly_at_withdrawal_cny": total * withdrawal / HOURS_PER_YEAR,
        "assets": rows,
    }


def collect_warnings(*results: dict) -> list[str]:
    warnings: list[str] = []
    for result in results:
        warnings.extend(result.get("warnings", []) or [])
    return warnings


def manual_assets(cfg, price: dict) -> tuple[dict | None, dict | None]:
    """手动报数的两项资产，都**计入分子**：稳定币（USD 计价）与人民币活钱。

    - 稳定币：USDT / USDC 按 1:1 锚定 USD，用与 BTC 同一份实时汇率折成人民币。
      因此汇率波动会真实改变完成度——现金类资产也有了汇率敞口。
    - 人民币活钱：余额宝一类，本币计价，不涉汇率。

    两项都没有公开数据源，数量由本人手动更新。返回 (stablecoin, cash_cny)，
    任一未启用就返回 None，调用方按 0 处理。
    """
    fx = float(price.get("usd_cny") or 0.0)

    stable = None
    spec = cfg.get("stablecoin") or {}
    holdings = spec.get("holdings") or []
    if spec.get("enabled", False) and holdings:
        rows = []
        for item in holdings:
            amount = float(item.get("amount") or 0.0)
            rows.append(
                {
                    "asset": str(item.get("asset") or "").upper(),
                    "amount": amount,
                    "value_cny": round(amount * fx, 2),
                }
            )
        units = sum(r["amount"] for r in rows)
        stable = {
            "holdings": rows,
            "total_units": round(units, 2),
            "usd_cny": fx,
            "value_cny": round(units * fx, 2),
            "snapshot_date": spec.get("snapshot_date"),
            "note": spec.get("note"),
            "included_in_assets": True,
        }

    cash = None
    cspec = cfg.get("cash_cny") or {}
    if cspec.get("enabled", False):
        balance = float(cspec.get("balance_cny") or 0.0)
        cash = {
            "value_cny": round(balance, 2),
            "snapshot_date": cspec.get("snapshot_date"),
            "note": cspec.get("note"),
            "included_in_assets": True,
        }
    return stable, cash


def _days_to_target(
    remaining: float, start: float, daily: float, annual: float
) -> float | None:
    """解「多久后达到目标」：目标 = A(1+r)^n + C·((1+r)^n − 1)/r。

    反解 n = ln((目标 + C/r) / (起点 + C/r)) / ln(1+r)，按日复利。
    年化 ≤ 0 时退化为纯定投（不猜测负收益下的路径，那没有意义）。

    ⚠️ 2026-10-31 修正：入参 remaining 是**缺口**（目标 − 起点），
    不是目标本身。分子必须是「目标 + C/r」，即 (remaining + start) + C/r。
    原实现直接用 remaining，等于把目标当成缺口来解，系统性低估天数——
    资产越接近目标，低估越严重（A→T 时会算出「已经到达」）。
    实测 2026-10-31 当天：错解 1486 天（2030-11-25），正解 1626 天（2031-01-13）。
    """
    if daily <= 0:
        return None
    if annual <= 0:
        return remaining / daily
    rd = (1 + annual) ** (1 / 365) - 1
    if rd <= 0:
        return remaining / daily
    num = remaining + start + daily / rd
    den = start + daily / rd
    if den <= 0 or num <= den:
        return 0.0
    return math.log(num / den) / math.log(1 + rd)


def projection(
    remaining: float,
    usd_cny: float,
    contribution: dict | None,
    assets: dict | None = None,
    expected_return: dict | None = None,
) -> dict | None:
    """按「真实定投额 + 资产增值」外推达成时间。

    两个输入缺一不可：
      - **定投额**（contribution）：自己能控制的变量，不会被行情扭曲。
        只用历史增速的问题是——涨得快不等于进度快，跌的时候还会推出
        「永远达不到」的荒谬结论。
      - **资产增值**（assets × expected_return）：已有持仓也会长，
        只算买入会系统性低估速度。加权方式与「每小时被动收入」一致，
        按当前市值权重。

    这是「外推」，不是预测：它假设定投不中断、收益率恒定。
    稳定币的限额活动利率会结束，单点假设不可靠，所以同时给出悲观/基准/乐观三档。
    """
    if remaining <= 0:
        return None

    contrib = contribution or {}
    btc_usdt = float(contrib.get("btc_usdt_per_day") or 0.0)
    sp500 = float(contrib.get("sp500_cny_per_day") or 0.0)
    ndx = float(contrib.get("ndx100_cny_per_day") or 0.0)
    fx = float(usd_cny or 0.0)

    base = {
        "btc_usdt_per_day": round(btc_usdt, 2),
        "sp500_cny_per_day": round(sp500, 2),
        "ndx100_cny_per_day": round(ndx, 2),
        "usd_cny": round(fx, 4),
    }

    # 缺汇率时不拿 0 冒充，否则比特币定投会被悄悄算成 0。
    if btc_usdt > 0 and fx <= 0:
        return {
            **base,
            "btc_cny_per_day": None,
            "daily_cny": None,
            "monthly_cny": None,
            "days_to_target": None,
            "eta": None,
            "reason": "缺少美元汇率，无法折算比特币定投额",
        }

    btc_cny = btc_usdt * fx
    daily = btc_cny + sp500 + ndx
    base.update(
        {
            "btc_cny_per_day": round(btc_cny, 2),
            "daily_cny": round(daily, 2),
            "monthly_cny": round(daily * 30, 2),
        }
    )

    if daily <= 0:
        return {**base, "days_to_target": None, "eta": None, "reason": "定投额为 0，无法外推"}

    # 按当前市值权重加权预期年化，与「每小时被动收入」同口径。
    # 五项资产都要列进权重字典：漏掉稳定币/活钱会让它们的市值参与增长、
    # 却不参与收益率加权，算出来的加权年化会凭空偏高。
    values = {"btc": 0.0, "sp500": 0.0, "ndx100": 0.0, "stablecoin": 0.0, "cash_cny": 0.0}
    for key in values:
        values[key] = float((assets or {}).get(key) or 0.0)
    start = sum(values.values())
    weights = (
        {k: v / start for k, v in values.items()}
        if start > 0
        else {k: 0.0 for k in values}
    )

    er = expected_return or {}
    scenarios: dict[str, dict] = {}
    for name, suffix in (("low", "_low"), ("base", ""), ("high", "_high")):
        rate = sum(weights[k] * float(er.get(k + suffix) or 0.0) for k in values)
        days = _days_to_target(remaining, start, daily, rate)
        days_int = None if days is None else int(days)
        scenarios[name] = {
            "rate": round(rate, 4),
            "days": days_int,
            "eta": (
                None
                if days_int is None
                else (_now().date() + timedelta(days=days_int)).isoformat()
            ),
        }

    chosen = scenarios["base"]
    return {
        **base,
        "assets_cny": round(start, 2),
        "weights": {k: round(v, 4) for k, v in weights.items()},
        "weighted_rate": chosen["rate"],
        "scenarios": scenarios,
        "days_to_target": chosen["days"],
        "eta": chosen["eta"],
        "reason": None,
    }


def capital_for_years(annual_expense: float, years: float, rate: float) -> float:
    """年金现值：给定年支出与年数，需要多少本金才够花完。

    「花完」不是「耗尽到 0」——它是「刚好在第 years 年末用完」，
    这正是两段式阶段 A 需要的口径：不需要永续，只需要撑到退出条件。

    rate 为 0 时退化为简单乘法（不做贴现）。
    """
    if years <= 0 or annual_expense <= 0:
        return 0.0
    if rate <= 0:
        return annual_expense * years
    return annual_expense * (1 - (1 + rate) ** -years) / rate


def years_from_capital(capital: float, annual_expense: float, rate: float) -> float | None:
    """反过来：给定本金，按年支出能撑多少年。

    返回 None 表示**永续**（本金产生的收益已经覆盖支出，不会耗尽）。
    返回 0 表示立刻就撑不住（本金或支出非正）。

    推导：A(t) = P(1+r)^t − (D/r)((1+r)^t − 1)，
    令 A(t)=0 得 (1+r)^t = k/(k−P)，其中 k = D/r。
    当 P ≥ k 时无解（资产单调不减），即永续。
    """
    if annual_expense <= 0:
        return None  # 没有净支出，永远花不完
    if capital <= 0:
        return 0.0
    if rate <= 0:
        return capital / annual_expense
    k = annual_expense / rate
    if capital >= k:
        return None  # 永续
    return math.log(k / (k - capital)) / math.log(1 + rate)


def critical_rate(annual_expense: float, capital: float) -> float | None:
    """永续所需的临界收益率 = 年净支出 ÷ 本金。

    低于提取率 → 保守假设下就成立；高于权益类长期实际回报 → 那是在赌。
    见 docs/FIRE-LIFE-PLAN.md §7.5。
    """
    if capital <= 0 or annual_expense <= 0:
        return None
    return annual_expense / capital


def two_phase(cfg, *, capital: float, annual_net_expense: float) -> dict | None:
    """两段式口径：这笔钱能撑多久（不是「够不够永续」）。

    背景见 docs/FIRE-ROADMAP.md。核心区别：
      - FIRE 目标（fire.target_cny）= 永续口径，回答「还要攒多少」，用于进度条
      - 本函数                    = 有期限口径，回答「能撑多久」，用于决策

    ⚠️ 本函数**不改变 FIRE 目标**。加资产不能让目标变化，这条在
    tests/test_fire_core.py 里钉死了；这里只读取实时市值做推演。
    """
    spec = cfg.get("timeline") or {}
    if not spec:
        return None

    rate = float(cfg.fire.get("withdrawal_rate") or 0.0)
    years = years_from_capital(capital, annual_net_expense, rate)
    start_age = spec.get("start_age")

    horizon = []
    for n in (5, 10, 15, 20, 30, 40):
        horizon.append(
            {
                "years": n,
                "capital_cny": round(capital_for_years(annual_net_expense, n, rate), 2),
                "covered": capital >= capital_for_years(annual_net_expense, n, rate),
            }
        )

    return {
        "capital_cny": round(capital, 2),
        "annual_net_expense_cny": round(annual_net_expense, 2),
        "rate": rate,
        # None = 永续
        "years": None if years is None else round(years, 1),
        "perpetual": years is None,
        "exhaust_age": (
            None if years is None or start_age is None else round(float(start_age) + years, 1)
        ),
        "critical_rate": (
            None
            if critical_rate(annual_net_expense, capital) is None
            else round(critical_rate(annual_net_expense, capital), 4)
        ),
        "graduation": spec.get("graduation"),
        "start_age": start_age,
        "monthly_contribution": spec.get("monthly_contribution"),
        "horizon": horizon,
    }


def allocation_split(
    cfg,
    btc_value: float,
    sp500_value: float,
    ndx_value: float = 0.0,
    stablecoin_value: float = 0.0,
    cash_value: float = 0.0,
) -> dict | None:
    """五项资产的市值占比，用于展示配置失衡程度。

    ⚠️ 只读展示，**不改变分子构成**。加资产不能让目标变化（测试钉死）。

    ⚠️ `in_range` 只按**标普500**判断：纳指100 与标普相关性 0.9 以上，
    都是美股成长敞口；稳定币和人民币活钱是现金等价物，不算权益敞口。
    所以 `equity_pct` 才是「权益类占比」，不要把现金也算进去。
    """
    spec = cfg.get("asset_allocation") or {}
    if not spec.get("enabled", False):
        return None

    total = (
        float(btc_value) + float(sp500_value) + float(ndx_value)
        + float(stablecoin_value) + float(cash_value)
    )
    if total <= 0:
        return None

    rng = list(spec.get("sp500_target_range") or [])
    low = rng[0] if len(rng) > 0 else None
    high = rng[1] if len(rng) > 1 else None

    btc_pct = float(btc_value) / total
    sp_pct = float(sp500_value) / total
    ndx_pct = float(ndx_value) / total
    stable_pct = float(stablecoin_value) / total
    cash_pct = float(cash_value) / total

    return {
        "btc_pct": round(btc_pct, 4),
        "sp500_pct": round(sp_pct, 4),
        "ndx100_pct": round(ndx_pct, 4),
        "stablecoin_pct": round(stable_pct, 4),
        "cash_pct": round(cash_pct, 4),
        "equity_pct": round(sp_pct + ndx_pct, 4),
        # 保留旧字段以免下游读不到；清仓后它恒为 100%，意义有限，
        # 真正该看的是 equity_pct（权益）与两项现金占比。
        "non_btc_pct": round(1 - btc_pct, 4),
        "sp500_target_range": [low, high],
        "in_range": bool(low is not None and high is not None and low <= sp_pct <= high),
        "note": spec.get("note"),
    }


def compute(
    cfg,
    *,
    price: dict,
    btc: dict,
    sp500: dict,
    history: list[dict],
    ndx100: dict | None = None,
    stablecoin: dict | None = None,
    cash_cny: dict | None = None,
    as_of: str | None = None,
) -> dict:
    monthly, plan_summary = lifeplan_mod.resolve_monthly(cfg)
    rate = float(cfg.fire.withdrawal_rate)
    # 目标按「组合需覆盖的月开销」算：咖啡师 FIRE 下兼职收入先抵扣一部分。
    # plan_summary 为 None（life_plan 未启用）时退回全部月开销，行为与旧口径一致。
    net_monthly = (plan_summary or {}).get("net_monthly_expense", monthly)
    # ⚠️ 不工作门槛按 target_profile 算（默认 = 当前 profile，见 lifeplan.target_profile_name）。
    # 与 net_monthly 分开，避免「临时试算别的档位」把进度条分母一起拖走：
    # 切到常规档（mudanjiang-rent-normal）时，月开销变 ¥2,754 用于门槛，
    # 但 target 仍按极简档 ¥1,454 算 ¥204,000.00。
    target_net = (plan_summary or {}).get("target_net_monthly_expense", net_monthly)
    target = target_cny(target_net, rate)
    # 完全 FIRE 门槛（2026-11-05）：完全不工作，不扣兼职收入。
    # life_plan 未启用时退回「全额月开销 × 12 ÷ 提取率」，行为与旧口径一致。
    full_fire_target = float(
        (plan_summary or {}).get("full_fire_target_cny")
        or target_cny(monthly, rate)
    )

    btc_qty = float(btc.get("total_btc") or 0.0)
    btc_value = btc_qty * float(price["btc_cny"])

    sp500_value = float(sp500.get("market_value") or 0.0)
    sp500_invested = float(sp500.get("invested") or 0.0)

    # 纳指100（2026-10-27 加入）：三只场外 QDII，已停止定投，份额固定。
    # 不传时按 0 处理，行为与加入前完全一致——mock 数据与旧调用点不受影响。
    ndx100 = ndx100 or {}
    ndx_value = float(ndx100.get("market_value") or 0.0)
    ndx_invested = float(ndx100.get("invested") or 0.0)

    # 手动维护的两项（2026-11-13 加入）：由 update.py 用 manual_assets() 折算后传入。
    # 不传时按 0 处理，行为与加入前完全一致——旧调用点与历史快照不受影响。
    # ⚠️ 刻意不在 compute() 里读 config：那会让每次调用都悄悄多出两项资产，
    #    口径测试会失去意义，也没法复现「只有三项资产」的历史快照。
    stable_value = float((stablecoin or {}).get("value_cny") or 0.0)
    cash_value = float((cash_cny or {}).get("value_cny") or 0.0)

    total = btc_value + sp500_value + ndx_value + stable_value + cash_value
    progress = total / target if target else 0.0
    remaining = max(target - total, 0.0)

    # --- 出发门槛（2026-10-31 新增）---
    # 全职方案下，「能不能走」由这笔钱决定，而不是 ¥204,000.00。
    # ⚠️ 它不改 target_cny，只是并行的一条线：两条线回答两个不同问题。
    gate = lifeplan_mod.departure_gate(cfg)
    departure = None
    if gate:
        departure = {
            **gate,
            "assets_cny": round(total, 2),
            "progress_low": (total / gate["low_cny"]) if gate["low_cny"] else 0.0,
            "progress_high": (total / gate["high_cny"]) if gate["high_cny"] else 0.0,
            "remaining_low_cny": round(max(gate["low_cny"] - total, 0.0), 2),
            "remaining_high_cny": round(max(gate["high_cny"] - total, 0.0), 2),
            "reached_low": total >= gate["low_cny"],
            "reached_high": total >= gate["high_cny"],
        }

    # --- 全职情景（云南省内 + 独自租房）---
    # 只展示现金流与外推，**绝不进入 target_cny**：
    # 全职净收入 > 月开销，代进目标公式会得到负数，那个负数没有意义。
    # 北京已排除，只保留云南省内一个口径（省内具体城市待定）。
    # fulltime_mudanjiang 已从配置移除，读取为 None；保留这个键是为了让
    # render/site 优雅降级，不破坏下游读取。
    fulltime = None
    fulltime_mudanjiang = None
    for _key, _slot in (("fulltime", "fulltime"), ("fulltime_mudanjiang", "fulltime_mudanjiang")):
        ft = lifeplan_mod.fulltime_income(cfg, _key)
        if not ft:
            continue
        # 阶段 A 个人月开销：默认等于完整月开销；若岗位包吃住，则扣除被覆盖的项
        # （房租/取暖/物业费/食品/饮用水），个人只付通讯、交通、探亲、医疗缓冲等。
        # ⚠️ 这一步只影响「阶段 A 盈余」的分母，**绝不改变 target_cny**（见下方不变量测试）。
        _spec = ((cfg.get("fire") or {}).get(_key)) or {}
        # 阶段 A 个人开销按「这个岗位所在城市」的 profile 算，不是按当前激活 profile。
        # 否则同一个岗位的盈余会随「你把 profile 切到哪」而变，看板上会莫名跳动。
        # 2026-11-05 起不包吃住，走的正是 elif 分支：完整月开销 ¥1,454。
        _spec_profile = _spec.get("life_plan_profile")
        if _spec.get("room_and_board_covered"):
            stage_a = lifeplan_mod.monthly_excluding(
                cfg, _spec.get("covered_keys"), _spec_profile
            )
        elif _spec_profile:
            # 不包吃住：用岗位所在城市的完整月开销，而不是当前激活 profile 的
            stage_a = lifeplan_mod.monthly_total(cfg, _spec_profile)
        else:
            stage_a = monthly
        _surplus = ft["net_monthly_cny"] - stage_a
        _res = {
            **ft,
            "monthly_expense": round(monthly, 2),
            "stage_a_monthly_expense": round(stage_a, 2),
            "room_and_board_covered": bool(_spec.get("room_and_board_covered")),
            "surplus_monthly_cny": round(_surplus, 2),
            "covered": _surplus >= 0,
            "projection": None,
        }
        if _slot == "fulltime":
            fulltime = _res
        else:
            fulltime_mudanjiang = _res

    # --- 本金 ---
    # 标普500：优先取 config 手工值，否则用 sp500-dca 仓库的累计投入（精确值）
    cfg_basis = cfg.get("cost_basis") or {}
    sp500_basis = cfg_basis.get("sp500_cny")
    sp500_basis = sp500_invested if sp500_basis is None else float(sp500_basis)

    # 比特币：从持仓备注的「均价 $xx/BTC」推算，按当前汇率折算成人民币。
    # 这是估算——真实成本取决于买入当时的汇率，这里的折算会引入偏差，展示时要标注。
    btc_cost_usd = btc.get("cost_basis_usd")
    btc_basis = (
        float(btc_cost_usd) * float(price["usd_cny"]) if btc_cost_usd is not None else None
    )

    # 纳指100：成本由 config 的 shares × cost_nav 直接算出，无需外部来源
    ndx_basis = ndx_invested if ndx_invested > 0 else None

    # 稳定币与活钱：现金等价物，按面值计入累计投入本金（不产生浮盈浮亏）。
    # ⚠️ 只统计当前仍持有的类别；清仓的比特币没有成本价了，btc_basis 为 None，
    #    所以累计投入本金会出现台阶——这是口径边界，不是亏损，见 CHANGELOG。
    stable_basis = stable_value if stable_value > 0 else None
    cash_basis = cash_value if cash_value > 0 else None

    parts = [p for p in (btc_basis, sp500_basis, ndx_basis, stable_basis, cash_basis) if p is not None]
    total_basis = sum(parts) if parts else None

    now = _now(cfg.automation.get("timezone", "Asia/Shanghai"))
    stamp = as_of or now.isoformat(timespec="seconds")

    # 两条外推：主口径（兼职兜底）与全职情景。同一个 projection()，只换定投额。
    proj = None
    if cfg.display.get("show_projection"):
        proj = projection(
            remaining,
            price.get("usd_cny"),
            cfg.get("contribution"),
            {
                "btc": btc_value,
                "sp500": sp500_value,
                "ndx100": ndx_value,
                "stablecoin": stable_value,
                "cash_cny": cash_value,
            },
            cfg.get("expected_return"),
        )

    for _ft in (fulltime, fulltime_mudanjiang):
        if _ft is not None and proj is not None:
            # 全职盈余并入标普500 日投：比特币日投是固定 USDT 额度，不随盈余变。
            # 盈余 ≤ 0 时不并入——否则会静默拉长外推，看起来像「全职更慢」。
            if _ft["surplus_monthly_cny"] > 0:
                base_contrib = cfg.get("contribution") or {}
                ft_contrib = dict(base_contrib)
                ft_contrib["sp500_cny_per_day"] = float(
                    base_contrib.get("sp500_cny_per_day") or 0.0
                ) + _ft["surplus_monthly_cny"] * 12 / 365
                _ft["projection"] = projection(
                    remaining,
                    price.get("usd_cny"),
                    ft_contrib,
                    {
                        "btc": btc_value,
                        "sp500": sp500_value,
                        "ndx100": ndx_value,
                        "stablecoin": stable_value,
                        "cash_cny": cash_value,
                    },
                    cfg.get("expected_return"),
                )

    # --- 三个门槛 + 主进度（2026-11-05）---
    # 以前只有一条「不工作门槛」，实为咖啡师 FIRE（含兼职）。现在并列三条：
    #   出发门槛   → 能不能动身（阶段 A 有工作，现金流为正）
    #   咖啡师 FIRE → 有兼职，资产只覆盖 (月开销 − 兼职净收入)
    #   完全 FIRE   → 完全不工作，资产覆盖全额月开销
    # ⚠️ 只新增展示层数据；target_cny / progress / remaining / 外推的既有语义
    #    一律不动，避免污染 history.json 的逐日留档和既有结论。
    def _goal(key: str, label: str, subtitle: str, value: float, note: str) -> dict:
        ratio = (total / value) if value else 0.0
        return {
            "key": key,
            "label": label,
            "subtitle": subtitle,
            "target_cny": round(value, 2),
            "progress": ratio,
            "progress_pct": round(ratio * 100, 4),
            "remaining_cny": round(max(value - total, 0.0), 2),
            "reached": total >= value,
            "note": note,
        }

    dep_low = float((departure or {}).get("low_cny") or 0.0)
    dep_high = float((departure or {}).get("high_cny") or 0.0)
    goal_items = [
        _goal(
            "departure", "出发门槛", "能不能动身",
            dep_low,
            "医疗应急 + 空窗期月开销（不含一次性支出）；区间上沿 "
            f"{dep_high:,.2f}（更保守的医疗额度与更长空窗）",
        ),
        _goal(
            "coffee_fire", "咖啡师 FIRE 门槛", "有兼职（每周 3 天 × 4h）",
            float(target),
            f"资产覆盖 (月开销 − 兼职净收入) = {target_net:,.2f}/月",
        ),
        _goal(
            "full_fire", "完全 FIRE 门槛", "完全不工作",
            full_fire_target,
            "资产覆盖全额月开销，不依赖任何劳动收入",
        ),
    ]
    primary_key = str(cfg.display.get("primary_progress") or "departure").strip()
    valid_keys = {g["key"] for g in goal_items}
    if primary_key not in valid_keys:
        raise ValueError(
            f"display.primary_progress 只能是 {sorted(valid_keys)}，当前 {primary_key!r}。"
            "不静默回落——回落会让主进度悄悄换一个门槛。"
        )
    for g in goal_items:
        g["is_primary"] = g["key"] == primary_key
    # 主进度排第一，其余按出发 → 咖啡师 → 完全的自然顺序。
    goal_items.sort(key=lambda g: (not g["is_primary"], ["departure", "coffee_fire", "full_fire"].index(g["key"])))
    primary = next(g for g in goal_items if g["is_primary"])

    return {
        "as_of": stamp,
        "as_of_date": now.strftime("%Y-%m-%d"),
        "fire": {
            "monthly_expense": monthly,
            # 组合需要覆盖的月开销（已扣兼职净收入）；没配兼职时等于 monthly_expense
            # ⚠️ 这是「当前城市」口径，用于阶段 A 与出发门槛。
            "net_monthly_expense": net_monthly,
            # 不工作门槛用的净支出（按 life_plan.target_profile）。
            # 两者只有在 profile ≠ target_profile 时才不同，见 lifeplan.target_profile_name。
            "target_net_monthly_expense": round(target_net, 2),
            "labor_income": (plan_summary or {}).get("labor_income"),
            "withdrawal_rate": rate,
            "annual_expense": monthly * 12,
            # 咖啡师 FIRE 门槛（有兼职）—— 既有 target_cny，语义未变。
            "target_cny": round(target, 2),
            # 完全 FIRE 门槛（完全不工作）—— 新增。
            "full_fire_target_cny": round(full_fire_target, 2),
            "target_with_one_off": (plan_summary or {}).get("target_with_one_off"),
            "monthly_override": bool((plan_summary or {}).get("override")),
        },
        "life_plan": plan_summary,
        # 两段式推演：这笔钱能撑多久。**不参与上面的 target_cny 计算**，
        # 只回答「够不够撑到回北京那天」，见 docs/FIRE-ROADMAP.md。
        "two_phase": two_phase(cfg, capital=total, annual_net_expense=net_monthly * 12),
        # 资产占比：只用于展示失衡程度，不改变分子构成
        "allocation": allocation_split(
            cfg, btc_value, sp500_value, ndx_value, stable_value, cash_value
        ),
        "assets": {
            "total_cny": round(total, 2),
            "progress": progress,
            "progress_pct": round(progress * 100, 4),
            "remaining_cny": round(remaining, 2),
            "btc": {
                "qty": round(btc_qty, 8),
                "price_cny": float(price["btc_cny"]),
                "value_cny": round(btc_value, 2),
                "snapshot_date": btc.get("snapshot_date"),
                "stale_days": btc.get("stale_days"),
                "positions": list(btc.get("positions", [])),
            },
            "sp500": {
                "value_cny": round(sp500_value, 2),
                "invested_cny": round(sp500_invested, 2),
                "profit_cny": round(sp500.get("profit") or 0.0, 2),
                "return_rate": sp500.get("return_rate"),
                "latest_nav_date": sp500.get("latest_nav_date"),
                "funds": sp500.get("funds", []),
            },
            "ndx100": {
                "value_cny": round(ndx_value, 2),
                "invested_cny": round(ndx_invested, 2),
                "profit_cny": round(ndx100.get("profit") or 0.0, 2),
                "return_rate": ndx100.get("return_rate"),
                "latest_nav_date": ndx100.get("latest_nav_date"),
                "funds": ndx100.get("funds", []),
            },
            # 稳定币 / 人民币活钱：计入分子的两项手动维护资产。
            "stablecoin": stablecoin,
            "cash_cny": cash_cny,
        },
        "cost_basis": {
            "btc_cny": round(btc_basis, 2) if btc_basis is not None else None,
            "btc_estimated": btc_basis is not None,
            "sp500_cny": round(sp500_basis, 2),
            "ndx100_cny": round(ndx_basis, 2) if ndx_basis is not None else None,
            "stablecoin_cny": round(stable_basis, 2) if stable_basis is not None else None,
            "cash_cny": round(cash_basis, 2) if cash_basis is not None else None,
            "total_cny": round(total_basis, 2) if total_basis is not None else None,
            "profit_cny": round(total - total_basis, 2) if total_basis is not None else None,
        },
        "price": price,
        "passive_income": (
            passive_income(
                cfg,
                btc_value=btc_value,
                sp500_value=sp500_value,
                ndx_value=ndx_value,
                stablecoin_value=stable_value,
                cash_value=cash_value,
                monthly_expense=monthly,
            )
            if cfg.display.get("show_passive_income", True)
            else None
        ),
        "projection": proj,
        # 出发门槛与全职情景（2026-10-31）。两者都**不改变上面的 target_cny**：
        # 出发门槛回答「能不能走」，全职情景回答「走之后攒得多快」。
        "departure": departure,
        # 三级门槛汇总（2026-11-05）：items 已按主进度优先排序，
        # primary 是配置指定的那一条；三个门槛的金额都在这里，渲染层不重算。
        "goals": {
            "primary": primary_key,
            "items": goal_items,
        },
        "full_fire": {
            "target_cny": round(full_fire_target, 2),
            "monthly_expense": round(float((plan_summary or {}).get("full_fire_monthly_expense") or monthly), 2),
            "progress_pct": round(total / full_fire_target * 100, 4) if full_fire_target else 0.0,
            "remaining_cny": round(max(full_fire_target - total, 0.0), 2),
            "reached": total >= full_fire_target,
        },
        "fulltime": fulltime,
        "fulltime_mudanjiang": fulltime_mudanjiang,
        "sources": {
            "btc": btc.get("available", False),
            "sp500": sp500.get("available", False),
        },
        "warnings": collect_warnings(btc, sp500),
    }
