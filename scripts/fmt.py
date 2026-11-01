"""金额格式化。

三个渲染器共用：README 区块、SVG 图表、静态页。
单独放一个模块，是为了避免它们各自实现一份、然后某天口径悄悄分叉。
"""

from __future__ import annotations


def money(value, cfg, *, decimals: int = 2, symbol: str | None = None) -> str:
    if value is None:
        return "—"
    if cfg.privacy.get("mode") == "masked":
        return "已隐藏"
    symbol = symbol if symbol is not None else cfg.fire.get("currency_symbol", "¥")
    return f"{symbol}{value:,.{decimals}f}"
