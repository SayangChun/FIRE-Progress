"""FIRE 生活规划的回归测试。

这段逻辑容易被改坏且不易察觉：月开销是 FIRE 目标的分母来源，
一旦逐项预算与总数对不上、或一次性支出被误摊进月开销，
FIRE 目标就会悄悄跑偏，而看板上完全看不出来。

这里把几条关键性质钉住：
  1. 月开销 == 逐项相加（不是另一个地方写死的数字）
  2. FIRE 目标 == 月开销 × 12 ÷ 提取率
  3. 一次性支出**不进**月开销（这是最容易算错的一条）
  4. 切换方案后月开销随之变化
  5. profile 写错时直接报错，不静默回落

运行：python tests/test_life_plan.py
"""

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import config as cfgmod  # noqa: E402
from scripts import lifeplan as lifeplan_mod  # noqa: E402

cfg = cfgmod.load()
RATE = float(cfg.fire.withdrawal_rate)

failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}{(' -- ' + detail) if detail else ''}")
        failures.append(label)


def variant(**overrides):
    """基于当前配置造一个变体，用来测切换与覆盖。"""
    data = copy.deepcopy(dict(cfg))
    for dotted, value in overrides.items():
        node = data
        parts = dotted.split(".")
        for key in parts[:-1]:
            node = node[key]
        node[parts[-1]] = value
    return cfgmod.Config(data)


# ---------------------------------------------------------------- 1. 基本结构
print("生活规划的基本结构")
check("life_plan 已启用", lifeplan_mod.enabled(cfg))

profile_names = sorted((cfg.life_plan.get("profiles") or {}).keys())
check("至少定义了一个方案", len(profile_names) >= 1, f"实际 {profile_names}")

items = lifeplan_mod.items(cfg)
check("items 非空", len(items) > 0, f"实际 {len(items)} 项")
check(
    "每项都有 key / label / monthly",
    all(it.get("key") and it.get("label") and it.get("monthly") is not None for it in items),
)
check("金额均非负", all(it["monthly"] >= 0 for it in items))
check("key 不重复", len({it["key"] for it in items}) == len(items))

# ---------------------------------------------------------------- 2. 加总口径
print()
print("加总口径（本次改动的核心）")
monthly = lifeplan_mod.monthly_total(cfg)
item_sum = round(sum(it["monthly"] for it in items), 2)
check(
    "月开销 == 逐项相加",
    abs(monthly - item_sum) < 0.01,
    f"月开销 {monthly}，逐项和 {item_sum}",
)

group_sum = round(sum(g["subtotal"] for g in lifeplan_mod.by_group(cfg)), 2)
check("月开销 == 分组小计之和", abs(monthly - group_sum) < 0.01, f"{monthly} vs {group_sum}")

resolved, plan = lifeplan_mod.resolve_monthly(cfg)
check("resolve_monthly 返回与 monthly_total 一致", abs(resolved - monthly) < 0.01)

expected_target = monthly * 12 / RATE
check(
    "FIRE 目标 == 月开销 × 12 ÷ 提取率",
    abs(plan["target_cny"] - expected_target) < 0.01,
    f"{plan['target_cny']} vs {expected_target:.2f}",
)

# ---------------------------------------------------------------- 3. 一次性支出
print()
print("一次性支出不进月开销")
one_off = lifeplan_mod.one_off(cfg)
one_off_total = lifeplan_mod.one_off_total(cfg)
check("一次性支出已列出", len(one_off) > 0, f"实际 {len(one_off)} 项")
check("一次性支出金额均为正", all(r["amount"] > 0 for r in one_off))
check(
    "一次性支出合计 == 逐项相加",
    abs(one_off_total - round(sum(r["amount"] for r in one_off), 2)) < 0.01,
)

# 关键：把一次性支出摊进月开销会虚增目标，这里明确钉死「不摊」
if one_off_total > 0:
    amortized = monthly + one_off_total / 12
    check(
        "月开销中不含一次性支出的摊销",
        abs(monthly - amortized) > 0.01,
        "月开销疑似把一次性支出摊了进去",
    )
    check(
        "含一次性支出的资金需求 = 目标 + 一次性支出",
        abs(plan["target_with_one_off"] - (plan["target_cny"] + one_off_total)) < 0.01,
    )
    check(
        "含一次性支出的需求严格大于纯目标",
        plan["target_with_one_off"] > plan["target_cny"],
    )

# ---------------------------------------------------------------- 4. 方案切换
print()
print("切换方案")
if len(profile_names) >= 2:
    totals = {}
    for name in profile_names:
        alt = variant(**{"life_plan.profile": name})
        totals[name] = lifeplan_mod.monthly_total(alt)
        print(f"       {name} -> ¥{totals[name]:,.2f}/月")
    check(
        "不同方案的月开销确实不同",
        len(set(totals.values())) > 1,
        f"各方案月开销：{totals}",
    )
    for name in profile_names:
        alt = variant(**{"life_plan.profile": name})
        _, alt_plan = lifeplan_mod.resolve_monthly(alt)
        check(
            f"{name} 的目标与自身月开销自洽",
            abs(alt_plan["target_cny"] - totals[name] * 12 / RATE) < 0.01,
        )
else:
    print("  skip 只定义了一个方案，跳过切换测试")

# ---------------------------------------------------------------- 5. 错误处理
print()
print("配置写错时必须报错，不能静默回落")
try:
    lifeplan_mod.monthly_total(variant(**{"life_plan.profile": "no-such-profile"}))
    check("profile 名不存在 -> 抛错", False, "没有抛错，说明会静默回落")
except lifeplan_mod.LifePlanError:
    check("profile 名不存在 -> 抛错", True)

try:
    bad = copy.deepcopy(dict(cfg))
    bad["life_plan"]["enabled"] = False
    bad["fire"]["monthly_expense"] = None
    lifeplan_mod.resolve_monthly(cfgmod.Config(bad))
    check("life_plan 关闭且月开销为 null -> 抛错", False, "没有抛错")
except lifeplan_mod.LifePlanError:
    check("life_plan 关闭且月开销为 null -> 抛错", True)

# ---------------------------------------------------------------- 6. 手工覆盖
print()
print("手工覆盖（试算用）")
override = variant(**{"fire.monthly_expense": 3000.0})
got, ov_plan = lifeplan_mod.resolve_monthly(override)
check("覆盖后月开销取覆盖值", abs(got - 3000.0) < 0.01, f"实际 {got}")
check("覆盖被标记 override=True", ov_plan.get("override") is True)
check(
    "覆盖时仍保留逐项推导值",
    abs(ov_plan.get("derived_monthly_expense", 0) - monthly) < 0.01,
)
check(
    "覆盖后目标按覆盖值重算",
    abs(ov_plan["target_cny"] - 3000.0 * 12 / RATE) < 0.01,
)

# 正式配置里应保持 null，确保口径来自逐项预算而不是某个写死的数字
check(
    "正式配置未开启手工覆盖",
    cfg.fire.get("monthly_expense") is None,
    f"当前为 {cfg.fire.get('monthly_expense')!r}",
)

print()
if failures:
    print(f"失败 {len(failures)} 项：")
    for name in failures:
        print(f"  - {name}")
    sys.exit(1)

print(f"全部通过（基准月开销 ¥{monthly:,.2f}，FIRE 目标 ¥{plan['target_cny']:,.2f}）")
sys.exit(0)
