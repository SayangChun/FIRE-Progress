"""「兼职净收入」的回归测试（咖啡师 FIRE）。

这段逻辑改变的是 FIRE 目标的分子来源，改坏了看板上完全看不出来——
目标会悄悄变低，而进度条只是"看起来变快了"。

钉住这几条：
  1. 月工时按 52 周 ÷ 12 折算，不按「每月 4 周」（否则少算约 8%）
  2. 只扣**因为工作才产生**的增量消耗，不扣本来就要花的钱
     （扣多了会让目标虚高，等于把生活费算了两遍）
  3. 净收入 ≥ 月开销时**直接报错**，不静默算出目标 0
  4. 关闭兼职后必须精确退回传统 FIRE 口径
  5. 缺字段 / 非正数时立刻报错，不拿默认值凑

运行：python tests/test_labor_income.py
"""

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import config as cfgmod  # noqa: E402
from scripts import lifeplan as lifeplan_mod  # noqa: E402

cfg = cfgmod.load()

failures: list[str] = []


def ok(label: str, cond: bool, extra: str = "") -> None:
    if cond:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}" + (f" -- {extra}" if extra else ""))
        failures.append(label)


def variant(**overrides):
    """基于当前配置造一个变体，用来测边界。"""
    data = copy.deepcopy(dict(cfg))
    for dotted, value in overrides.items():
        node = data
        parts = dotted.split(".")
        for key in parts[:-1]:
            node = node[key]
        node[parts[-1]] = value
    return cfgmod.Config(data)


SPEC = (cfg.get("fire") or {}).get("labor_income") or {}
li = lifeplan_mod.labor_income(cfg)

print("兼职收入的基本口径")
ok("labor_income 已启用并返回结果", li is not None)
if li is None:
    print("  兼职未启用，后续测试跳过")
    sys.exit(1)

wage = float(SPEC["hourly_wage"])
hours_week = float(SPEC["hours_per_week"])
days_week = float(SPEC["work_days_per_week"])
transport_day = float(SPEC["transport_per_day"])
meal = float(SPEC.get("meal_increment_monthly") or 0.0)
gear = float(SPEC.get("gear_monthly") or 0.0)
commute = float(SPEC.get("commute_hours_per_day") or 0.0)

print(f"       时薪 ¥{wage}，每周 {hours_week}h / {days_week} 天")
print(f"       毛 {li['gross_monthly_cny']:,.2f}  消耗 {li['cost_monthly_cny']:,.2f}"
      f"  净 {li['net_monthly_cny']:,.2f}")

print()
print("工时折算：52 周 ÷ 12，不是每月 4 周")
hours_month = hours_week * 52 / 12
ok(
    "月工时 = 周工时 × 52 ÷ 12",
    abs(li["hours_per_month"] - hours_month) < 0.01,
    f'{li["hours_per_month"]} vs {hours_month:.4f}',
)
# 按「每月 4 周」会算成 32 小时，比正确值少 8%
ok(
    "月工时明显高于「周工时 × 4」（没按 4 周少算）",
    li["hours_per_month"] > hours_week * 4 * 1.05,
    f'{li["hours_per_month"]} vs {hours_week * 4}',
)
ok(
    "月工作日 = 周工作日 × 52 ÷ 12",
    abs(li["work_days_per_month"] - days_week * 52 / 12) < 0.01,
)

print()
print("毛收入与消耗")
ok(
    "毛收入 = 月工时 × 时薪",
    abs(li["gross_monthly_cny"] - hours_month * wage) < 0.01,
    f'{li["gross_monthly_cny"]} vs {hours_month * wage:.2f}',
)
expected_transport = days_week * 52 / 12 * transport_day
ok(
    "交通 = 月工作日 × 每日往返",
    abs(li["transport_cny"] - expected_transport) < 0.01,
    f'{li["transport_cny"]} vs {expected_transport:.2f}',
)
ok(
    "消耗合计 = 交通 + 餐食增量 + 装备摊销",
    abs(li["cost_monthly_cny"] - (li["transport_cny"] + meal + gear)) < 0.01,
)
ok(
    "净收入 = 毛收入 − 消耗",
    abs(li["net_monthly_cny"] - (li["gross_monthly_cny"] - li["cost_monthly_cny"])) < 0.01,
)
ok(
    "消耗远小于毛收入（只扣增量，没把生活费算进来）",
    li["cost_monthly_cny"] < li["gross_monthly_cny"] * 0.15,
    f'消耗占毛收入 {li["cost_monthly_cny"] / li["gross_monthly_cny"] * 100:.1f}%',
)

print()
print("等效时薪：通勤摊薄")
ok(
    "等效时薪 < 净时薪（通勤占掉了一部分时间）",
    li["effective_hourly_cny"] < li["net_hourly_cny"],
    f'{li["effective_hourly_cny"]} vs {li["net_hourly_cny"]}',
)
occupied = li["work_days_per_month"] * (li["hours_per_day"] + commute)
ok(
    "占用时间 = 月工作日 × (每日工时 + 通勤)",
    abs(li["occupied_hours_per_month"] - occupied) < 0.05,
    f'{li["occupied_hours_per_month"]} vs {occupied:.2f}',
)
ok(
    "等效时薪 = 净收入 ÷ 占用时间",
    abs(li["effective_hourly_cny"] - li["net_monthly_cny"] / occupied) < 0.01,
)

print()
print("净收入必须真的被扣进目标")
net = li["net_monthly_cny"]
monthly = lifeplan_mod.monthly_total(cfg)
rate = float(cfg.fire.withdrawal_rate)
_, plan = lifeplan_mod.resolve_monthly(cfg)
ok(
    "组合需覆盖 = 月开销 − 净收入",
    abs(plan["net_monthly_expense"] - (monthly - net)) < 0.01,
    f'{plan["net_monthly_expense"]} vs {monthly - net:.2f}',
)
ok(
    "目标 = 组合需覆盖 × 12 ÷ 提取率",
    abs(plan["target_cny"] - (monthly - net) * 12 / rate) < 0.01,
)
ok(
    "目标严格低于传统口径",
    plan["target_cny"] < monthly * 12 / rate,
    f'{plan["target_cny"]:,.2f} vs {monthly * 12 / rate:,.2f}',
)

print()
print("边界：净收入 ≥ 月开销时必须报错")
try:
    # 把时薪抬到足够高，让净收入超过月开销
    rich = variant(**{"fire.labor_income.hourly_wage": 200.0})
    lifeplan_mod.resolve_monthly(rich)
    ok("净收入 ≥ 月开销 -> 抛错", False, "没有抛错，会静默算出目标 0")
except lifeplan_mod.LifePlanError:
    ok("净收入 ≥ 月开销 -> 抛错", True)

print()
print("边界：配置写错必须立刻报错")
for field, value, label in (
    ("fire.labor_income.hourly_wage", 0.0, "时薪为 0"),
    ("fire.labor_income.hours_per_week", 0.0, "周工时为 0"),
    ("fire.labor_income.work_days_per_week", 0.0, "周工作日为 0"),
):
    try:
        lifeplan_mod.labor_income(variant(**{field: value}))
        ok(f"{label} -> 抛错", False, "没有抛错")
    except lifeplan_mod.LifePlanError:
        ok(f"{label} -> 抛错", True)

try:
    bad = copy.deepcopy(dict(cfg))
    del bad["fire"]["labor_income"]["hourly_wage"]
    lifeplan_mod.labor_income(cfgmod.Config(bad))
    ok("缺 hourly_wage -> 抛错", False, "没有抛错，会静默算成 0")
except lifeplan_mod.LifePlanError:
    ok("缺 hourly_wage -> 抛错", True)

print()
print("边界：关闭兼职 = 精确退回传统 FIRE")
off = variant(**{"fire.labor_income.enabled": False})
ok("关闭时 labor_income() 返回 None", lifeplan_mod.labor_income(off) is None)
_, off_plan = lifeplan_mod.resolve_monthly(off)
ok(
    "关闭后目标 == 月开销 × 12 ÷ 提取率",
    abs(off_plan["target_cny"] - monthly * 12 / rate) < 0.01,
)
ok(
    "关闭后组合需覆盖 == 月开销",
    abs(off_plan["net_monthly_expense"] - monthly) < 0.01,
)

print()
print("线性：工时翻倍，净收入不等于翻倍（消耗不随工时变）")
twice = variant(**{"fire.labor_income.hours_per_week": hours_week * 2})
li2 = lifeplan_mod.labor_income(twice)
ok(
    "工时翻倍 -> 毛收入翻倍",
    abs(li2["gross_monthly_cny"] - li["gross_monthly_cny"] * 2) < 0.05,
)
ok(
    "工时翻倍但天数不变 -> 消耗不变（交通按天数算，不按工时算）",
    abs(li2["cost_monthly_cny"] - li["cost_monthly_cny"]) < 0.05,
    f'{li2["cost_monthly_cny"]} vs {li["cost_monthly_cny"]}',
)
ok(
    "工时翻倍 -> 净收入增幅超过毛收入增幅（固定消耗被摊薄）",
    (li2["net_monthly_cny"] / li["net_monthly_cny"]) > 2.0,
    f'净收入倍数 {li2["net_monthly_cny"] / li["net_monthly_cny"]:.3f}',
)

print()
if failures:
    print(f"失败 {len(failures)} 项：")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print(f"全部通过（净收入 ¥{net:,.2f}/月，目标 ¥{plan['target_cny']:,.2f}）")
sys.exit(0)
