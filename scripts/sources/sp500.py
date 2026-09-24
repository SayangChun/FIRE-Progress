"""读取 sp500-dca 仓库的持仓数据。

数据源：https://github.com/SayangChun/sp500-dca
- data/portfolio.json  -> total.market_value / total.invested / total.profit
- data/timeline.json   -> 逐日 {date, invested, market_value, profit}

注意：QDII 基金净值 T+1 晚间披露，因此该仓库的数据天然滞后 1 个交易日左右，
      这是数据源的节奏，不是抓取故障。
"""

from __future__ import annotations

from scripts import net

RAW_TEMPLATE = "https://raw.githubusercontent.com/{repo}/{ref}/{path}"


def _raw(cfg, path: str) -> dict:
    url = RAW_TEMPLATE.format(repo=cfg.repo, ref=cfg.get("ref", "main"), path=path)
    return net.fetch_json(url)


def fetch(cfg) -> dict:
    try:
        portfolio = _raw(cfg, cfg.portfolio_path)
    except Exception as exc:
        return {"available": False, "warnings": [f"标普500：读取 portfolio.json 失败：{exc}"]}

    total = portfolio.get("total") or {}
    result = {
        "available": True,
        "market_value": float(total.get("market_value") or 0.0),
        "invested": float(total.get("invested") or 0.0),
        "profit": float(total.get("profit") or 0.0),
        "return_rate": float(total.get("return_rate") or 0.0),
        "trading_days": int(total.get("trading_days") or 0),
        "latest_nav_date": portfolio.get("latest_nav_date"),
        "updated_at": portfolio.get("updated_at"),
        "funds": [
            {
                "code": f.get("code"),
                "short_name": f.get("short_name"),
                "market_value": float(f.get("market_value") or 0.0),
                "invested": float(f.get("invested") or 0.0),
                "shares": float(f.get("shares") or 0.0),
                "latest_nav": float(f.get("latest_nav") or 0.0),
            }
            for f in portfolio.get("funds", []) or []
        ],
        "warnings": list(portfolio.get("warnings") or []),
    }

    # 时间线用于绘制曲线，失败不影响主流程
    try:
        timeline = _raw(cfg, cfg.get("timeline_path", "data/timeline.json"))
        result["timeline"] = timeline if isinstance(timeline, list) else []
    except Exception:
        result["timeline"] = []

    return result
