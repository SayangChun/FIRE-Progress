"""主入口：抓取 -> 计算 -> 落盘 -> 渲染 README。

用法：
    python scripts/update.py              # 正常跑（CI 用）
    python scripts/update.py --mock       # 用本地 fixture 跑，不联网
    python scripts/update.py --force      # 忽略变更阈值，强制重写
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import config as cfgmod  # noqa: E402
from scripts import fire as firemod  # noqa: E402
from scripts import render as rendermod  # noqa: E402
from scripts.sources import btc_repo, price as price_src, sp500 as sp500_src  # noqa: E402


# ------------------------------------------------------------------ 工具函数


def read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def read_fixture(name: str) -> str:
    # utf-8-sig：文件可能带 BOM，带与不带都能正确读取
    return (cfgmod.FIXTURES_DIR / name).read_text(encoding="utf-8-sig")


def load_fixture_json(name: str) -> dict:
    return json.loads(read_fixture(name))


# ------------------------------------------------------------------ 数据抓取


def fetch_all(cfg, mock: bool) -> tuple[dict, dict, dict]:
    """返回 (price, btc, sp500)。单个来源失败不阻断整体。"""
    if mock:
        print("[mock] 使用 tests/fixtures 下的样例数据")
        price = load_fixture_json("price.json")
        btc = btc_repo.fetch(cfg.sources.btc, csv_text=read_fixture("holdings.csv"))
        sp500 = load_fixture_json("sp500.json")
        return price, btc, sp500

    price = price_src.resolve(cfg)

    if cfg.sources.btc.get("enabled", True):
        btc = btc_repo.fetch(cfg.sources.btc)
    else:
        btc = {"available": False, "positions": [], "warnings": ["比特币：已在配置中禁用"]}

    if cfg.sources.sp500.get("enabled", True):
        sp500 = sp500_src.fetch(cfg.sources.sp500)
    else:
        sp500 = {"available": False, "warnings": ["标普500：已在配置中禁用"]}

    return price, btc, sp500


def apply_last_good(btc, sp500, previous: dict) -> tuple[dict, dict, list[str]]:
    """某个来源挂掉时沿用上次的可用值，并明确告警——绝不用 0 冒充持仓。

    注意：必须把「替换后的对象」显式返回，否则调用方拿到的仍是原来的变量。
    """
    notes: list[str] = []
    prev_assets = (previous or {}).get("assets") or {}

    if not btc.get("available") or not btc.get("total_btc"):
        cached = prev_assets.get("btc") or {}
        original_warnings = list(btc.get("warnings", []))
        if cached.get("qty"):
            print(f"[fallback] 比特币持仓不可用，沿用上次值 {cached['qty']}")
            btc = {
                "available": True,
                "total_btc": cached["qty"],
                "snapshot_date": cached.get("snapshot_date"),
                "stale_days": None,
                "cost_basis_usd": None,
                "positions": [],
                "warnings": [],
            }
            notes.append("比特币持仓取自上次成功值（本次未读到 holdings.csv）")
        else:
            # 没有缓存可退：绝不能把「拿不到数据」当成「持有 0 枚」写进去，
            # 那会让进度看起来凭空倒退，且没有任何痕迹。
            notes.append("⚠️ 比特币持仓不可用，本次进度**未计入比特币**，实际进度被低估")
        notes.extend(original_warnings)

    if not sp500.get("available") and prev_assets.get("sp500", {}).get("value_cny") is not None:
        sp = prev_assets["sp500"]
        sp500 = {
            "available": True,
            "market_value": sp.get("value_cny", 0.0),
            "invested": sp.get("invested_cny", 0.0),
            "profit": sp.get("profit_cny", 0.0),
            "return_rate": sp.get("return_rate"),
            "latest_nav_date": sp.get("latest_nav_date"),
            "funds": sp.get("funds", []),
            "timeline": [],
            "warnings": ["标普500：读取失败，沿用上次成功值"],
        }
        notes.append("标普500 市值取自上次成功值")

    return btc, sp500, notes


# ------------------------------------------------------------------ 快照


def upsert_snapshot(history: list[dict], data: dict) -> list[dict]:
    row = {
        "date": data["as_of_date"],
        "as_of": data["as_of"],
        "total_cny": data["assets"]["total_cny"],
        "progress_pct": data["assets"]["progress_pct"],
        "btc_cny": data["assets"]["btc"]["value_cny"],
        "btc_qty": data["assets"]["btc"]["qty"],
        "sp500_cny": data["assets"]["sp500"]["value_cny"],
        "target_cny": data["fire"]["target_cny"],
    }
    kept = [r for r in history if r.get("date") != row["date"]]
    kept.append(row)
    kept.sort(key=lambda r: r.get("date", ""))
    return kept


def is_material(previous: dict, data: dict, cfg) -> tuple[bool, str]:
    if not previous:
        return True, "首次生成"
    if previous.get("as_of_date") != data["as_of_date"]:
        return True, "新的一天"
    prev_total = ((previous.get("assets") or {}).get("total_cny")) or 0.0
    prev_pct = ((previous.get("assets") or {}).get("progress_pct")) or 0.0
    delta_cny = abs(data["assets"]["total_cny"] - prev_total)
    delta_pct = abs(data["assets"]["progress_pct"] - prev_pct)
    if delta_pct >= float(cfg.automation.get("min_commit_delta_pct", 0.005)):
        return True, f"完成度变动 {delta_pct:.4f} 个百分点"
    if delta_cny >= float(cfg.automation.get("min_commit_delta_cny", 1.0)):
        return True, f"总资产变动 {delta_cny:.2f} 元"
    return False, f"变动不足阈值（Δ{delta_cny:.4f} 元 / Δ{delta_pct:.6f} 个百分点）"


# ------------------------------------------------------------------ 主流程


def main() -> int:
    parser = argparse.ArgumentParser(description="更新 FIRE 进度")
    parser.add_argument("--config", default=None, help="配置文件路径")
    parser.add_argument("--mock", action="store_true", help="使用本地样例数据，不联网")
    parser.add_argument("--force", action="store_true", help="忽略变更阈值，强制重写")
    args = parser.parse_args()

    cfg = cfgmod.load(args.config)
    cfgmod.DATA_DIR.mkdir(parents=True, exist_ok=True)
    cfgmod.REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    previous = read_json(cfgmod.LATEST_PATH, {})
    history = read_json(cfgmod.HISTORY_PATH, [])
    if not isinstance(history, list):
        history = []

    print("→ 抓取数据源…")
    price, btc, sp500 = fetch_all(cfg, args.mock)
    print(f"  BTC/USDT = {price['btc_usdt']:,.2f} ({price['btc_source']})")
    print(f"  USD/CNY  = {price['usd_cny']:.4f} ({price['fx_source']})")
    print(f"  → BTC/CNY = {price['btc_cny']:,.2f}")
    if btc.get("available"):
        print(f"  比特币持仓快照 = {btc.get('snapshot_date')}（{btc.get('stale_days')} 天前）")

    btc, sp500, fallback_notes = apply_last_good(btc, sp500, previous)

    print("→ 计算 FIRE 进度…")
    data = firemod.compute(cfg, price=price, btc=btc, sp500=sp500, history=history)

    # 兜底说明排在前面，并去重（同一告警可能从来源和兜底两处各来一次）
    seen: set[str] = set()
    merged: list[str] = []
    for warn in [*fallback_notes, *data.get("warnings", [])]:
        if warn not in seen:
            seen.add(warn)
            merged.append(warn)
    data["warnings"] = merged

    fire = data["fire"]
    assets = data["assets"]
    print(f"  目标 = ¥{fire['target_cny']:,.2f}（{fire['monthly_expense']:.0f} × 12 ÷ {fire['withdrawal_rate']}）")
    print(f"  比特币 = {assets['btc']['qty']:.8f} → ¥{assets['btc']['value_cny']:,.2f}")
    print(f"  标普500 = ¥{assets['sp500']['value_cny']:,.2f}")
    print(f"  合计 = ¥{assets['total_cny']:,.2f}　完成度 = {assets['progress_pct']:.4f}%")

    material, reason = is_material(previous, data, cfg)
    if not material and not args.force:
        print(f"→ 跳过写入：{reason}")
        return 0
    print(f"→ 写入（{reason}）")

    history = upsert_snapshot(history, data)
    data["history_days"] = len(history)
    write_json(cfgmod.HISTORY_PATH, history)
    write_json(cfgmod.LATEST_PATH, data)

    if cfg.display.get("show_curve", True):
        svg = rendermod.curve_svg(history, cfg)
        (cfgmod.REPORTS_DIR / "curve.svg").write_text(svg, encoding="utf-8")
        print(f"→ 已写出 reports/curve.svg（{len(history)} 个数据点）")

    block = rendermod.render_block(data, cfg, history)
    readme_path = ROOT / "README.md"
    existing = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""
    if rendermod.START_MARK in existing:
        merged_readme = rendermod.merge_readme(existing, block)
    else:
        merged_readme = rendermod.default_readme(block, cfg)
    readme_path.write_text(merged_readme, encoding="utf-8")
    print("→ 已更新 README.md")

    if data["warnings"]:
        print("⚠️ 告警：")
        for warn in data["warnings"]:
            print(f"   - {warn}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
