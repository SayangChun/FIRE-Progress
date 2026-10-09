"""应急金（支付宝小荷包）的回归测试。

钉住几条容易改坏、且改坏了不容易察觉的口径：

  1. 应急金**计入分子**（当前资产），但**绝不影响 FIRE 目标**（分母）。
     加一项资产让目标跟着变，是口径错误里最隐蔽的一种——看板上完全看不出来。
  2. 还没开始存时**不能告警**（否则一建仓就先吵起来）。
  3. 超过核对周期必须告警（这是本项目唯一需要人工更新的数字）。
  4. 文件读不到 / 格式错 / 余额为负时返回 available=False，
     **绝不静默按 0 处理**——「没读到」和「余额是 0」是两件事。

运行：python tests/test_emergency.py
"""

import json
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import config as cfgmod  # noqa: E402
from scripts import fire as firemod  # noqa: E402
from scripts.sources import emergency as em_src  # noqa: E402
from scripts.update import apply_last_good  # noqa: E402

cfg = cfgmod.load()
failures: list[str] = []


def ok(label: str, cond: bool, extra: str = "") -> None:
    if cond:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}" + (f" -- {extra}" if extra else ""))
        failures.append(label)


TODAY = date.today()
TMP = Path(tempfile.mkdtemp(prefix="fire-emergency-"))


def make_cfg(name: str, payload, **over):
    path = TMP / f"{name}.json"
    if payload is not None:
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    base = dict(cfg.sources.emergency)
    base.update({"path": str(path), "started_on": TODAY.isoformat()})
    base.update(over)
    return cfgmod.Config(base)


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


print("应急金计入分子，但绝不影响 FIRE 目标（分母）")
base = firemod.compute(cfg, price=PRICE, btc=BTC, sp500=SP500, history=[])
with_em = firemod.compute(
    cfg, price=PRICE, btc=BTC, sp500=SP500, emergency={"balance_cny": 200.0}, history=[]
)
ok(
    "分子 = 比特币 + 标普500 + 应急金",
    abs(with_em["assets"]["total_cny"] - (base["assets"]["total_cny"] + 200.0)) < 0.01,
    f'{with_em["assets"]["total_cny"]} vs {base["assets"]["total_cny"]}',
)
ok(
    "FIRE 目标不受影响",
    with_em["fire"]["target_cny"] == base["fire"]["target_cny"],
    f'{with_em["fire"]["target_cny"]} vs {base["fire"]["target_cny"]}',
)
ok("完成度随分子上升", with_em["assets"]["progress_pct"] > base["assets"]["progress_pct"])
ok(
    "assets 里能看到应急金余额",
    abs(with_em["assets"]["emergency"]["value_cny"] - 200.0) < 0.01,
)
ok("缺省（不传 emergency）时按 0 处理，不报错", base["assets"]["emergency"]["value_cny"] == 0.0)

print()
print("未开始存钱时不告警")
em = em_src.fetch(
    make_cfg("not_started", {"as_of": TODAY.isoformat(), "balance_cny": 0.0},
             started_on=(TODAY + timedelta(days=30)).isoformat())
)
ok("available", em["available"] is True)
ok("started=False", em["started"] is False)
ok("stale_days 为空", em["stale_days"] is None)
ok("没有告警", em["warnings"] == [], str(em["warnings"]))
ok("余额为 0", em["balance_cny"] == 0.0)

print()
print("已开始：超过核对周期要告警，没超过不告警")
fresh = em_src.fetch(
    make_cfg("fresh", {"as_of": TODAY.isoformat(), "balance_cny": 400.0},
             started_on=(TODAY - timedelta(days=100)).isoformat())
)
ok("新鲜时无告警", fresh["warnings"] == [], str(fresh["warnings"]))
ok("started=True", fresh["started"] is True)
ok("余额读对", fresh["balance_cny"] == 400.0)

old_day = (TODAY - timedelta(days=100)).isoformat()
stale = em_src.fetch(
    make_cfg("stale", {"as_of": old_day, "balance_cny": 400.0},
             started_on=(TODAY - timedelta(days=200)).isoformat())
)
ok("过期时有告警", len(stale["warnings"]) == 1, str(stale["warnings"]))
ok("告警里带天数与阈值", "100 天" in stale["warnings"][0] and "45" in stale["warnings"][0],
   stale["warnings"][0])

print()
print("读不到 / 格式错 / 余额为负 —— 一律 available=False，绝不静默按 0")
missing = em_src.fetch(make_cfg("missing", None))
ok("文件不存在 -> available=False", missing["available"] is False)
ok("文件不存在 -> 有告警", len(missing["warnings"]) == 1)

bad = em_src.fetch(make_cfg("bad", {"as_of": "2026-01-01"}))
ok("缺 balance_cny -> available=False", bad["available"] is False)

bad_date = em_src.fetch(make_cfg("bad_date", {"as_of": "不是日期", "balance_cny": 1.0}))
ok("as_of 不是日期 -> available=False", bad_date["available"] is False)

neg = em_src.fetch(make_cfg("neg", {"as_of": TODAY.isoformat(), "balance_cny": -5.0}))
ok("余额为负 -> available=False", neg["available"] is False)

bad_cfg = em_src.fetch(make_cfg("bad_cfg", {"as_of": TODAY.isoformat(), "balance_cny": 1.0},
                                started_on="不是日期"))
ok("config 里 started_on 写错 -> available=False", bad_cfg["available"] is False)

print()
print("读取失败时沿用上次成功值，绝不用 0 冒充")
prev = {"assets": {"emergency": {"value_cny": 400.0, "label": "支付宝小荷包", "short_label": "应急金"}}}
_, _, em2, notes = apply_last_good(
    BTC, SP500, {"available": False, "warnings": ["读不到"]}, prev
)
ok("沿用上次余额", em2["available"] is True and abs(em2["balance_cny"] - 400.0) < 0.01)
ok("标注了兜底", any("应急金" in n for n in notes), str(notes))

_, _, em3, notes3 = apply_last_good(BTC, SP500, {"available": False, "warnings": []}, {"assets": {}})
ok("没有缓存可退时不伪造 0", em3["available"] is False)

print()
if failures:
    print(f"失败 {len(failures)} 项：")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("全部通过")
