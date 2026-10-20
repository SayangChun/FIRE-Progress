"""FIRE 分子口径的回归测试。

钉住几条容易被改坏、且改坏了看板上完全看不出来的口径：

  1. **分子只由两项资产构成**：比特币市值 + 标普500基金市值。
     2026-10-15 移除了应急金（支付宝小荷包）——如果哪天有人又加回一项资产，
     这条会立刻失败，提醒他重新确认口径，而不是让看板悄悄改变含义。
  2. **资产变化绝不影响 FIRE 目标**（分母）。目标是「组合需覆盖 × 12 ÷ 提取率」
     （组合需覆盖 = 月开销 − 兼职净收入，见 fire.labor_income），
     与持有多少资产无关。加一项资产让目标跟着变，是口径错误里最隐蔽的一种。
  3. 缺数据（拿不到比特币或基金）时绝不按 0 冒充——那会让进度凭空倒退。

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


PRICE = {"btc_cny": 550_000.0, "usd_cny": 6.7, "btc_usdt": 82_000.0}
BTC = {"available": True, "total_btc": 0.02, "cost_basis_usd": 1300.0, "positions": [], "warnings": []}
SP500 = {
    "available": True,
    "market_value": 600.0,
    "invested": 600.0,
    "profit": 0.0,
    "funds": [],
    "warnings": [],
}

print("分子 = 比特币市值 + 标普500基金市值，只有这两项")
data = firemod.compute(cfg, price=PRICE, btc=BTC, sp500=SP500, history=[])
btc_value = 0.02 * PRICE["btc_cny"]
ok(
    "分子 == 比特币 + 标普500",
    abs(data["assets"]["total_cny"] - (btc_value + 600.0)) < 0.01,
    f'{data["assets"]["total_cny"]} vs {btc_value + 600.0}',
)
ok(
    "assets 里**没有** emergency（应急金已移除）",
    "emergency" not in data["assets"],
    str(sorted(data["assets"].keys())),
)
ok("assets 只有 btc / sp500 两个资产块",
   sorted(k for k in data["assets"] if k in ("btc", "sp500", "emergency")) == ["btc", "sp500"])

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
    price={"btc_cny": 550_000.0 * 100, "usd_cny": 6.7, "btc_usdt": 82_000.0},
    btc=BTC,
    sp500=SP500,
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
print("本金与盈亏：比特币成本按备注均价 × 当前汇率折算")
ok("比特币本金 = cost_basis_usd × usd_cny", abs(data["cost_basis"]["btc_cny"] - 1300.0 * 6.7) < 0.01)
ok("总本金 = 比特币 + 标普500", abs(data["cost_basis"]["total_cny"] - (1300.0 * 6.7 + 600.0)) < 0.01)
ok("盈亏 = 市值 − 本金",
   abs(data["cost_basis"]["profit_cny"] - (data["assets"]["total_cny"] - data["cost_basis"]["total_cny"])) < 0.01)
ok("比特币成本标为估算值", data["cost_basis"]["btc_estimated"] is True)

print()
print("拿不到数据时绝不按 0 冒充")
no_btc = firemod.compute(
    cfg,
    price=PRICE,
    btc={"available": False, "total_btc": None, "warnings": ["比特币：读不到"]},
    sp500=SP500,
    history=[],
)
ok(
    "比特币不可用时，分子里没有它的贡献（= 只有标普500）",
    abs(no_btc["assets"]["total_cny"] - 600.0) < 0.01,
    str(no_btc["assets"]["total_cny"]),
)
ok("但告警被保留下来", any("比特币" in w for w in no_btc["warnings"]), str(no_btc["warnings"]))
ok("sources 里标为不可用", no_btc["sources"]["btc"] is False)

print()
if failures:
    print(f"失败 {len(failures)} 项：")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print(f"全部通过（提取率 {RATE * 100:.1f}%，FIRE 目标 ¥{TARGET:,.2f}）")
