"""「出发门槛」与「全职情景」的回归测试（2026-10-31 新增）。

这两段都不是口径的微调，是**计划结构变了**：

    旧：攒够 ¥205,953 再出发（阶段 A 靠兼职 + 消耗本金）
    新：毕业后就出发，阶段 A 有工作（全职优先，兼职兜底）

所以最要紧的一条是第 4 条——**加全职不能让 FIRE 目标动一分钱**。
全职净收入大于月开销，一旦有人把它塞进 `_net_after_labor`，
目标会变成负数并静默通过所有下游计算，看板上看不出来。

钉住这几条：
  1. 出发门槛 = 医疗专项 + 一次性搬家 + 空窗期月开销
  2. 全职净收入按「只扣工作增量」算，与兼职同一套算法
  3. 全职盈余 = 净收入 − 月开销（不是 − 净月开销）
  4. **加全职不改变 target_cny**（核心）
  5. 关闭任一段后必须精确退回原行为，不报错、不出空表
  6. 双线进度条在没有 departure 时返回 None，调用方退回单条

运行：python tests/test_departure_fulltime.py
"""

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from scripts import config as cfgmod  # noqa: E402
from scripts import fire as fire_mod  # noqa: E402
from scripts import lifeplan as lifeplan_mod  # noqa: E402
from scripts import render as render_mod  # noqa: E402

cfg = cfgmod.load()

failures: list[str] = []


def ok(label: str, cond: bool, extra: str = "") -> None:
    if cond:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}" + (f" -- {extra}" if extra else ""))
        failures.append(label)


def variant(**overrides):
    data = copy.deepcopy(dict(cfg))
    for dotted, value in overrides.items():
        node = data
        parts = dotted.split(".")
        for key in parts[:-1]:
            node = node[key]
        node[parts[-1]] = value
    return cfgmod.Config(data)


monthly = lifeplan_mod.monthly_total(cfg)
target = lifeplan_mod.summary(cfg)["target_cny"]

print("出发门槛")
gate = lifeplan_mod.departure_gate(cfg)
ok("开启时返回 dict", isinstance(gate, dict))
ok(
    "下沿 = 医疗下沿 + 搬家 + 空窗下沿",
    abs(gate["low_cny"] - (gate["medical_low_cny"] + gate["moving_cny"] + gate["gap_low_cny"])) < 0.01,
    str(gate["low_cny"]),
)
ok(
    "上沿 = 医疗上沿 + 搬家 + 空窗上沿",
    abs(gate["high_cny"] - (gate["medical_high_cny"] + gate["moving_cny"] + gate["gap_high_cny"])) < 0.01,
    str(gate["high_cny"]),
)
ok("下沿 < 上沿", gate["low_cny"] < gate["high_cny"], f'{gate["low_cny"]} vs {gate["high_cny"]}')
ok("搬家费取自 life_plan.one_off，与配置同源", abs(gate["moving_cny"] - 15000) < 0.01)
ok("空窗期按当前月开销折算", abs(gate["gap_low_cny"] - monthly * 3) < 0.01, str(gate["gap_low_cny"]))
ok("下沿落在 ¥6–8 万区间", 60000 < gate["low_cny"] < 80000, str(gate["low_cny"]))

off_gate = variant(**{"departure.enabled": False})
ok("关闭时返回 None", lifeplan_mod.departure_gate(off_gate) is None)

print("\n全职净收入")
ft = lifeplan_mod.fulltime_income(cfg)
ok("开启时返回 dict", isinstance(ft, dict))
ok(
    "毛收入 = 周工时 × 52÷12 × 时薪",
    abs(ft["gross_monthly_cny"] - 40 * 52 / 12 * 17) < 0.02,
    str(ft["gross_monthly_cny"]),
)
ok(
    "净收入 = 毛收入 − 增量消耗",
    abs(ft["net_monthly_cny"] - (ft["gross_monthly_cny"] - ft["cost_monthly_cny"])) < 0.02,
    str(ft["net_monthly_cny"]),
)
ok("净收入约 ¥2,739", abs(ft["net_monthly_cny"] - 2739.33) < 0.05, str(ft["net_monthly_cny"]))
ok(
    "只扣增量：餐食是 ¥154（22 天 × ¥7），不是全天饭钱",
    abs(ft["meal_cny"] - 154) < 0.01,
    str(ft["meal_cny"]),
)
ok(
    "等效时薪低于净时薪（通勤计入占用）",
    ft["effective_hourly_cny"] < ft["net_hourly_cny"],
    f'{ft["effective_hourly_cny"]} vs {ft["net_hourly_cny"]}',
)
ok("月占用 195 小时（含 1h 通勤 × 21.67 天）", abs(ft["occupied_hours_per_month"] - 195) < 0.5)

off_ft = variant(**{"fire.fulltime.enabled": False})
ok("关闭时返回 None", lifeplan_mod.fulltime_income(off_ft) is None)

print("\n全职盈余")
ok(
    "盈余 = 净收入 − 月开销（不是 − 净月开销）",
    abs((ft["net_monthly_cny"] - monthly) - 1278.33) < 0.05,
    str(ft["net_monthly_cny"] - monthly),
)
ok(
    "盈余 = (全职净收入 − 兼职净收入) − 净月开销",
    abs(
        (ft["net_monthly_cny"] - monthly)
        - ((ft["net_monthly_cny"] - 723) - (monthly - 723))
    )
    < 0.01,
    str(ft["net_monthly_cny"] - monthly),
)

print("\n包吃住：阶段 A 个人月开销")
covered = cfg["fire"]["fulltime"]["covered_keys"]
stage_a = lifeplan_mod.monthly_excluding(cfg, covered)
ok(
    "被包吃住覆盖后阶段 A 个人开销约 ¥556",
    abs(stage_a - 556) < 1.0,
    str(stage_a),
)
ok(
    "覆盖项正是房租/取暖/物业费/食品/饮用水（合计 ¥905）",
    abs(monthly - stage_a - 905) < 1.0,
    str(monthly - stage_a),
)

print("\n⚠️ 核心：全职 + 包吃住都不改变 FIRE 目标")
ok("目标仍是 ¥205,953.49", abs(target - 205953.49) < 0.01, str(target))
ok(
    "目标只由「月开销 − 兼职净收入」决定",
    abs(target - (monthly - 723) * 12 / 0.043) < 0.01,
    str(target),
)
try:
    lifeplan_mod._net_after_labor(monthly, ft)
    ok("把全职塞进 _net_after_labor 必须报错", False, "没有报错，目标会变成负数")
except lifeplan_mod.LifePlanError:
    ok("把全职塞进 _net_after_labor 必须报错", True)

print("\ncompute() 的输出")
import contextlib  # noqa: E402
import io  # noqa: E402

with contextlib.redirect_stdout(io.StringIO()):
    import test_fire_core as T  # noqa: E402

PRICE = dict(T.PRICE)
PRICE.setdefault("btc_source", "binance")
PRICE.setdefault("fx_source", "er-api")
data = fire_mod.compute(
    cfg, price=PRICE, btc=T.BTC, sp500=T.SP500, ndx100=T.NDX, history=[]
)
ok("compute 带 departure", isinstance(data.get("departure"), dict))
ok("compute 带 fulltime", isinstance(data.get("fulltime"), dict))
ok("compute 的目标未被全职影响", abs(data["fire"]["target_cny"] - target) < 0.01)
# 关掉包吃住必须精确退回旧盈余（¥1,278.33），且目标仍不变
no_rb = variant(**{"fire.fulltime.room_and_board_covered": False})
data_no_rb = fire_mod.compute(no_rb, price=PRICE, btc=T.BTC, sp500=T.SP500, ndx100=T.NDX, history=[])
ok(
    "关掉包吃住后阶段 A 盈余退回 ¥1,278.33",
    abs(data_no_rb["fulltime"]["surplus_monthly_cny"] - 1278.33) < 0.05,
    str(data_no_rb["fulltime"]["surplus_monthly_cny"]),
)
ok("关掉包吃住后目标仍不变", abs(data_no_rb["fire"]["target_cny"] - 205953.49) < 0.01)
ok(
    "compute 的 fulltime 带 stage_a_monthly_expense 且≈¥556",
    abs(data["fulltime"]["stage_a_monthly_expense"] - 556) < 1.0,
    str(data["fulltime"]["stage_a_monthly_expense"]),
)
ok(
    "compute 的 fulltime 标记 room_and_board_covered",
    data["fulltime"]["room_and_board_covered"] is True,
)
ok(
    "包吃住后盈余 ≈ ¥2,183（净收入 ¥2,739 − 阶段 A ¥556），大于旧 ¥1,278",
    abs(data["fulltime"]["surplus_monthly_cny"] - 2183.33) < 1.0,
    str(data["fulltime"]["surplus_monthly_cny"]),
)
ok(
    "departure 完成度 = 资产 ÷ 下沿",
    abs(data["departure"]["progress_low"] - data["assets"]["total_cny"] / gate["low_cny"]) < 1e-9,
)
ft_proj = data["fulltime"].get("projection")
ok("全职外推存在", isinstance(ft_proj, dict))
ok(
    "全职外推的月投 > 主口径月投（盈余并入了定投）",
    ft_proj["monthly_cny"] > data["projection"]["monthly_cny"],
    f'{ft_proj["monthly_cny"]} vs {data["projection"]["monthly_cny"]}',
)
ok(
    "全职外推比主口径更早达标",
    ft_proj["days_to_target"] < data["projection"]["days_to_target"],
    f'{ft_proj["days_to_target"]} vs {data["projection"]["days_to_target"]}',
)

print("\n北京备选位置（§3.5.8）")
bj = data.get("fulltime_beijing")
ok("compute 带 fulltime_beijing（备选位置）", isinstance(bj, dict))
ok("北京备选不改变 FIRE 目标", abs(data["fire"]["target_cny"] - target) < 0.01)
ok(
    "北京备选阶段 A 个人开销也≈¥556（同 covered_keys 扣除）",
    abs(bj["stage_a_monthly_expense"] - 556) < 1.0,
    str(bj["stage_a_monthly_expense"]),
)
ok(
    "北京备选净收入 ≈ ¥3,456.67（¥20/h × 173.33h − 装备 ¥10）",
    abs(bj["net_monthly_cny"] - 3456.67) < 1.0,
    str(bj["net_monthly_cny"]),
)
ok(
    "北京备选盈余 ≈ ¥2,900.67（净 ¥3,456.67 − 阶段 A ¥556），高于牡丹江 ¥2,183",
    abs(bj["surplus_monthly_cny"] - 2900.67) < 1.0,
    str(bj["surplus_monthly_cny"]),
)
bj_proj = bj.get("projection")
ok("北京备选外推存在", isinstance(bj_proj, dict))
ok(
    "北京备选外推比牡丹江备选更早达标（攒钱更快）",
    bj_proj["days_to_target"] < ft_proj["days_to_target"],
    f'{bj_proj["days_to_target"]} vs {ft_proj["days_to_target"]}',
)

print("\n渲染降级")
svg = render_mod.dual_progress_svg(data, cfg)
ok("有 departure 时画出双线", isinstance(svg, str) and "出发门槛" in svg and "不工作门槛" in svg)
no_dep = dict(data)
no_dep.pop("departure")
ok("没有 departure 时返回 None（调用方退回单条）", render_mod.dual_progress_svg(no_dep, cfg) is None)

block = render_mod.render_block(data, cfg, [])
ok("README 出现两条门槛", "出发门槛" in block and "不工作门槛" in block)
ok("README 出现全职小节", "阶段 A 首选方案" in block)
ok("README 明说全职不改变目标", "全职**不改变**上面的 FIRE 目标" in block)
ok(
    "外推文案说「不工作门槛」而不是含糊的「目标」",
    "后达到**不工作门槛**" in block,
)
ok(
    "外推段给出全职的第二条外推",
    "阶段 A 若有全职收入" in block,
)
ok(
    "README 全职小节显示阶段 A 个人月开销（包吃住）",
    "阶段 A 个人月开销（包吃住" in block,
)
ok("README 出现北京备选小节", "阶段 A 备选方案" in block)
ok("北京备选小节标为 §3.5.8 备选道路", "§3.5.8" in block and "备选道路" in block)
ok("外推段给出北京备选的第二条外推", "备选：阶段 A 在北京做同等全职" in block)

no_ft = dict(data)
no_ft.pop("fulltime")
block2 = render_mod.render_block(no_ft, cfg, [])
ok("没有 fulltime 时不出空表", "阶段 A 首选方案" not in block2)

print("\n进度曲线：两条线")
HIST = [
    {"date": "2026-10-01", "total_cny": 10000.0, "progress_pct": 4.855, "target_cny": 205953.49},
    {"date": "2026-10-15", "total_cny": 12000.0, "progress_pct": 5.827, "target_cny": 205953.49},
    {"date": "2026-10-31", "total_cny": 19491.38, "progress_pct": 9.464, "target_cny": 205953.49},
]
two = render_mod.curve_svg(HIST, cfg, gate["low_cny"])
ok(
    "有 departure 时画出两条线",
    'class="line-dep"' in two and 'class="line-fire"' in two,
)
ok("两条线各有末端标注", two.count('r="3.5"') == 2, str(two.count('r="3.5"')))
ok(
    "出发门槛那条线更高（同样的资产 ÷ 更小的门槛）",
    f"{19491.38 / gate['low_cny'] * 100:.2f}%" in two,
    "末端百分比没出现",
)
one = render_mod.curve_svg(HIST, cfg)
ok(
    "不给 departure 时只画一条（向后兼容）",
    'class="line-dep"' not in one and 'class="line-fire"' in one,
)
ok(
    "历史里自带 departure_cny 时优先用它，不退回传参",
    'class="line-dep"' in render_mod.curve_svg(
        [{**r, "departure_cny": 80000.0} for r in HIST], cfg
    ),
)

print("\nhistory 逐日留档")
from scripts import update as update_mod  # noqa: E402

snap = update_mod.upsert_snapshot([], data)
ok("upsert_snapshot 写入 departure_cny", snap[0].get("departure_cny") == gate["low_cny"],
   str(snap[0].get("departure_cny")))
ok("upsert_snapshot 仍写 target_cny", snap[0].get("target_cny") == data["fire"]["target_cny"])

print("\n静态页卡片")
from scripts import site as site_mod  # noqa: E402
import tempfile  # noqa: E402

with tempfile.TemporaryDirectory() as tmp:
    html = site_mod.build_page(data, cfg, [snap[0]], Path(tmp))
# progress_low 是比率（0.2811），pct() 只格式化不乘 100 —— 曾经漏乘，
# 页面上显示成 0.28%。这里按「和 README 一致」钉死。
want_dep = f'{data["departure"]["progress_low"] * 100:.2f}%'
ok("静态页出发门槛完成度按百分数显示", f"<dd>{want_dep}</dd>" in html, want_dep)
ok("静态页不工作门槛完成度仍在", f'<dd>{data["assets"]["progress_pct"]:.2f}%</dd>' in html)
ok("静态页出现出发门槛卡片", "<dt>出发门槛</dt>" in html)

print()
if failures:
    print(f"失败 {len(failures)} 项：")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print(f"全部通过（出发门槛 ¥{gate['low_cny']:,.2f}–¥{gate['high_cny']:,.2f}，"
      f"全职净收入 ¥{ft['net_monthly_cny']:,.2f}，FIRE 目标 ¥{target:,.2f}）")
