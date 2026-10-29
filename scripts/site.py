"""把最新数据渲染成一个可以直接看的静态页（GitHub Pages 用）。

和 README 的关系：README 是给 GitHub 上的读者看的，这个页面是给手机浏览器看的。
两者共用 data/latest.json，所以数字不会打架；图表直接复用 reports/ 下的三个 SVG。

用法：
    python scripts/site.py                  # 输出到 site/
    python scripts/site.py --out /tmp/site   # 输出到别处（CI 用）
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from . import config as cfgmod

# 资产顺序固定，避免 dict 顺序变化导致页面上下跳
ASSET_LABELS = {
    "btc": "比特币",
    "sp500": "标普500基金",
    "ndx100": "纳指100基金",
}

CSS = """
:root {
  --bg: #ffffff;
  --bg-soft: #f6f7f8;
  --fg: #1f2328;
  --muted: #5c6670;
  --line: #e6e8eb;
  --accent: #c2410c;
  --accent-soft: #fdf0e7;
  --up: #15803d;
  --down: #b91c1c;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0d1117;
    --bg-soft: #161b22;
    --fg: #e6edf3;
    --muted: #9198a1;
    --line: #262c34;
    --accent: #f0b429;
    --accent-soft: #2a2113;
    --up: #3fb950;
    --down: #f85149;
  }
}
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--fg);
  font-family: ui-sans-serif, system-ui, -apple-system, "PingFang SC",
    "Microsoft YaHei", "Segoe UI", sans-serif;
  font-size: 16px;
  line-height: 1.7;
  font-variant-numeric: tabular-nums;
}
main { max-width: 42rem; margin: 0 auto; padding: 28px 20px 64px; }
h1, h2, h3 { line-height: 1.3; font-weight: 600; }
h2 {
  font-size: 1.05rem;
  margin: 40px 0 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--line);
}
p { margin: 10px 0; }
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
.muted { color: var(--muted); font-size: 0.85rem; }

.hero { margin-bottom: 8px; }
.eyebrow {
  font-size: 0.78rem;
  letter-spacing: 0.12em;
  color: var(--muted);
  margin: 0 0 6px;
}
.hero .pct {
  font-size: 3rem;
  font-weight: 700;
  margin: 0;
  letter-spacing: -0.02em;
}
.bar {
  height: 10px;
  background: var(--bg-soft);
  border-radius: 999px;
  overflow: hidden;
  margin: 14px 0 10px;
}
.bar > span {
  display: block;
  height: 100%;
  background: var(--accent);
  border-radius: 999px;
  min-width: 3px;
}
.hero .sub { margin: 0; font-size: 0.95rem; }

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(8.5rem, 1fr));
  gap: 1px;
  background: var(--line);
  border: 1px solid var(--line);
  border-radius: 10px;
  overflow: hidden;
  margin: 18px 0 0;
}
.grid div { background: var(--bg); padding: 12px 14px; }
.grid dt { font-size: 0.76rem; color: var(--muted); margin: 0 0 2px; }
.grid dd { margin: 0; font-size: 1.02rem; font-weight: 600; }

table { width: 100%; border-collapse: collapse; font-size: 0.92rem; }
th, td { padding: 8px 6px; border-bottom: 1px solid var(--line); text-align: left; }
th { color: var(--muted); font-weight: 500; font-size: 0.8rem; }
td.num, th.num { text-align: right; }
tr:last-child td { border-bottom: 0; }
.total td { font-weight: 600; }

figure { margin: 14px 0 0; }
figure img { width: 100%; height: auto; display: block; }
figcaption { font-size: 0.8rem; color: var(--muted); margin-top: 8px; }

details {
  margin: 14px 0 0;
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 0 14px;
}
details[open] { padding-bottom: 12px; }
summary {
  cursor: pointer;
  padding: 12px 0;
  font-weight: 500;
  list-style: none;
}
summary::-webkit-details-marker { display: none; }
summary::before { content: "＋ "; color: var(--muted); }
details[open] summary::before { content: "－ "; }

.note {
  background: var(--bg-soft);
  border-left: 3px solid var(--accent);
  border-radius: 0 8px 8px 0;
  padding: 10px 14px;
  font-size: 0.85rem;
  color: var(--muted);
  margin: 14px 0 0;
}
.note strong { color: var(--fg); font-weight: 600; }
.warn { border-left-color: var(--down); }
.up { color: var(--up); }
.down { color: var(--down); }

footer {
  margin-top: 48px;
  padding-top: 16px;
  border-top: 1px solid var(--line);
  font-size: 0.8rem;
  color: var(--muted);
}
"""


def money(value, cfg, decimals: int = 2) -> str:
    if value is None:
        return "—"
    if cfg.privacy.get("mode") == "masked":
        return "已隐藏"
    symbol = cfg.fire.get("currency_symbol", "¥")
    return f"{symbol}{value:,.{decimals}f}"


def pct(value: float, decimals: int = 1) -> str:
    return f"{value:.{decimals}f}%"


def asset_rows(assets: dict, cfg) -> list[tuple[str, float, float]]:
    rows: list[tuple[str, float, float]] = []
    total = assets.get("total_cny") or 0
    for key, label in ASSET_LABELS.items():
        item = assets.get(key)
        if not isinstance(item, dict) or item.get("value_cny") is None:
            continue
        value = float(item["value_cny"])
        share = value / total * 100 if total else 0.0
        rows.append((label, value, share))
    return rows


def build_page(data: dict, cfg, history: list[dict], out_dir: Path) -> str:
    fire = data["fire"]
    assets = data["assets"]
    masked = cfg.privacy.get("mode") == "masked"

    progress = float(assets.get("progress_pct") or 0.0)
    total = assets.get("total_cny")
    target = fire.get("target_cny")
    remaining = assets.get("remaining_cny")

    as_of = data["as_of"].replace("T", " ")[:16]
    btc_snap = (assets.get("btc") or {}).get("snapshot_date") or "—"
    stale = (assets.get("btc") or {}).get("stale_days")
    nav_date = (assets.get("sp500") or {}).get("latest_nav_date") or "—"

    cards = [
        ("FIRE 目标", money(target, cfg)),
        ("当前资产", money(total, cfg)),
        ("距离目标", money(remaining, cfg)),
        ("完成度", pct(progress, 2)),
    ]
    labor = fire.get("labor_income")
    if labor:
        cards.append(("兼职净收入（月）", money(labor.get("net_monthly_cny"), cfg)))
        cards.append(("组合需覆盖（月）", money(fire.get("net_monthly_expense"), cfg)))

    card_html = "".join(
        f'<div><dt>{name}</dt><dd>{value}</dd></div>' for name, value in cards
    )

    rows = asset_rows(assets, cfg)
    asset_table = "".join(
        f"<tr><td>{label}</td><td class='num'>{money(value, cfg)}</td>"
        f"<td class='num'>{pct(share)}</td></tr>"
        for label, value, share in rows
    )
    asset_table += (
        f"<tr class='total'><td>合计</td><td class='num'>{money(total, cfg)}</td>"
        f"<td class='num'>100.0%</td></tr>"
    )

    # ---- 投入与盈亏
    basis = data.get("cost_basis") or {}
    basis_html = ""
    if basis.get("total_cny") is not None:
        profit = float(basis.get("profit_cny") or 0)
        base = float(basis.get("total_cny") or 0)
        rate = profit / base * 100 if base else 0.0
        tone = "up" if profit >= 0 else "down"
        basis_html = f"""
      <h2>投入与盈亏</h2>
      <table>
        <tr><th>累计投入</th><td class="num">{money(basis.get('total_cny'), cfg)}</td></tr>
        <tr><th>当前市值</th><td class="num">{money(total, cfg)}</td></tr>
        <tr><th>累计盈亏</th><td class="num {tone}">{money(profit, cfg)}</td></tr>
        <tr><th>累计收益率</th><td class="num {tone}">{rate:+.2f}%</td></tr>
      </table>
      <p class="note">比特币本金按持仓备注的均价推算，用当前汇率折算，和真实买入成本有偏差。</p>
    """

    # ---- 月开销
    plan = data.get("life_plan") or {}
    plan_html = ""
    if plan.get("groups"):
        one_off = plan.get("one_off_total")
        one_off_line = (
            f'<p class="muted">一次性落地支出 {money(one_off, cfg)}，不计入月开销。</p>'
            if one_off
            else ""
        )
        items = "".join(
            f"<tr><td>{item['label']}</td>"
            f"<td class='num'>{money(item['monthly'], cfg)}</td></tr>"
            for group in plan["groups"]
            for item in group["items"]
        )
        plan_html = f"""
      <details>
        <summary>月开销明细 · {plan.get('headline') or plan.get('profile') or ''}</summary>
        <table>
          {items}
          <tr class="total"><td>合计（{sum(len(g['items']) for g in plan['groups'])} 项）</td>
          <td class="num">{money(plan['monthly_expense'], cfg)}</td></tr>
        </table>
        {one_off_line}
      </details>
    """

    # ---- 被动收入
    pi = data.get("passive_income") or {}
    passive_html = ""
    if pi.get("hourly_cny") is not None:
        passive_html = f"""
      <h2>每小时被动收入</h2>
      <p><strong>{money(pi['hourly_cny'], cfg, 2)}</strong> / 小时 ·
        {money(pi['monthly_cny'], cfg)} / 月 ·
        {money(pi['annual_cny'], cfg)} / 年</p>
      <p class="muted">按当前持仓和预期年化 {pct((pi['weighted_rate'] or 0) * 100)} 加权算出来的，
        相当于月开销的 {pct((pi.get('coverage') or 0) * 100)}。</p>
      <p class="note warn">这是「资产平均在长多快」，不是「能花多少」。
        按 {pct((pi.get('withdrawal_rate') or 0) * 100)} 提取率算，同样这笔资产每月只有
        {money(pi.get('monthly_at_withdrawal_cny'), cfg)}。</p>
    """

    # ---- 外推
    proj = data.get("projection") or {}
    proj_html = ""
    if proj.get("days_to_target"):
        days = int(proj["days_to_target"])
        horizon = f"{days} 天" if days < 365 else f"{days / 365:.1f} 年"
        proj_html = f"""
      <h2>线性外推</h2>
      <p>按真实定投额（比特币 {money(proj['btc_cny_per_day'], cfg)}/天
        + 标普500 {money(proj['sp500_cny_per_day'], cfg)}/天，
        合计 {money(proj['daily_cny'], cfg)}/天），约 <strong>{horizon}</strong> 后达到目标（{proj['eta']}）。</p>
      <p class="note">只算投入，不算涨跌：假设定投不中断、价格不变。</p>
    """

    fig = lambda name, alt, cap: (
        f'<figure><img src="{name}" alt="{alt}" loading="lazy">'
        f"<figcaption>{cap}</figcaption></figure>"
        if (out_dir / name).exists()
        else ""
    )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<meta name="description" content="FIRE 进度看板：只统计长期不动用的资产，跟着行情自动更新。">
<title>FIRE 进度 · {pct(progress, 2)}</title>
<style>{CSS}</style>
</head>
<body>
<main>
  <header class="hero">
    <p class="eyebrow">FIRE 进度</p>
    <h1 class="pct">{pct(progress, 2)}</h1>
    <div class="bar"><span style="width:{min(progress, 100):.2f}%"></span></div>
    <p class="sub">{money(total, cfg)} / {money(target, cfg)}</p>
    <p class="muted">更新于 {as_of}　·　比特币快照 {btc_snap}
      （{stale if stale is not None else '—'} 天前）　·　基金净值日 {nav_date}</p>
  </header>

  <dl class="grid">{card_html}</dl>

  <h2>进度曲线</h2>
  {fig("curve.svg", "FIRE 进度曲线", "竖虚线是口径调整日，那天目标变了，所以曲线出现台阶。")}

  <h2>资产构成</h2>
  <table>
    <tr><th>资产</th><th class="num">市值</th><th class="num">占比</th></tr>
    {asset_table}
  </table>
  <p class="note">只算长期不动用的钱，日常现金和活期不算。所以进度下跌未必是亏了，可能只是钱变成了现金。</p>
{basis_html}
  <h2>收益曲线</h2>
  {fig("profit.svg", "FIRE 收益曲线", "上面板是投入和市值，下面板是收益率。加仓会让收益率下降，因为本金变大、盈亏不变。")}
{plan_html}
{passive_html}
{proj_html}

  <footer>
    <p>数据源：<a href="https://github.com/{cfg.sources.btc.repo}">比特币持仓</a>（每周手动快照）、
      <a href="https://github.com/{cfg.sources.sp500.repo}">基金持仓</a>。
      行情来自 Binance，汇率来自 open.er-api.com。</p>
    <p>个人资产记录，不构成任何投资建议。完整说明见
      <a href="https://github.com/{cfg.sources.btc.repo.rsplit('/', 1)[0]}/FIRE-Progress">GitHub 仓库</a>。</p>
  </footer>
</main>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 FIRE 进度静态页")
    parser.add_argument("--out", default="site", help="输出目录")
    args = parser.parse_args()

    cfg = cfgmod.load()
    data = json.loads(cfgmod.LATEST_PATH.read_text(encoding="utf-8"))
    history = json.loads(cfgmod.HISTORY_PATH.read_text(encoding="utf-8"))

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 图表直接复用 update.py 生成的 SVG
    for svg in ("curve.svg", "progress.svg", "profit.svg"):
        src = cfgmod.REPORTS_DIR / svg
        if src.exists():
            shutil.copy2(src, out_dir / svg)

    html = build_page(data, cfg, history, out_dir)
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    print(f"→ 已写出 {out_dir / 'index.html'}（{len(html):,} 字节）")


if __name__ == "__main__":
    main()
