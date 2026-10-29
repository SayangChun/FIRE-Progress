"""静态页（GitHub Pages）的冒烟测试。

页面是给别人看的，错了不会有人报错——所以钉住这几条：

  1. 资产是**遍历出来的**，不是硬编码两项。2026-10-27 加了纳指100，
     如果页面只画比特币和标普500，数字加起来会不等于合计，看着像 bug。
  2. `privacy.mode: masked` 时页面上不能出现任何金额。
  3. 不能漏出 Python 的 None / nan ——那说明某个字段缺了，取数没兜底。
  4. 进度条宽度必须和 progress_pct 一致，否则页面自相矛盾。

运行：python tests/test_site.py
"""

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import site  # noqa: E402


def fake_data() -> dict:
    return {
        "as_of": "2026-10-28T11:44:11+08:00",
        "fire": {
            "monthly_expense": 1461.0,
            "net_monthly_expense": 738.0,
            "target_cny": 205953.49,
            "withdrawal_rate": 0.043,
            "labor_income": {"net_monthly_cny": 723.0},
        },
        "assets": {
            "total_cny": 20125.39,
            "progress_pct": 9.7718,
            "remaining_cny": 185828.10,
            "btc": {"value_cny": 14780.99, "snapshot_date": "2026-10-25", "stale_days": 3},
            "sp500": {"value_cny": 873.12, "latest_nav_date": "2026-10-26"},
            "ndx100": {"value_cny": 4471.28},
        },
        "cost_basis": {"total_cny": 17720.05, "profit_cny": 2405.34},
        "passive_income": {
            "hourly_cny": 0.239,
            "monthly_cny": 174.53,
            "annual_cny": 2094.39,
            "weighted_rate": 0.1041,
            "coverage": 0.1195,
            "withdrawal_rate": 0.043,
            "monthly_at_withdrawal_cny": 72.12,
        },
        "projection": {
            "days_to_target": 905,
            "eta": "2029-04-20",
            "btc_cny_per_day": 66.14,
            "sp500_cny_per_day": 20.0,
            "daily_cny": 86.14,
            "monthly_cny": 2584.2,
        },
        "life_plan": {
            "headline": "牡丹江 · 单人 · 租房 · 极简",
            "monthly_expense": 1461.0,
            "one_off_total": 15000.0,
            "groups": [
                {"group": "住房", "subtotal": 712.0,
                 "items": [{"label": "房租", "monthly": 500.0},
                           {"label": "取暖费", "monthly": 75.0}]},
            ],
        },
        "price": {"btc_source": "binance", "fx_source": "open.er-api.com"},
    }


class FakeCfg(dict):
    def __getattr__(self, item):
        value = self[item]
        return FakeCfg(value) if isinstance(value, dict) else value


def make_cfg(masked: bool = False) -> FakeCfg:
    return FakeCfg({
        "fire": {"currency_symbol": "¥"},
        "privacy": {"mode": "masked" if masked else "full"},
        "sources": {"btc": {"repo": "SayangChun/0.1BTC"},
                    "sp500": {"repo": "SayangChun/sp500-dca"}},
    })


def render(masked: bool = False) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        return site.build_page(fake_data(), make_cfg(masked), [], Path(tmp))


html = render()

# 1. 三种资产都在，且合计与分项对得上
for label in ("比特币", "标普500基金", "纳指100基金"):
    assert label in html, f"页面缺资产：{label}"
assert "¥20,125.39" in html, "合计没出现"
assert html.count("¥14,780.99") >= 1 and html.count("¥4,471.28") >= 1

# 2. 完成度与进度条一致
assert "9.77%" in html
assert 'style="width:9.77%"' in html, "进度条宽度与完成度不一致"

# 3. 关键数字齐全
for token in ("¥205,953.49", "¥185,828.10", "¥723.00", "¥738.00", "¥15,000.00"):
    assert token in html, f"页面缺数字：{token}"

# 4. 没有漏出 Python 的占位值
for bad in (">None<", ">nan<", "None 天"):
    assert bad not in html, f"页面漏出了 {bad}"

# 5. masked 模式下不出现金额
masked_html = render(masked=True)
assert "¥20,125.39" not in masked_html, "masked 模式仍在显示金额"
assert "已隐藏" in masked_html

print("静态页冒烟测试通过（资产遍历 / 进度条一致 / 隐私遮蔽 / 无 None）")
