"""USD/CNY 汇率。

设计要点：
- 汇率源按 config 顺序逐个尝试，任一成功即返回，并记录实际来源。
- 全部失败时抛出异常，由上层决定「沿用上次值」还是「标记数据缺失」，
  绝不静默返回 0——把 0 当成汇率会让折算结果凭空失真。
"""

from __future__ import annotations

from datetime import datetime, timezone

from scripts import net

ER_API = "https://open.er-api.com/v6/latest/USD"
FRANKFURTER = "https://api.frankfurter.dev/v1/latest?base=USD&symbols=CNY"


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


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
    """汇总一次汇率快照。"""
    fx, fx_src = usd_cny(list(cfg.price.fx_sources), cfg.price.get("fallback_fx_usdcny"))
    return {
        "usd_cny": fx,
        "fx_source": fx_src,
        "fetched_at": _now_iso(),
    }
