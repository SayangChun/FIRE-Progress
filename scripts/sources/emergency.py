"""应急金：支付宝小荷包。

⚠️ 这个源和其它源**本质不同**，改之前先读这段：

- 比特币与标普500 都是「读别人的公开仓库」，这个没有对外接口——
  小荷包在支付宝 App 内，没有任何公开 API，所以余额**只能手动维护**。
- 数据来自仓库内的 `data/emergency.json`（**不联网**）。
  口径（名称、每月计划额、开始日期、核对周期）放 `config.yaml`，
  余额放数据文件——两者分离，改余额不用碰配置。
- **¥200/月是「计划」，不是数据。** 这里只读实际余额，绝不按公式推算：
  万一哪天应急动用了，公式会算出一个「钱还在」的假数字，而那是要出事的。
- 读不到或格式错时返回 `available=False`，由上层沿用上次成功值——
  **绝不静默按 0 处理**（「没读到」和「余额是 0」是两件事）。

聚合规则：直接取文件里的 `balance_cny`，不做任何推导。
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from scripts import config as cfgmod

DATE_FMT = "%Y-%m-%d"


def _resolve(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else cfgmod.ROOT / path


def fetch(cfg) -> dict:
    label = str(cfg.get("label") or "应急金")
    path = _resolve(str(cfg.get("path") or "data/emergency.json"))

    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            raw = json.load(fh)
    except Exception as exc:
        return {"available": False, "warnings": [f"{label}：读取 {path.name} 失败：{exc}"]}

    if not isinstance(raw, dict):
        return {"available": False, "warnings": [f"{label}：{path.name} 顶层必须是对象"]}

    try:
        balance = float(raw.get("balance_cny"))
        as_of = str(raw.get("as_of") or "").strip()
        snapshot = datetime.strptime(as_of, DATE_FMT).date()
    except Exception as exc:
        return {
            "available": False,
            "warnings": [f"{label}：{path.name} 格式有误（需要 balance_cny 与 as_of）：{exc}"],
        }

    if balance < 0:
        return {"available": False, "warnings": [f"{label}：余额为负数 {balance}，拒绝采用"]}

    # 计划开始日：在此之前视为「还没开始存」，不算过期（否则一建仓就先告警，很吵）
    started_on_raw = str(cfg.get("started_on") or "").strip()
    try:
        started_on = datetime.strptime(started_on_raw, DATE_FMT).date() if started_on_raw else None
    except ValueError:
        return {
            "available": False,
            "warnings": [f"{label}：config 里的 started_on 不是日期（{started_on_raw}）"],
        }

    today = date.today()
    stale_days = (today - snapshot).days
    started = (started_on is None) or (today >= started_on)

    warnings: list[str] = []
    max_stale = int(cfg.get("max_stale_days", 45))
    if started and stale_days > max_stale:
        warnings.append(
            f"{label}：余额已 {stale_days} 天未核对"
            f"（快照 {as_of}，超过 {max_stale} 天）——请更新 data/emergency.json"
        )

    return {
        "available": True,
        "label": label,
        "short_label": str(cfg.get("short_label") or label),
        "balance_cny": balance,
        "as_of": as_of,
        "stale_days": stale_days if started else None,
        "started": started,
        "started_on": started_on_raw or None,
        "monthly_plan_cny": float(cfg.get("monthly_plan_cny") or 0.0),
        "warnings": warnings,
    }
