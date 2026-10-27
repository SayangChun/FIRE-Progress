"""纳指100 场外基金的净值抓取与估值。

**与标普500 不同：不读外部仓库，直接抓东方财富的公开接口。** 零密钥、零鉴权。

数据源：`https://fund.eastmoney.com/pingzhongdata/{code}.js`
每只基金返回一个 JS 文件，其中：

    var fS_name = "天弘纳斯达克100指数发起(QDII)A";
    var Data_netWorthTrend = [{"x":<ms 时间戳>,"y":<单位净值>,...}, ...];

取 `Data_netWorthTrend` 的最后一项即最新净值。份额与成本净值写在 config.yaml，
**只有申购/赎回时才需要改**——这是它和比特币（每周手动更新数量）最大的区别。

⚠️ QDII 净值 T+1/T+2 披露，因此天然滞后 1–2 个交易日，这不是抓取故障。
⚠️ 任一只基金取不到就整体判为不可用（由调用方沿用上次值），
   绝不用 0 或成本价冒充市值——那会让进度凭空变化。
"""

from __future__ import annotations

import json
import re
from datetime import datetime

from scripts import net

NAV_URL = "https://fund.eastmoney.com/pingzhongdata/{code}.js"

NETWORTH_RE = re.compile(r"var\s+Data_netWorthTrend\s*=\s*(\[.*?\])\s*;", re.S)
NAME_RE = re.compile(r'var\s+fS_name\s*=\s*"([^"]*)"')


def _parse(text: str) -> tuple[str, float, str]:
    """从 pingzhongdata 的 JS 文本里取（名称、最新净值、净值日期）。"""
    name_match = NAME_RE.search(text)
    name = name_match.group(1) if name_match else ""

    trend_match = NETWORTH_RE.search(text)
    if not trend_match:
        raise ValueError("未找到 Data_netWorthTrend")

    rows = json.loads(trend_match.group(1))
    if not rows:
        raise ValueError("净值序列为空")

    last = rows[-1]
    nav = float(last["y"])
    # x 是毫秒时间戳
    stamp = datetime.fromtimestamp(float(last["x"]) / 1000).strftime("%Y-%m-%d")
    return name, nav, stamp


def fetch(cfg) -> dict:
    """按 config 里的份额与成本净值，算出三只纳指100 的合计市值。"""
    specs = list(cfg.get("funds") or [])
    if not specs:
        return {"available": False, "warnings": ["纳指100：配置里没有 funds"]}

    url_template = cfg.get("nav_url") or NAV_URL
    funds: list[dict] = []
    warnings: list[str] = []
    nav_dates: list[str] = []

    for spec in specs:
        code = str(spec.get("code") or "").strip()
        if not code:
            return {"available": False, "warnings": ["纳指100：有一条配置缺 code"]}

        try:
            shares = float(spec["shares"])
            cost_nav = float(spec["cost_nav"])
        except (KeyError, TypeError, ValueError) as exc:
            return {
                "available": False,
                "warnings": [f"纳指100 {code}：shares / cost_nav 缺失或非法（{exc}）"],
            }

        try:
            text = net.fetch_text(url_template.format(code=code))
            name, nav, stamp = _parse(text)
        except Exception as exc:
            # 单只失败即整体失败：宁可沿用上次值，也不拿部分数据拼一个假合计
            return {
                "available": False,
                "warnings": [f"纳指100 {code}：抓取或解析失败：{exc}"],
            }

        market_value = shares * nav
        invested = shares * cost_nav
        nav_dates.append(stamp)
        funds.append(
            {
                "code": code,
                "short_name": spec.get("name") or name,
                "shares": round(shares, 4),
                "latest_nav": round(nav, 4),
                "nav_date": stamp,
                "market_value": round(market_value, 2),
                "invested": round(invested, 2),
                "profit": round(market_value - invested, 2),
                "return_rate": (market_value / invested - 1) if invested else None,
            }
        )

    market_value = sum(f["market_value"] for f in funds)
    invested = sum(f["invested"] for f in funds)

    return {
        "available": True,
        "market_value": round(market_value, 2),
        "invested": round(invested, 2),
        "profit": round(market_value - invested, 2),
        "return_rate": (market_value / invested - 1) if invested else None,
        # 三只基金的净值日通常一致；取最早的那个更保守
        "latest_nav_date": min(nav_dates) if nav_dates else None,
        "funds": funds,
        "warnings": warnings,
    }
