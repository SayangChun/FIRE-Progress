"""提交门控的回归测试。

这段逻辑容易被改坏且不易察觉：阈值如果退化成固定金额，
资产小的时候会变成每小时提交一次（约 720 次/月），
资产大了之后又会失去意义。这里把关键性质钉住。

运行：python tests/test_commit_gate.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import config as cfgmod  # noqa: E402
from scripts.update import is_material  # noqa: E402

cfg = cfgmod.load()
TARGET = float(cfg.fire.monthly_expense) * 12 / float(cfg.fire.withdrawal_rate)
RATIO = float(cfg.automation.get("min_commit_delta_ratio", 0.003))
FLOOR = float(cfg.automation.get("min_commit_delta_cny", 1.0))

failures: list[str] = []


def make(total: float, date: str = "2026-09-24") -> dict:
    return {
        "as_of_date": date,
        "assets": {"total_cny": total, "progress_pct": total / TARGET * 100},
    }


def check(label: str, previous: dict, data: dict, expect: bool) -> None:
    got, reason = is_material(previous, data, cfg)
    if got == expect:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label} -- 提交={got}，预期 {expect}｜{reason}")
        failures.append(label)


BASE = 13535.02
print("首次运行必须提交")
check("无历史 -> 提交", {}, make(BASE), True)

print("跨天必须提交（保证曲线每天至少一个数据点）")
check("跨天且零变动 -> 提交", make(BASE, "2026-09-23"), make(BASE), True)

print(f"同一天、变动不足阈值则跳过（当前阈值 ¥{max(FLOOR, BASE * RATIO):,.2f}）")
for delta in (1.0, 13.0, 26.0, 39.0):
    check(f"变动 ¥{delta:.2f} -> 跳过", make(BASE), make(BASE + delta), False)

print("同一天、变动达到阈值则提交")
for delta in (41.0, 65.0, 200.0):
    check(f"变动 ¥{delta:.2f} -> 提交", make(BASE), make(BASE + delta), True)

print("阈值必须随资产规模缩放，而不是固定金额")
for total, delta in (
    (1000.0, 1.0),  # 小资产：被绝对下限拦住
    (1000.0, 3.5),  # 小资产：越过下限
    (500000.0, 100.0),  # 大资产：¥100 已微不足道
    (500000.0, 1600.0),  # 大资产：越过 0.3%
):
    expect = delta >= max(FLOOR, total * RATIO)
    verdict = "提交" if expect else "跳过"
    check(f"资产 ¥{total:,.0f} / 变动 ¥{delta:,.2f} -> {verdict}", make(total), make(total + delta), expect)

print("反向变动同样按绝对值判断")
check("资产下跌超过阈值 -> 提交", make(BASE), make(BASE - 100.0), True)
check("资产下跌不足阈值 -> 跳过", make(BASE), make(BASE - 5.0), False)

print()
if failures:
    print(f"失败 {len(failures)} 项：")
    for name in failures:
        print(f"  - {name}")
    sys.exit(1)

print("全部通过")
sys.exit(0)
