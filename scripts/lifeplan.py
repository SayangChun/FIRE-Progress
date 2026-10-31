"""FIRE 生活规划：把「月开销」变成一份可追溯的逐项预算。

口径（唯一权威定义，与 fire.py 配合）：

    FIRE 目标资产 = 组合需覆盖月开销 × 12 ÷ 提取率
    月开销        = Σ life_plan.profiles[profile].items[].monthly
    组合需覆盖    = 月开销 − 兼职净收入

「月开销」不再是一个拍脑袋的数字，而是逐项相加得到，每一项都在
config.yaml 里标注了依据。这样改任何一项都会自动传导到 FIRE 目标。

「兼职净收入」对应咖啡师 FIRE（fire.labor_income，2026-10-20 起）：
FIRE 之后仍做低压力、可随时停的兼职，收入覆盖一部分开销，
所以资产不必覆盖全部开销。净收入为 0 时公式退化为传统 FIRE
「月开销 × 12 ÷ 提取率」——两种口径共用同一套代码。

2026-10-31 起新增两个口径，**都不改变上面这条主线公式**：

1. `fulltime_income()` —— 全职净收入。只做现金流展示，**不参与目标计算**。
   全职净收入必然大于月开销，代进公式会得负数，那个负数没有意义。
2. `departure_gate()` —— 出发门槛 = 医疗专项 + 一次性搬家 + 空窗期开销。
   全职方案下它才是「能不能走」的约束，比 ¥205,953 更早成为瓶颈。
   ¥205,953 保留原义：**能不能不工作**（兼职兜底的永续线）。

为什么一次性支出不进月开销
--------------------------
搬家、押金、家具、购房款是一次性消耗，不产生永续现金流。
如果把它们摊进「月开销」，会同时虚增月开销与 FIRE 目标——
而 FIRE 目标的本意是「一个能永久覆盖生活费的资产池」。
所以它们单列在 life_plan.one_off，用「目标 + 一次性支出」另算。

注意：如果将来改为「买房」，购房款同样属于一次性支出，
并且月开销里要相应去掉房租、加上维修摊销——两条腿都要动，
只改一条会得到错误的结果。
"""

from __future__ import annotations

# 分组展示顺序；未列出的分组排在后面
GROUP_ORDER = ["住房与水电燃气", "日常开销", "医疗与应急"]

_REQUIRED_ITEM_FIELDS = ("key", "label", "monthly")


class LifePlanError(ValueError):
    """配置写错时立刻失败。

    刻意不做「取默认值」的兜底：月开销是 FIRE 目标的分母来源，
    静默回落会让目标悄悄跑偏，而看板上完全看不出来。
    """


def _plan(cfg) -> dict:
    return cfg.get("life_plan") or {}


def enabled(cfg) -> bool:
    return bool(_plan(cfg).get("enabled"))


def active_profile(cfg) -> dict:
    plan = _plan(cfg)
    if not plan.get("enabled"):
        raise LifePlanError("life_plan.enabled 为 false，无法读取生活规划")
    name = plan.get("profile")
    profiles = plan.get("profiles") or {}
    if not profiles:
        raise LifePlanError("life_plan.profiles 为空")
    if name not in profiles:
        raise LifePlanError(
            f"life_plan.profile = {name!r} 不存在；可选：{sorted(profiles)}"
        )
    prof = dict(profiles[name])
    prof["profile_name"] = name
    return prof


def items(cfg) -> list[dict]:
    """当前方案的逐项月开销（已做字段与符号校验）。"""
    prof = active_profile(cfg)
    raw = prof.get("items") or []
    if not raw:
        raise LifePlanError(f"方案 {prof['profile_name']!r} 的 items 为空")

    out: list[dict] = []
    seen: set[str] = set()
    for idx, it in enumerate(raw):
        for field in _REQUIRED_ITEM_FIELDS:
            if field not in it:
                raise LifePlanError(
                    f"{prof['profile_name']}.items[{idx}] 缺少字段 {field!r}"
                )
        key = str(it["key"])
        if key in seen:
            raise LifePlanError(f"{prof['profile_name']}.items 中 key 重复：{key}")
        seen.add(key)

        monthly = float(it["monthly"])
        if monthly < 0:
            raise LifePlanError(f"{prof['profile_name']}.items[{idx}] 金额为负")
        out.append(
            {
                "key": key,
                "group": it.get("group") or "其他",
                "label": str(it["label"]),
                "monthly": round(monthly, 2),
                "note": str(it.get("note") or ""),
            }
        )
    return out


def monthly_total(cfg) -> float:
    return round(sum(it["monthly"] for it in items(cfg)), 2)


def by_group(cfg) -> list[dict]:
    """按分组聚合，供 README 表格展示小计。"""
    groups: dict[str, list[dict]] = {}
    for it in items(cfg):
        groups.setdefault(it["group"], []).append(it)

    ordered = [g for g in GROUP_ORDER if g in groups]
    ordered += [g for g in groups if g not in GROUP_ORDER]

    return [
        {
            "group": name,
            "items": groups[name],
            "subtotal": round(sum(r["monthly"] for r in groups[name]), 2),
        }
        for name in ordered
    ]


def one_off(cfg) -> list[dict]:
    rows: list[dict] = []
    for idx, it in enumerate(_plan(cfg).get("one_off") or []):
        if "label" not in it or "amount" not in it:
            raise LifePlanError(f"life_plan.one_off[{idx}] 需要 label 与 amount")
        amount = float(it["amount"])
        if amount < 0:
            raise LifePlanError(f"life_plan.one_off[{idx}] 金额为负")
        rows.append(
            {
                "key": str(it.get("key") or f"one_off_{idx}"),
                "label": str(it["label"]),
                "amount": round(amount, 2),
                "note": str(it.get("note") or ""),
            }
        )
    return rows


def one_off_total(cfg) -> float:
    return round(sum(r["amount"] for r in one_off(cfg)), 2)


# 月工时按 52 周 ÷ 12 折算，不按「每月 4 周」——
# 后者会把年工时少算约 8%（48 周 vs 52 周），让兼职收入系统性偏低。
WEEKS_PER_YEAR = 52
MONTHS_PER_YEAR = 12

_LABOR_REQUIRED = (
    "hourly_wage",
    "hours_per_week",
    "work_days_per_week",
    "transport_per_day",
)


def _income_from_spec(spec: dict, where: str, default_label: str) -> dict:
    """把「按时薪计的工作」换算成每月净收入。兼职与全职共用同一套算法。

    净收入 = 毛收入 − 工作增量消耗

    ⚠️ 只扣**因为工作才产生**的增量，不扣本来就要花的钱：
      - 交通：往返通勤，真增量
      - 餐食：在外吃饭比在家做贵出来的**差额**，不是一顿饭的全价
        （家里那顿的成本已经在 life_plan 的「食品」里，全额扣是重复计算）
      - 装备：防滑鞋等按年摊销
    这个区分是整段计算里最容易错的地方。扣多了会让目标虚高，
    等于拿「上班多花的钱」把「本来就要花的钱」又算了一遍。

    where 只用于报错定位（如 "fire.labor_income"），不参与计算。
    """
    for field in _LABOR_REQUIRED:
        if spec.get(field) is None:
            raise LifePlanError(
                f"{where} 缺少字段 {field!r}"
                "（enabled 为 true 时不能省略，否则净收入会静默算成 0）"
            )

    wage = float(spec["hourly_wage"])
    hours_week = float(spec["hours_per_week"])
    days_week = float(spec["work_days_per_week"])
    transport_day = float(spec["transport_per_day"])
    meal = float(spec.get("meal_increment_monthly") or 0.0)
    gear = float(spec.get("gear_monthly") or 0.0)
    commute_day = float(spec.get("commute_hours_per_day") or 0.0)

    for name, value in (
        ("hourly_wage", wage),
        ("hours_per_week", hours_week),
        ("work_days_per_week", days_week),
    ):
        if value <= 0:
            raise LifePlanError(f"{where}.{name} 必须为正数，当前 {value}")

    hours_month = hours_week * WEEKS_PER_YEAR / MONTHS_PER_YEAR
    days_month = days_week * WEEKS_PER_YEAR / MONTHS_PER_YEAR
    gross = hours_month * wage
    transport = days_month * transport_day
    cost = transport + meal + gear
    net = gross - cost

    if net <= 0:
        raise LifePlanError(
            f"{where} 算出的月净收入为 {net:.2f} 元（≤0）："
            "收入抵不上通勤与在外吃饭的增量消耗，这份工在财务上是倒贴的"
        )

    hours_day = hours_week / days_week
    occupied = days_month * (hours_day + commute_day)

    return {
        "enabled": True,
        "label": str(spec.get("label") or default_label),
        "hourly_wage": round(wage, 2),
        "hours_per_week": round(hours_week, 2),
        "hours_per_day": round(hours_day, 2),
        "hours_per_month": round(hours_month, 2),
        "work_days_per_month": round(days_month, 2),
        "gross_monthly_cny": round(gross, 2),
        "transport_cny": round(transport, 2),
        "meal_cny": round(meal, 2),
        "gear_cny": round(gear, 2),
        "cost_monthly_cny": round(cost, 2),
        "net_monthly_cny": round(net, 2),
        # 净时薪按纯工作时间算；等效时薪把通勤也计进去——后者才是真实代价
        "net_hourly_cny": round(net / hours_month, 2),
        "commute_hours_per_day": round(commute_day, 2),
        "occupied_hours_per_month": round(occupied, 2),
        "effective_hourly_cny": round(net / occupied, 2) if occupied else None,
        "note": str(spec.get("note") or ""),
    }


def labor_income(cfg) -> dict | None:
    """兼职净收入。fire.labor_income.enabled 为 false 时返回 None。

    这是 **FIRE 目标的兜底口径**：全职找不到时退回这里。
    全职本身走 fulltime_income()，绝不进入目标计算（见那个函数的说明）。
    """
    spec = ((cfg.get("fire") or {}).get("labor_income")) or {}
    if not spec.get("enabled"):
        return None
    return _income_from_spec(spec, "fire.labor_income", "兼职")


def fulltime_income(cfg) -> dict | None:
    """全职净收入。fire.fulltime.enabled 为 false 时返回 None。

    ⚠️ **不参与 FIRE 目标计算**，原因见 config.yaml 的注释：
    全职净收入必然大于月开销，代进 (月开销 − 净收入) × 12 ÷ 提取率
    会得到负数。负数不代表「超额完成」，而是这个公式在这里没有答案。

    所以本函数只输出现金流，由调用方单独展示；谁都不能把它塞进
    _net_after_labor，那会让目标变成负数并静默通过所有下游计算。
    """
    spec = ((cfg.get("fire") or {}).get("fulltime")) or {}
    if not spec.get("enabled"):
        return None
    return _income_from_spec(spec, "fire.fulltime", "全职")


def departure_gate(cfg) -> dict | None:
    """出发门槛 = 医疗专项应急金 + 一次性搬家 + 空窗期月开销。

    为什么需要它
    ------------
    旧口径把「攒够 ¥205,953」当成出发条件。但那是「靠资产覆盖净支出」的
    永续要求；一旦阶段 A 有全职工作，现金流为正，这个门槛就不再是出发条件。

    真正决定「能不能走」的是三笔钱：
      1. 医疗专项应急金 —— 零医保、住院 100% 自付，唯一防线（规划书 §5.4）
      2. 一次性搬家     —— 押金、运费、家具、过冬装备，取自 life_plan.one_off
      3. 空窗期月开销   —— 到牡丹江后到第一笔工资之间

    给出 low / high 两档：下沿是出发前必须到位的，上沿差额可以边工作边补。
    """
    spec = cfg.get("departure") or {}
    if not spec.get("enabled"):
        return None

    monthly = monthly_total(cfg)
    moving = one_off_total(cfg)
    med_low = float(spec.get("medical_reserve_low") or 0.0)
    med_high = float(spec.get("medical_reserve_high") or 0.0)
    gap_low = float(spec.get("gap_months_low") or 0.0)
    gap_high = float(spec.get("gap_months_high") or 0.0)

    if med_low <= 0 or gap_low <= 0:
        raise LifePlanError(
            "departure.medical_reserve_low / gap_months_low 必须为正数，"
            "否则出发门槛会静默算成只有搬家费"
        )
    if med_high < med_low or gap_high < gap_low:
        raise LifePlanError("departure 的上沿不能小于下沿")

    gap_low_cny = monthly * gap_low
    gap_high_cny = monthly * gap_high
    low = med_low + moving + gap_low_cny
    high = med_high + moving + gap_high_cny

    return {
        "enabled": True,
        "medical_low_cny": round(med_low, 2),
        "medical_high_cny": round(med_high, 2),
        "moving_cny": round(moving, 2),
        "gap_months_low": gap_low,
        "gap_months_high": gap_high,
        "gap_low_cny": round(gap_low_cny, 2),
        "gap_high_cny": round(gap_high_cny, 2),
        "low_cny": round(low, 2),
        "high_cny": round(high, 2),
        "note": str(spec.get("note") or ""),
    }



def _net_after_labor(monthly: float, labor: dict | None) -> float:
    """组合需要覆盖的月开销 = 月开销 − 兼职净收入。

    ⚠️ 结果 ≤ 0 时直接报错，不 clamp 到 0：
    「兼职收入 ≥ 月开销」意味着不用攒钱就能 FIRE，实务上几乎一定是
    时薪或工时填错了。静默算出一个目标 0 比报错危险得多。
    """
    net_labor = float(labor["net_monthly_cny"]) if labor else 0.0
    net = monthly - net_labor
    if net <= 0:
        raise LifePlanError(
            f"兼职净收入 {net_labor:,.2f} ≥ 月开销 {monthly:,.2f}："
            "组合需覆盖为 0，意味着不用攒钱就能 FIRE。"
            "先核对 fire.labor_income 的时薪与工时。"
        )
    return round(net, 2)


def _target(monthly: float, rate: float) -> float:
    return monthly * 12 / rate


def summary(cfg) -> dict:
    """当前方案的完整摘要，供 README 与计算核心消费。"""
    prof = active_profile(cfg)
    rate = float(cfg.fire.withdrawal_rate)
    monthly = monthly_total(cfg)
    extra = one_off_total(cfg)
    labor = labor_income(cfg)
    net_monthly = _net_after_labor(monthly, labor)
    target = _target(net_monthly, rate)

    return {
        "enabled": True,
        "profile": prof["profile_name"],
        "city": prof.get("city"),
        "province": prof.get("province"),
        "housing": prof.get("housing"),
        "household": prof.get("household"),
        "lifestyle": prof.get("lifestyle"),
        "headline": prof.get("headline") or "",
        "monthly_expense": monthly,
        # 组合需要覆盖的月开销：月开销 − 兼职净收入。没配兼职时等于月开销。
        "net_monthly_expense": net_monthly,
        "labor_income": labor,
        "annual_expense": round(monthly * 12, 2),
        "target_cny": round(target, 2),
        "groups": by_group(cfg),
        "one_off": one_off(cfg),
        "one_off_total": extra,
        "target_with_one_off": round(target + extra, 2),
        "override": False,
    }


def resolve_monthly(cfg) -> tuple[float, dict | None]:
    """返回 (月开销, 生活规划摘要)。

    优先级：
      1. life_plan.enabled 且 fire.monthly_expense 为 null -> 由逐项预算推导
      2. life_plan.enabled 且 fire.monthly_expense 有值     -> 用覆盖值（临时试算）
      3. life_plan 未启用                                   -> 必须显式给出月开销

    返回的摘要里 `override=True` 时，README 会标注「当前为手工覆盖值」，
    避免把试算结果误当成正式口径。
    """
    plan = _plan(cfg)
    override = cfg.fire.get("monthly_expense")

    if plan.get("enabled"):
        data = summary(cfg)
        if override is None:
            return data["monthly_expense"], data

        rate = float(cfg.fire.withdrawal_rate)
        monthly = float(override)
        net_monthly = _net_after_labor(monthly, data.get("labor_income"))
        target = _target(net_monthly, rate)
        data = dict(data)
        data.update(
            {
                "derived_monthly_expense": data["monthly_expense"],
                "monthly_expense": monthly,
                "net_monthly_expense": net_monthly,
                "annual_expense": round(monthly * 12, 2),
                "target_cny": round(target, 2),
                "target_with_one_off": round(target + data["one_off_total"], 2),
                "override": True,
            }
        )
        return monthly, data

    if override is None:
        raise LifePlanError(
            "fire.monthly_expense 为 null 且 life_plan 未启用：无法确定月开销。"
            "请二选一——启用 life_plan，或直接填一个月开销数字。"
        )
    return float(override), None
