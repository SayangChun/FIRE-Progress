"""FIRE 分子口径的回归测试。

钉住几条容易被改坏、且改坏了看板上完全看不出来的口径：

  1. **分子只由四项资产构成**：标普500基金 + 纳指100基金 + 稳定币 + 人民币活钱。
     如果哪天有人又加回一项资产，这条会立刻失败，提醒他重新确认口径，
     而不是让看板悄悄改变含义。
  2. **资产变化绝不影响 FIRE 目标**（分母）。目标是「组合需覆盖 × 12 ÷ 提取率」
     （组合需覆盖 = 月开销 − 兼职净收入，见 fire.labor_income），
     与持有多少资产无关。加一项资产让目标跟着变，是口径错误里最隐蔽的一种。
  3. 不传可选资产时按 0 处理，绝不影响既有调用点与历史快照。

运行：python tests/test_fire_core.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import config as cfgmod  # noqa: E402
from scripts import fire as firemod  # noqa: E402
from scripts import lifeplan as lifeplan_mod  # noqa: E402

cfg = cfgmod.load()
MONTHLY, PLAN = lifeplan_mod.resolve_monthly(cfg)
NET_MONTHLY = PLAN["net_monthly_expense"]
TARGET = NET_MONTHLY * 12 / float(cfg.fire.withdrawal_rate)
RATE = float(cfg.fire.withdrawal_rate)

failures: list[str] = []


def ok(label: str, cond: bool, extra: str = "") -> None:
    if cond:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}" + (f" -- {extra}" if extra else ""))
        failures.append(label)


PRICE = {"usd_cny": 6.7}
SP500 = {
    "available": True,
    "market_value": 600.0,
    "invested": 600.0,
    "profit": 0.0,
    "funds": [],
    "warnings": [],
}

NDX = {
    "available": True,
    "market_value": 4425.42,
    "invested": 4177.22,
    "profit": 248.20,
    "return_rate": 0.059414,
    "latest_nav_date": "2026-10-23",
    "funds": [],
    "warnings": [],
}

print("分子 = 标普500基金 + 纳指100基金 + 稳定币 + 人民币活钱")
data = firemod.compute(cfg, price=PRICE, sp500=SP500, ndx100=NDX, history=[])
ok(
    "分子 == 标普500 + 纳指100（未传手动资产时）",
    abs(data["assets"]["total_cny"] - (600.0 + 4425.42)) < 0.01,
    f'{data["assets"]["total_cny"]} vs 5025.42',
)
ok(
    "assets 里**没有** emergency（应急金已移除）",
    "emergency" not in data["assets"],
    str(sorted(data["assets"].keys())),
)
ok("不传手动资产时只有两个有值的资产块",
   sorted(k for k in ("sp500", "ndx100", "stablecoin", "cash_cny", "emergency")
          if isinstance(data["assets"].get(k), dict))
   == ["ndx100", "sp500"])

# 不传纳指时必须与加入前完全一致——旧调用点、mock 数据、历史快照都靠这条
legacy = firemod.compute(cfg, price=PRICE, sp500=SP500, history=[])
ok(
    "不传 ndx100 时分子只剩标普500（向后兼容）",
    abs(legacy["assets"]["total_cny"] - 600.0) < 0.01,
    f'{legacy["assets"]["total_cny"]} vs 600.0',
)
ok(
    "但传了 ndx100 就必须算进分子",
    data["assets"]["total_cny"] - legacy["assets"]["total_cny"] > 4425.41,
    f'{data["assets"]["total_cny"]} vs {legacy["assets"]["total_cny"]}',
)

print()
print("FIRE 目标只由净月开销与提取率决定，与资产无关")
ok(
    "目标 == 组合需覆盖 × 12 ÷ 提取率",
    abs(data["fire"]["target_cny"] - TARGET) < 0.01,
    f'{data["fire"]["target_cny"]} vs {TARGET}',
)
ok(
    "fire.net_monthly_expense == 月开销 − 兼职净收入",
    abs(
        data["fire"]["net_monthly_expense"]
        - (MONTHLY - (data["fire"].get("labor_income") or {}).get("net_monthly_cny", 0.0))
    )
    < 0.01,
)
ok("兼职收入确实降低了目标", data["fire"]["target_cny"] < MONTHLY * 12 / RATE)
# 把资产翻 100 倍，目标必须一动不动
rich = firemod.compute(
    cfg,
    price=PRICE,
    sp500={**SP500, "market_value": 60_000.0, "invested": 60_000.0},
    history=[],
)
ok(
    "资产放大 100 倍 -> 目标不变",
    rich["fire"]["target_cny"] == data["fire"]["target_cny"],
    f'{rich["fire"]["target_cny"]} vs {data["fire"]["target_cny"]}',
)
ok("资产放大 100 倍 -> 完成度上升", rich["assets"]["progress_pct"] > data["assets"]["progress_pct"])
ok("完成度 = 当前资产 ÷ 目标", abs(data["assets"]["progress"] - data["assets"]["total_cny"] / TARGET) < 1e-12)
ok("距离目标 = max(目标 − 当前资产, 0)", abs(data["assets"]["remaining_cny"] - (TARGET - data["assets"]["total_cny"])) < 0.01)

print()
print("本金与盈亏：只统计当前仍持有的类别")
ok("总本金 = 标普500 + 纳指100",
   abs(data["cost_basis"]["total_cny"] - (600.0 + 4177.22)) < 0.01)
ok("盈亏 = 市值 − 本金",
   abs(data["cost_basis"]["profit_cny"] - (data["assets"]["total_cny"] - data["cost_basis"]["total_cny"])) < 0.01)

print()
print("定投额 + 资产增值外推")
FX = 6.680538
CONTRIB = cfg.get("contribution")
ER = cfg.get("expected_return")
ASSETS = {"sp500": 900.0, "ndx100": 4_500.0, "stablecoin": 13_811.08, "cash_cny": 5_959.74}
SP_DAY = float(CONTRIB["sp500_cny_per_day"])
NDX_DAY = float(CONTRIB["ndx100_cny_per_day"])
proj = firemod.projection(185_828.10, FX, CONTRIB, ASSETS, ER)
ok(
    "日定投合计 = 标普500 + 纳指100",
    abs(proj["daily_cny"] - (SP_DAY + NDX_DAY)) < 0.01,
    str(proj["daily_cny"]),
)
ok(
    "月定投额 = 日定投额 × 30（容差 0.5，日额已四舍五入到分）",
    abs(proj["monthly_cny"] - proj["daily_cny"] * 30) < 0.5,
    f'{proj["monthly_cny"]} vs {proj["daily_cny"] * 30:.2f}',
)
_w = {k: v / sum(ASSETS.values()) for k, v in ASSETS.items()}
_expect_rate = sum(_w[k] * float(ER[k]) for k in ASSETS)
ok(
    "加权预期年化按当前市值权重（与被动收入同口径）",
    abs(proj["weighted_rate"] - _expect_rate) < 1e-4,
    f'{proj["weighted_rate"]} vs {_expect_rate:.4f}',
)
ok(
    "三档收益率单调：悲观 ≤ 基准 ≤ 乐观",
    proj["scenarios"]["low"]["rate"]
    <= proj["scenarios"]["base"]["rate"]
    <= proj["scenarios"]["high"]["rate"],
    str({k: v["rate"] for k, v in proj["scenarios"].items()}),
)
only_dca = firemod.projection(185_828.10, FX, CONTRIB)
# projection() 内部用未四舍五入的日定投额求解，daily_cny 展示值则保留到分，
# 两者在整数天上可能差 1。用未取整的日额做基准，钉住「退化成纯定投」这个性质。
_daily_raw = SP_DAY + NDX_DAY
ok(
    "不给资产时退化为纯定投（天数 = 剩余 ÷ 日定投）",
    only_dca["days_to_target"] == int(185_828.10 / _daily_raw),
    f'{only_dca["days_to_target"]} vs {int(185_828.10 / _daily_raw)}',
)
ok(
    "计入资产增值后，天数比纯定投更短",
    proj["days_to_target"] < only_dca["days_to_target"],
    f'{proj["days_to_target"]} vs {only_dca["days_to_target"]}',
)
ok(
    "外推结果不再带历史增速字段",
    "window_days" not in proj and "daily_gain_cny" not in proj,
    str(sorted(proj)),
)
zero = firemod.projection(100_000.0, FX, {"sp500_cny_per_day": 0, "ndx100_cny_per_day": 0})
ok(
    "定投额为 0 时给出原因，不做除零",
    zero["days_to_target"] is None and bool(zero["reason"]),
    str(zero),
)
ok("已达标（剩余 ≤ 0）返回 None", firemod.projection(0, FX, CONTRIB) is None)
ok(
    "compute() 里的外推用的是配置中的定投额与预期回报",
    abs(data["projection"]["daily_cny"] - (SP_DAY + NDX_DAY)) < 0.01
    and data["projection"]["weighted_rate"] > 0,
    str(data["projection"].get("weighted_rate")),
)
# 每月储蓄 ¥2,000 里，只有定投那部分进分子；差额转现金缓冲，
# 既不进资产构成也不进外推。写死这条边界，避免以后有人把两者合并。
monthly_saving = float((cfg.get("timeline") or {}).get("monthly_contribution") or 0)
ok(
    "储蓄能力不低于定投额（现金缓冲非负），外推分子仍只算定投额",
    monthly_saving >= data["projection"]["monthly_cny"],
    f'储蓄 ¥{monthly_saving:,.0f} vs 定投 ¥{data["projection"]["monthly_cny"]:,.2f}',
)

print()
print("手动资产：稳定币与活钱计入分子")
PRICE_MANUAL = {"usd_cny": 6.685071}
base = firemod.compute(cfg, price=PRICE_MANUAL, sp500=SP500,
                       ndx100=NDX, history=[])
ok(
    "不传手动资产时分子只剩标普500 + 纳指100（向后兼容）",
    abs(base["assets"]["total_cny"] - (600.0 + 4425.42)) < 0.01,
    str(base["assets"]["total_cny"]),
)

sc, cash = firemod.manual_assets(cfg, PRICE_MANUAL)
ok("稳定币明细由配置生成", isinstance(sc, dict) and bool(sc.get("holdings")), str(sc))
ok("活钱明细由配置生成", isinstance(cash, dict) and cash.get("value_cny") == 5959.74, str(cash))
if sc:
    ok("稳定币按实时汇率折人民币",
       abs(sc["value_cny"] - sc["total_units"] * 6.685071) < 0.01,
       f'{sc["value_cny"]} vs {sc["total_units"] * 6.685071:.2f}')
    ok("稳定币明确标记为计入分子", sc.get("included_in_assets") is True)

with_manual = firemod.compute(cfg, price=PRICE_MANUAL, sp500=SP500,
                              ndx100=NDX, stablecoin=sc, cash_cny=cash, history=[])
expect_total = 600.0 + 4425.42 + sc["value_cny"] + cash["value_cny"]
ok("两项手动资产都计入分子",
   abs(with_manual["assets"]["total_cny"] - expect_total) < 0.01,
   f'{with_manual["assets"]["total_cny"]} vs {expect_total:.2f}')
ok("加入资产不改变 FIRE 目标（钉死的不变量）",
   abs(with_manual["fire"]["target_cny"] - TARGET) < 0.01,
   f'{with_manual["fire"]["target_cny"]} vs {TARGET}')
ok("完成度随分子上升",
   with_manual["assets"]["progress_pct"] > base["assets"]["progress_pct"])
pi = with_manual["passive_income"]
ok("被动收入把四项资产都纳入加权，权重和为 1",
   len(pi["assets"]) == 4 and abs(sum(r["weight"] for r in pi["assets"]) - 1.0) < 1e-9,
   str([(r["key"], round(r["weight"], 4)) for r in pi["assets"]]))
ok("被动收入市值之和 == 总资产",
   abs(sum(r["value_cny"] for r in pi["assets"]) - with_manual["assets"]["total_cny"]) < 0.02,
   str(pi["weighted_rate"]))
ok("稳定币年化 10%、下沿 0% 进入加权区间",
   any(r["key"] == "stablecoin" and r["rate"] == 0.10 and r["rate_low"] == 0.0
       for r in pi["assets"]),
   str(pi["rate_low"]))
ok("活钱年化 1% 进入加权",
   any(r["key"] == "cash_cny" and r["rate"] == 0.01 for r in pi["assets"]))
ok("外推权重覆盖四项资产",
   set(with_manual["projection"]["weights"]) == {"sp500", "ndx100", "stablecoin", "cash_cny"},
   str(with_manual["projection"]["weights"]))
ok("累计本金是当前持有类别之和",
   abs(with_manual["cost_basis"]["total_cny"]
       - (600.0 + 4177.22 + sc["value_cny"] + cash["value_cny"])) < 0.01,
   str(with_manual["cost_basis"]["total_cny"]))

print()
if failures:
    print(f"失败 {len(failures)} 项：")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print(f"全部通过（提取率 {RATE * 100:.1f}%，FIRE 目标 ¥{TARGET:,.2f}）")
