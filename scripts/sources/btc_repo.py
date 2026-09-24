"""比特币持仓：读取 0.1BTC 仓库的 data/holdings.csv。

仓库：https://github.com/SayangChun/0.1BTC
该文件由本人**每周手动更新一次**，因此数据存在延迟，不代表实时持仓。

CSV 格式（字段名固定）：
    date,location,btc,note
    2026-09-20,binance,0.00785078,"Binance账户；均价 $68,163.56/BTC"
    2026-09-20,okx,0.0152673,"OKX账户；均价 $68,158.3/BTC"

聚合规则（与 0.1BTC 仓库自己的 scripts/update_readme.py 保持一致）：
    取「日期最新」的那一天，把该天所有 location 相加，即为当前持仓。
    未出现在最新那天的 location 视为 0（**不做 carry-forward**），
    所以每次更新必须把每个账户都写一遍——这是仓库既有的约定，不要自行改成
    「每个 location 取各自最新一行」，两者结果会不一样。
"""

from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime

from scripts import net

RAW_TEMPLATE = "https://raw.githubusercontent.com/{repo}/{ref}/{path}"

# 从备注里解析均价，例如「均价 $68,163.56/BTC」「均价 $66,966.9/BTC」
AVG_PRICE_RE = re.compile(r"均价\s*\$([\d,]+(?:\.\d+)?)\s*/\s*BTC")

LOCATION_LABELS = {
    "binance": "币安",
    "okx": "欧易",
    "hot": "热钱包",
    "other": "其他",
    "cold": "冷钱包",
    "exchange": "交易所",
}


def _read_rows(text: str) -> list[dict[str, str]]:
    """读 CSV：跳过空行与 # 注释行，并剥掉可能存在的 UTF-8 BOM。

    BOM 会让首列名变成 '\\ufeffdate'，导致所有行都取不到 date 而被静默丢弃——
    仓库里的 CSV 是手工维护的，带不带 BOM 说不准，这里必须兜住。
    """
    text = text.lstrip("\ufeff")
    lines = [
        line
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    if not lines:
        return []
    return list(csv.DictReader(io.StringIO("\n".join(lines))))


def _parse_avg_usd(note: str) -> float | None:
    match = AVG_PRICE_RE.search(note or "")
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def parse_holdings(text: str) -> dict:
    """把 holdings.csv 的文本解析成当前持仓。纯函数，便于测试。"""
    rows: list[dict] = []
    for raw in _read_rows(text):
        date_s = (raw.get("date") or "").strip()
        location = (raw.get("location") or "").strip().lower()
        btc_s = (raw.get("btc") or "").strip()
        if not (date_s and location and btc_s):
            continue
        try:
            btc = float(btc_s)
        except ValueError:
            continue
        rows.append(
            {
                "date": date_s,
                "location": location,
                "btc": btc,
                "note": (raw.get("note") or "").strip(),
            }
        )

    if not rows:
        raise ValueError("holdings.csv 中没有可用的数据行")

    latest_date = max(r["date"] for r in rows)
    # 同一天同一 location 若重复出现，后写的覆盖先写的
    by_location: dict[str, dict] = {}
    for row in rows:
        if row["date"] == latest_date:
            by_location[row["location"]] = row

    positions = []
    for location, row in by_location.items():
        positions.append(
            {
                "venue": LOCATION_LABELS.get(location, location),
                "location": location,
                "product": "账户持仓",
                "asset": "BTC",
                "amount": row["btc"],
                "avg_usd": _parse_avg_usd(row["note"]),
                "note": row["note"],
            }
        )
    # 展示顺序固定，避免每次运行顺序漂移造成无意义的 diff
    order = ["binance", "okx", "hot", "other", "cold", "exchange"]
    positions.sort(key=lambda p: order.index(p["location"]) if p["location"] in order else 99)

    total_btc = sum(p["amount"] for p in positions)

    # 成本推算：只有全部持仓都能解析出均价时才给结果，否则宁可不出数
    avg_prices = [p["avg_usd"] for p in positions]
    cost_usd = None
    if positions and all(a is not None for a in avg_prices):
        cost_usd = sum(p["amount"] * p["avg_usd"] for p in positions)

    snapshot = datetime.strptime(latest_date, "%Y-%m-%d").date()
    stale_days = (date.today() - snapshot).days

    return {
        "available": True,
        "total_btc": total_btc,
        "snapshot_date": latest_date,
        "stale_days": stale_days,
        "cost_basis_usd": cost_usd,
        "positions": positions,
        "warnings": [],
    }


def fetch(cfg, csv_text: str | None = None) -> dict:
    """csv_text 为空时从仓库下载；传入时直接用（供本地 --mock 使用）。"""
    if csv_text is None:
        url = RAW_TEMPLATE.format(
            repo=cfg.repo, ref=cfg.get("ref", "main"), path=cfg.holdings_path
        )
        try:
            csv_text = net.fetch_text(url)
        except Exception as exc:
            return {"available": False, "positions": [], "warnings": [f"比特币：读取 holdings.csv 失败：{exc}"]}

    try:
        result = parse_holdings(csv_text)
    except Exception as exc:
        return {"available": False, "positions": [], "warnings": [f"比特币：解析 holdings.csv 失败：{exc}"]}

    max_stale = int(cfg.get("max_stale_days", 14))
    if result["stale_days"] > max_stale:
        result["warnings"].append(
            f"比特币持仓快照为 {result['snapshot_date']}，距今 {result['stale_days']} 天"
            f"（超过 {max_stale} 天未更新）"
        )
    if not cfg.get("derive_cost_from_note", True):
        result["cost_basis_usd"] = None
    return result
