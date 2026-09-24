"""BTC 价格与 USD/CNY 汇率。

设计要点：
- 价格源按 config 顺序逐个尝试，任一成功即返回，并记录实际来源。
- 全部失败时抛出异常，由上层决定「沿用上次值」还是「标记数据缺失」，
  绝不静默返回 0——把 0 当成持仓会让进度看起来凭空倒退。
"""

from __future__ import annotations

from datetime import datetime, timezone

from scripts import net

BINANCE_SPOT = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
BINANCE_VISION = "https://data-api.binance.vision/api/v3/ticker/price?symbol=BTCUSDT"
OKX_TICKER = "https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT"

ER_API = "https://open.er-api.com/v6/latest/USD"
FRANKFURTER = "https://api.frankfurter.dev/v1/latest?base=USD&symbols=CNY"


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _btc_from_binance() -> tuple[float, str]:
    payload = net.fetch_json(BINANCE_SPOT)
    price = float(payload["price"])
    return price, "binance:api.binance.com"


def _btc_from_binance_vision() -> tuple[float, str]:
    payload = net.fetch_json(BINANCE_VISION)
    price = float(payload["price"])
    return price, "binance:data-api.binance.vision"


def _btc_from_okx() -> tuple[float, str]:
    payload = net.fetch_json(OKX_TICKER)
    if payload.get("code") != "0" or not payload.get("data"):
        raise RuntimeError(f"OKX 行情返回异常: {payload.get('msg') or payload.get('code')}")
    price = float(payload["data"][0]["last"])
    return price, "okx:www.okx.com"


BTC_PROVIDERS = {
    "binance": _btc_from_binance,
    "binance_vision": _btc_from_binance_vision,
    "okx": _btc_from_okx,
}


def btc_usdt(order: list[str]) -> tuple[float, str]:
    """按顺序尝试各行情源，返回 (价格, 来源)。"""
    errors: list[str] = []
    for name in order:
        provider = BTC_PROVIDERS.get(name)
        if provider is None:
            errors.append(f"{name}: 未知数据源")
            continue
        try:
            price, label = provider()
            if price > 0:
                return price, label
            errors.append(f"{name}: 价格非正数 {price}")
        except Exception as exc:
            errors.append(f"{name}: {exc}")
    raise RuntimeError("全部 BTC 行情源失败 -> " + " | ".join(errors))


def _fx_er_api() -> tuple[float, str]:
    payload = net.fetch_json(ER_API)
    rate = float(payload["rates"]["CNY"])
    return rate, "open.er-api.com"


def _fx_frankfurter() -> tuple[float, str]:
    payload = net.fetch_json(FRANKFURTER)
    rate = float(payload["rates"]["CNY"])
    return rate, "api.frankfurter.dev"


FX_PROVIDERS = {
    "er-api": _fx_er_api,
    "frankfurter": _fx_frankfurter,
}


def usd_cny(order: list[str], fallback: float | None = None) -> tuple[float, str]:
    """按顺序尝试汇率源，返回 (汇率, 来源)。全部失败时使用兜底值并标注。"""
    errors: list[str] = []
    for name in order:
        provider = FX_PROVIDERS.get(name)
        if provider is None:
            errors.append(f"{name}: 未知数据源")
            continue
        try:
            rate, label = provider()
            if rate > 0:
                return rate, label
            errors.append(f"{name}: 汇率非正数 {rate}")
        except Exception as exc:
            errors.append(f"{name}: {exc}")

    if fallback:
        return float(fallback), f"fallback({fallback}) 兜底"
    raise RuntimeError("全部汇率源失败 -> " + " | ".join(errors))


def resolve(cfg) -> dict:
    """汇总一次价格快照。"""
    btc_price, btc_src = btc_usdt(list(cfg.price.btc_sources))
    fx, fx_src = usd_cny(list(cfg.price.fx_sources), cfg.price.get("fallback_fx_usdcny"))
    return {
        "btc_usdt": btc_price,
        "usd_cny": fx,
        "btc_cny": round(btc_price * fx, 2),
        "btc_source": btc_src,
        "fx_source": fx_src,
        "fetched_at": _now_iso(),
    }
