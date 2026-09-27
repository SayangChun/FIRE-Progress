"""FIRE 生活规划：把「月开销」变成一份可追溯的逐项预算。

口径（唯一权威定义，与 fire.py 配合）：

    FIRE 目标资产 = 月开销 × 12 ÷ 提取率
    月开销        = Σ life_plan.profiles[profile].items[].monthly

「月开销」不再是一个拍脑袋的数字，而是逐项相加得到，每一项都在
config.yaml 里标注了依据。这样改任何一项都会自动传导到 FIRE 目标。

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
GROUP_ORDER = ["住房与水电燃气", "日常开销", "医疗与保障", "风险缓冲"]

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


def _target(monthly: float, rate: float) -> float:
    return monthly * 12 / rate


def summary(cfg) -> dict:
    """当前方案的完整摘要，供 README 与计算核心消费。"""
    prof = active_profile(cfg)
    rate = float(cfg.fire.withdrawal_rate)
    monthly = monthly_total(cfg)
    extra = one_off_total(cfg)
    target = _target(monthly, rate)

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
        data = dict(data)
        data.update(
            {
                "derived_monthly_expense": data["monthly_expense"],
                "monthly_expense": monthly,
                "annual_expense": round(monthly * 12, 2),
                "target_cny": round(_target(monthly, rate), 2),
                "target_with_one_off": round(
                    _target(monthly, rate) + data["one_off_total"], 2
                ),
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
