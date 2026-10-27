"""两段式口径的回归测试。

2026-10-27 新增。这一段回答的是「这笔钱能撑多久」，而 FIRE 目标回答的是
「还要攒多少」——两者共用同一个 config，但**绝不能互相污染**。

钉住这几条：

  1. **两段式绝不改变 FIRE 目标。** 这是最容易犯的错：一旦把「阶段 A 需要的本金」
     当成目标，进度条会凭空跳动，而看板上完全看不出来。
  2. `capital_for_years` 与 `years_from_capital` 互为反函数（在能算出的区间内）。
  3. 本金 ≥ 年支出 ÷ 收益率时判为**永续**（返回 None），不能给出一个假的年数。
  4. 资产占比只做展示，改占比不改变目标与分子。
  5. 关掉 `asset_allocation.enabled` 时返回 None，不猜默认值。

运行：python tests/test_two_phase.py
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
RATE = float(cfg.fire.withdrawal_rate)
TARGET = NET_MONTHLY * 12 / RATE

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

print("1. 两段式不改变 FIRE 目标")
data = firemod.compute(cfg, price=PRICE, btc=BTC, sp500=SP500, history=[])
ok("目标仍等于（月开销 − 兼职净收入）× 12 ÷ 提取率", abs(data["fire"]["target_cny"] - TARGET) < 0.01)
ok("two_phase 已生成", data.get("two_phase") is not None)

# 换一个完全不同的资产规模，目标必须一动不动
big = firemod.compute(
    cfg, price=PRICE, btc={**BTC, "total_btc": 2.0}, sp500=SP500, history=[]
)
ok(
    "资产扩大 100 倍，目标不变",
    abs(big["fire"]["target_cny"] - data["fire"]["target_cny"]) < 0.01,
    f'{big["fire"]["target_cny"]} vs {data["fire"]["target_cny"]}',
)
ok(
    "但两段式结果跟着资产变（这才是它该做的）",
    big["two_phase"]["years"] != data["two_phase"]["years"],
)

print("\n2. 年金现值与年数互为反函数")
for years in (5, 10, 15, 20, 30):
    need = firemod.capital_for_years(8856.0, years, RATE)
    back = firemod.years_from_capital(need, 8856.0, RATE)
    ok(
        f"{years} 年 -> 本金 {need:,.0f} -> 反算 {back:.2f} 年",
        back is not None and abs(back - years) < 0.01,
        f"{back}",
    )

print("\n3. 永续判定")
k = 8856.0 / RATE  # 永续所需本金
ok(f"本金 = 永续线 {k:,.0f} 时判为永续", firemod.years_from_capital(k, 8856.0, RATE) is None)
ok("本金略低于永续线时给出有限年数", firemod.years_from_capital(k * 0.99, 8856.0, RATE) is not None)
ok("本金为 0 时返回 0 年（不返回 None）", firemod.years_from_capital(0.0, 8856.0, RATE) == 0.0)
ok("年支出为 0 时判为永续", firemod.years_from_capital(100_000.0, 0.0, RATE) is None)

print("\n4. 临界收益率")
cr = firemod.critical_rate(8856.0, 100_000.0)
ok("临界收益率 = 年支出 ÷ 本金", cr is not None and abs(cr - 0.08856) < 1e-6, f"{cr}")
ok("本金越大临界值越低", firemod.critical_rate(8856.0, 200_000.0) < cr)

print("\n5. 资产占比只做展示")
alloc = data["allocation"]
ok("占比之和为 1", abs(alloc["btc_pct"] + alloc["sp500_pct"] - 1.0) < 1e-6)
ok(
    "标普500 占比 = 市值 ÷ 总市值",
    abs(alloc["sp500_pct"] - 600.0 / (0.02 * 550_000.0 + 600.0)) < 1e-4,
    f'{alloc["sp500_pct"]}',
)
ok("当前远超目标区间，标记为不在区间", alloc["in_range"] is False)

# 关掉开关 -> None，不猜
import copy  # noqa: E402

off = cfgmod.Config(copy.deepcopy(dict(cfg)))
off["asset_allocation"]["enabled"] = False
off_data = firemod.compute(off, price=PRICE, btc=BTC, sp500=SP500, history=[])
ok("关闭 asset_allocation -> None", off_data["allocation"] is None)
ok("关闭它不影响目标", abs(off_data["fire"]["target_cny"] - TARGET) < 0.01)

print()
if failures:
    print(f"失败 {len(failures)} 项：{failures}")
    sys.exit(1)
print(f"全部通过（年净支出 ¥{NET_MONTHLY * 12:,.2f}，FIRE 目标 ¥{TARGET:,.2f}）")
