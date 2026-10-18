"""「每小时被动收入」的回归测试。

这个数字很容易被算错，而算错了在看板上完全看不出来（就是个 ¥0.xx）。
钉住这几条：

  1. 加权年化是**按市值加权**，不是两项算术平均。95% 仓位在比特币上时，
     两个算法差 5 个百分点，但显示上都像「11% 左右」。
  2. 每小时 = 总市值 × 加权年化 ÷ 8760，四条时间尺度互相自洽
     （每小时 × 24 = 每天，× 365 = 每年，÷ 12 = 每月）。
  3. 它**绝不能**影响 FIRE 目标。目标只由月开销与提取率决定。
  4. 预期回报口径的被动收入必须**高于**提取率口径的——否则说明有人
     把两个概念搞混了（预期回报是「平均能涨多少」，提取率是「能安全花多少」）。
  5. 配置缺项时返回 None，不拿默认值凑——猜一个回报率比不显示更糟。

运行：python tests/test_passive_income.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import config as cfgmod  # noqa: E402
from scripts import fire as firemod  # noqa: E402
from scripts import lifeplan as lifeplan_mod  # noqa: E402

cfg = cfgmod.load()
MONTHLY, _ = lifeplan_mod.resolve_monthly(cfg)
SPEC = cfg.get("expected_return") or {}

failures: list[str] = []


def ok(label: str, cond: bool, extra: str = "") -> None:
    if cond:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}" + (f" -- {extra}" if extra else ""))
        failures.append(label)


def close(a, b, tol=1e-6) -> bool:
    return a is not None and b is not None and abs(float(a) - float(b)) <= tol


PRICE = {"btc_cny": 550_000.0, "usd_cny": 6.7, "btc_usdt": 82_000.0}
BTC = {"available": True, "total_btc": 0.025, "cost_basis_usd": 1300.0, "positions": [], "warnings": []}
SP500 = {"available": True, "market_value": 700.0, "invested": 700.0, "profit": 0.0, "funds": [], "warnings": []}

BTC_VALUE = 0.025 * PRICE["btc_cny"]  # 13,750
TOTAL = BTC_VALUE + 700.0

print("加权年化按市值加权，不是两项算术平均")
data = firemod.compute(cfg, price=PRICE, btc=BTC, sp500=SP500, history=[])
pi = data["passive_income"]
ok("passive_income 已生成", pi is not None)

w_btc = BTC_VALUE / TOTAL
w_sp = 700.0 / TOTAL
expect_rate = w_btc * float(SPEC["btc"]) + w_sp * float(SPEC["sp500"])
ok(
    "加权年化 == 比特币×权重 + 标普500×权重",
    close(pi["weighted_rate"], expect_rate),
    f'{pi["weighted_rate"]} vs {expect_rate}',
)
naive = (float(SPEC["btc"]) + float(SPEC["sp500"])) / 2
ok(
    "加权值不等于两项算术平均（权重必须真的起作用）",
    not close(pi["weighted_rate"], naive, 1e-9),
    f'加权 {pi["weighted_rate"]:.4f} vs 平均 {naive:.4f}',
)
ok("权重之和 == 1", close(sum(r["weight"] for r in pi["assets"]), 1.0, 1e-12))
ok("市值之和 == 总资产", close(sum(r["value_cny"] for r in pi["assets"]), TOTAL, 0.01))

print()
print("四条时间尺度互相自洽")
ok("每小时 = 总市值 × 加权年化 ÷ 8760", close(pi["hourly_cny"], TOTAL * expect_rate / 8760, 1e-9))
ok("每年 = 每小时 × 8760", close(pi["annual_cny"], pi["hourly_cny"] * 8760, 0.01))
ok("每天 = 每小时 × 24", close(pi["daily_cny"], pi["hourly_cny"] * 24, 1e-9))
ok("每月 = 每年 ÷ 12", close(pi["monthly_cny"], pi["annual_cny"] / 12, 0.01))
ok("一年小时数写死为 8760", pi["hours_per_year"] == 8760, str(pi["hours_per_year"]))

print()
print("被动收入绝不影响 FIRE 目标")
target = MONTHLY * 12 / float(cfg.fire.withdrawal_rate)
ok("目标 == 月开销 × 12 ÷ 提取率", close(data["fire"]["target_cny"], target, 0.01))
# 把预期回报改到荒唐的 500%，目标必须一动不动
loud = cfgmod.Config(
    {**cfg, "expected_return": {"btc": 5.0, "sp500": 5.0, "btc_low": 0, "sp500_low": 0,
                                "btc_high": 9, "sp500_high": 9}}
)
loud_data = firemod.compute(loud, price=PRICE, btc=BTC, sp500=SP500, history=[])
ok(
    "预期回报改成 500% -> FIRE 目标不变",
    loud_data["fire"]["target_cny"] == data["fire"]["target_cny"],
    f'{loud_data["fire"]["target_cny"]} vs {data["fire"]["target_cny"]}',
)
ok("但被动收入变了", loud_data["passive_income"]["hourly_cny"] > pi["hourly_cny"])

print()
print("预期回报口径 必须高于 提取率口径（否则是把两个概念搞混了）")
ok(
    "每小时（预期回报）> 每小时（提取率）",
    pi["hourly_cny"] > pi["hourly_at_withdrawal_cny"],
    f'{pi["hourly_cny"]:.4f} vs {pi["hourly_at_withdrawal_cny"]:.4f}',
)
ok(
    "提取率口径 = 总市值 × 提取率 ÷ 8760",
    close(pi["hourly_at_withdrawal_cny"], TOTAL * float(cfg.fire.withdrawal_rate) / 8760, 1e-9),
)
ok(
    "覆盖月开销 = 每月被动收入 ÷ 月开销",
    close(pi["coverage"], pi["monthly_cny"] / MONTHLY, 1e-9),
)

print()
print("区间：悲观 <= 中枢 <= 乐观")
ok(
    "hourly_low <= hourly <= hourly_high",
    pi["hourly_low_cny"] <= pi["hourly_cny"] <= pi["hourly_high_cny"],
    f'{pi["hourly_low_cny"]:.4f} / {pi["hourly_cny"]:.4f} / {pi["hourly_high_cny"]:.4f}',
)

print()
print("配置缺项时不猜默认值")
no_spec = cfgmod.Config({k: v for k, v in cfg.items() if k != "expected_return"})
no_spec_data = firemod.compute(no_spec, price=PRICE, btc=BTC, sp500=SP500, history=[])
ok("缺 expected_return -> passive_income 为 None", no_spec_data["passive_income"] is None)
off = cfgmod.Config({**cfg, "display": {**cfg.display, "show_passive_income": False}})
off_data = firemod.compute(off, price=PRICE, btc=BTC, sp500=SP500, history=[])
ok("开关关闭 -> passive_income 为 None", off_data["passive_income"] is None)

print()
print("只有标普500时，加权年化 == 标普500 的假设")
sp_only = firemod.compute(
    cfg, price=PRICE, btc={"available": False, "total_btc": None, "warnings": []}, sp500=SP500, history=[]
)
ok(
    "纯标普500组合的加权年化 == sp500 假设",
    close(sp_only["passive_income"]["weighted_rate"], float(SPEC["sp500"]), 1e-9),
    str(sp_only["passive_income"]["weighted_rate"]),
)

print()
if failures:
    print(f"失败 {len(failures)} 项：")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print(
    f'全部通过（加权年化 {pi["weighted_rate"] * 100:.2f}%，'
    f'每小时 ¥{pi["hourly_cny"]:.4f}）'
)
