"""FIRE 计算核心。

口径（唯一权威定义，改口径只改这里 + config.yaml）：

    FIRE 目标资产 = 月开销 × 12 ÷ 提取率
                  = 2000 × 12 ÷ 0.043
                  = 558,139.53 元

    当前资产 = 比特币市值 + 标普500基金市值
    完成度   = 当前资产 ÷ FIRE 目标资产

只统计这两项资产，其他一律不计入。
比特币持仓数量来自 0.1BTC 仓库（每周手动更新，存在延迟），
标普500持仓来自 sp500-dca 仓库；估值用实时行情折算成人民币。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def _now(tz_name: str = "Asia/Shanghai") -> datetime:
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo(tz_name))
    except Exception:
        # Windows 上可能没有 tzdata；北京无夏令时，直接用固定 +8 偏移
        if tz_name == "Asia/Shanghai":
            return datetime.now(timezone(timedelta(hours=8)))
        return datetime.now(timezone.utc).astimezone()


def target_cny(monthly_expense: float, withdrawal_rate: float) -> float:
    return monthly_expense * 12 / withdrawal_rate


def collect_warnings(*results: dict) -> list[str]:
    warnings: list[str] = []
    for result in results:
        warnings.extend(result.get("warnings", []) or [])
    return warnings


def projection(
    history: list[dict], remaining: float, window_days: int
) -> dict | None:
    """按近 window_days 的平均日增额线性外推达成时间。

    这是「线性外推」，不是预测——它假设未来增速与过去一致，
    而现实中资产会波动、定投会暂停。展示时必须标注清楚。
    """
    if not history or remaining <= 0:
        return None

    cutoff = _now().date() - timedelta(days=window_days)
    points: list[tuple] = []
    for row in history:
        try:
            day = datetime.strptime(row["date"], "%Y-%m-%d").date()
        except (KeyError, ValueError):
            continue
        if day >= cutoff:
            points.append((day, float(row.get("total_cny") or 0.0)))

    if len(points) < 2:
        return None

    points.sort(key=lambda x: x[0])
    span_days = (points[-1][0] - points[0][0]).days
    if span_days < 3:
        return None

    daily = (points[-1][1] - points[0][1]) / span_days
    if daily <= 0:
        return {
            "daily_gain_cny": round(daily, 4),
            "days_to_target": None,
            "eta": None,
            "window_days": window_days,
            "reason": "近窗口内资产未增长，无法外推",
        }

    days = int(remaining / daily)
    eta = _now().date() + timedelta(days=days)
    return {
        "daily_gain_cny": round(daily, 4),
        "days_to_target": days,
        "eta": eta.isoformat(),
        "window_days": window_days,
        "reason": None,
    }


def compute(
    cfg,
    *,
    price: dict,
    btc: dict,
    sp500: dict,
    history: list[dict],
    as_of: str | None = None,
) -> dict:
    monthly = float(cfg.fire.monthly_expense)
    rate = float(cfg.fire.withdrawal_rate)
    target = target_cny(monthly, rate)

    btc_qty = float(btc.get("total_btc") or 0.0)
    btc_value = btc_qty * float(price["btc_cny"])

    sp500_value = float(sp500.get("market_value") or 0.0)
    sp500_invested = float(sp500.get("invested") or 0.0)

    total = btc_value + sp500_value
    progress = total / target if target else 0.0
    remaining = max(target - total, 0.0)

    # --- 本金 ---
    # 标普500：优先取 config 手工值，否则用 sp500-dca 仓库的累计投入（精确值）
    cfg_basis = cfg.get("cost_basis") or {}
    sp500_basis = cfg_basis.get("sp500_cny")
    sp500_basis = sp500_invested if sp500_basis is None else float(sp500_basis)

    # 比特币：从持仓备注的「均价 $xx/BTC」推算，按当前汇率折算成人民币。
    # 这是估算——真实成本取决于买入当时的汇率，这里的折算会引入偏差，展示时要标注。
    btc_cost_usd = btc.get("cost_basis_usd")
    btc_basis = (
        float(btc_cost_usd) * float(price["usd_cny"]) if btc_cost_usd is not None else None
    )

    parts = [p for p in (btc_basis, sp500_basis) if p is not None]
    total_basis = sum(parts) if parts else None

    now = _now(cfg.automation.get("timezone", "Asia/Shanghai"))
    stamp = as_of or now.isoformat(timespec="seconds")

    return {
        "as_of": stamp,
        "as_of_date": now.strftime("%Y-%m-%d"),
        "fire": {
            "monthly_expense": monthly,
            "withdrawal_rate": rate,
            "annual_expense": monthly * 12,
            "target_cny": round(target, 2),
        },
        "assets": {
            "total_cny": round(total, 2),
            "progress": progress,
            "progress_pct": round(progress * 100, 4),
            "remaining_cny": round(remaining, 2),
            "btc": {
                "qty": round(btc_qty, 8),
                "price_cny": float(price["btc_cny"]),
                "value_cny": round(btc_value, 2),
                "snapshot_date": btc.get("snapshot_date"),
                "stale_days": btc.get("stale_days"),
                "positions": list(btc.get("positions", [])),
            },
            "sp500": {
                "value_cny": round(sp500_value, 2),
                "invested_cny": round(sp500_invested, 2),
                "profit_cny": round(sp500.get("profit") or 0.0, 2),
                "return_rate": sp500.get("return_rate"),
                "latest_nav_date": sp500.get("latest_nav_date"),
                "funds": sp500.get("funds", []),
            },
        },
        "cost_basis": {
            "btc_cny": round(btc_basis, 2) if btc_basis is not None else None,
            "btc_estimated": btc_basis is not None,
            "sp500_cny": round(sp500_basis, 2),
            "total_cny": round(total_basis, 2) if total_basis is not None else None,
            "profit_cny": round(total - total_basis, 2) if total_basis is not None else None,
        },
        "price": price,
        "projection": (
            projection(history, remaining, int(cfg.display.get("projection_window_days", 30)))
            if cfg.display.get("show_projection")
            else None
        ),
        "sources": {
            "btc": btc.get("available", False),
            "sp500": sp500.get("available", False),
        },
        "warnings": collect_warnings(btc, sp500),
    }
