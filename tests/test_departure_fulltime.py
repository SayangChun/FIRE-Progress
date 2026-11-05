"""「出发门槛」与「全职情景」的回归测试（2026-10-31 新增，2026-11-05 改口径）。

这两段都不是口径的微调，是**计划结构变了**：

    旧：攒够 ¥205,953 再出发（阶段 A 靠兼职 + 消耗本金）
    新：毕业后就出发，阶段 A 有工作（牡丹江图书馆保安，独自租房）

⚠️ 2026-11-05 他明确：只去牡丹江 FIRE、排除北京，且要一个人租房住、
不接受包吃住。所以全职只有一个变体（牡丹江、¥17/h、阶段 A 开销 ¥1,461），
出发门槛里的搬家费恢复为「押金 ¥1,000 + 运输 ¥800」= ¥1,800。

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
ok(
    "搬家费 = 押金 ¥1,000 + 运输 ¥800（独自租房，家具不恢复）",
    abs(gate["moving_cny"] - 1800) < 0.01,
    str(gate["moving_cny"]),
)
ok("空窗期按当前月开销折算", abs(gate["gap_low_cny"] - monthly * 3) < 0.01, str(gate["gap_low_cny"]))
ok("下沿落在 ¥5–6 万区间", 50000 < gate["low_cny"] < 60000, str(gate["low_cny"]))

off_gate = variant(**{"departure.enabled": False})
ok("关闭时返回 None", lifeplan_mod.departure_gate(off_gate) is None)

print("\n全职净收入（牡丹江，独自租房）")
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
ok("净收入约 ¥2,739.33", abs(ft["net_monthly_cny"] - 2739.33) < 0.05, str(ft["net_monthly_cny"]))
ok(
    "独自租房：通勤 ¥43.33 + 餐食 ¥154 + 装备 ¥10",
    abs(ft["transport_cny"] - 43.33) < 0.05
    and abs(ft["meal_cny"] - 154) < 0.01
    and abs(ft["gear_cny"] - 10) < 0.01,
    f'{ft["transport_cny"]} / {ft["meal_cny"]} / {ft["gear_cny"]}',
)
ok(
    "月占用 195 小时（40h 工作 + 5h 通勤）",
    abs(ft["occupied_hours_per_month"] - 195) < 0.5,
    str(ft["occupied_hours_per_month"]),
)

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

print("\n包吃住：monthly_excluding() 仍可用（当前配置不启用）")
# 2026-11-05 起他明确不接受包吃住（要一个人租房住），配置里已没有 covered_keys。
# 这里直接给一份覆盖清单，验证函数本身没坏——将来岗位形态若再变可复用。
covered = ["rent", "heating", "property_fee", "food", "drinking_water"]
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
ok(
    "当前配置不启用包吃住（room_and_board_covered = false）",
    cfg["fire"]["fulltime"].get("room_and_board_covered") is False,
    str(cfg["fire"]["fulltime"].get("room_and_board_covered")),
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

print("\n主进度开关（display.primary_progress）")
# 主进度只改展示位排序与标记，三个门槛的金额和完成度一律不变。
for key in ("departure", "coffee_fire", "full_fire"):
    alt_cfg = variant(**{"display.primary_progress": key})
    alt = fire_mod.compute(alt_cfg, price=PRICE, btc=T.BTC, sp500=T.SP500, ndx100=T.NDX, history=[])
    items = (alt.get("goals") or {}).get("items") or []
    ok(
        f"主进度设为 {key} 时排在第一位",
        alt["goals"]["primary"] == key and bool(items) and items[0]["key"] == key and items[0]["is_primary"],
    )
    ok(
        f"主进度设为 {key} 时三个门槛金额不变",
        {g["key"]: g["target_cny"] for g in items} == {g["key"]: g["target_cny"] for g in data["goals"]["items"]},
    )
    ok(
        f"主进度设为 {key} 时 FIRE 目标与完成度不变",
        abs(alt["fire"]["target_cny"] - data["fire"]["target_cny"]) < 0.01
        and abs(alt["assets"]["progress_pct"] - data["assets"]["progress_pct"]) < 0.0001,
    )
bad_cfg = variant(**{"display.primary_progress": "not_a_goal"})
try:
    fire_mod.compute(bad_cfg, price=PRICE, btc=T.BTC, sp500=T.SP500, ndx100=T.NDX, history=[])
    ok("主进度写错名字必须报错，不静默回落", False, "没有报错")
except ValueError:
    ok("主进度写错名字必须报错，不静默回落", True)
ok("compute 的目标未被全职影响", abs(data["fire"]["target_cny"] - target) < 0.01)
ok(
    "compute 的 fulltime 阶段 A 开销 = 完整月开销 ¥1,461（独自租房）",
    abs(data["fulltime"]["stage_a_monthly_expense"] - 1461) < 1.0,
    str(data["fulltime"]["stage_a_monthly_expense"]),
)
ok(
    "compute 的 fulltime 标记 room_and_board_covered = False",
    data["fulltime"]["room_and_board_covered"] is False,
)
ok(
    "独自租房盈余 ≈ ¥1,278.33（净 ¥2,739.33 − 月开销 ¥1,461）",
    abs(data["fulltime"]["surplus_monthly_cny"] - 1278.33) < 1.0,
    str(data["fulltime"]["surplus_monthly_cny"]),
)
# 反向验证：把包吃住打开，盈余应升到 ¥2,183.33（¥2,739.33 − ¥556），目标仍不变。
rb = variant(**{
    "fire.fulltime.room_and_board_covered": True,
    "fire.fulltime.covered_keys": covered,
})
data_rb = fire_mod.compute(rb, price=PRICE, btc=T.BTC, sp500=T.SP500, ndx100=T.NDX, history=[])
ok(
    "打开包吃住后盈余回到 ¥2,183.33（仅作反向验证，非当前方案）",
    abs(data_rb["fulltime"]["surplus_monthly_cny"] - 2183.33) < 1.0,
    str(data_rb["fulltime"]["surplus_monthly_cny"]),
)
ok("打开包吃住后目标仍不变", abs(data_rb["fire"]["target_cny"] - 205953.49) < 0.01)
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

print("\n备选变体已移除")
ok(
    "配置里只剩 fulltime 一个变体，fulltime_mudanjiang 为 None",
    data.get("fulltime_mudanjiang") is None,
    str(data.get("fulltime_mudanjiang")),
)
ok("备选变体不改变 FIRE 目标", abs(data["fire"]["target_cny"] - target) < 0.01)

print("\n三级门槛与主进度")
svg = render_mod.dual_progress_svg(data, cfg)
ok(
    "进度条画出三条门槛",
    isinstance(svg, str)
    and all(k in svg for k in ("出发门槛", "咖啡师 FIRE", "完全 FIRE")),
)
ok("进度条标出主进度", isinstance(svg, str) and "主进度" in svg)
# 主进度由 display.primary_progress 决定，默认出发门槛。
ok("主进度是出发门槛", (data.get("goals") or {}).get("primary") == "departure")
goals = (data.get("goals") or {}).get("items") or []
ok("goals 有三条且主进度排第一", len(goals) == 3 and goals[0]["is_primary"])
by_key = {g["key"]: g for g in goals}
ok(
    "完全 FIRE 门槛 = 全额月开销 × 12 ÷ 提取率",
    abs(by_key["full_fire"]["target_cny"] - 1461 * 12 / 0.043) < 0.01,
    str(by_key["full_fire"]["target_cny"]),
)
ok(
    "完全 FIRE 门槛 > 咖啡师 FIRE 门槛 > 出发门槛",
    by_key["full_fire"]["target_cny"] > by_key["coffee_fire"]["target_cny"] > by_key["departure"]["target_cny"],
)
ok(
    "完全 FIRE 完成度 < 咖啡师 FIRE 完成度",
    by_key["full_fire"]["progress_pct"] < by_key["coffee_fire"]["progress_pct"],
)
ok(
    "完全 FIRE 门槛不依赖兼职收入（与 coffee 差 = 兼职 × 12 ÷ 提取率）",
    abs(
        (by_key["full_fire"]["target_cny"] - by_key["coffee_fire"]["target_cny"])
        - 723 * 12 / 0.043
    ) < 0.01,
)
no_goals = dict(data)
no_goals.pop("goals")
ok("没有 goals 时返回 None（调用方退回单条）", render_mod.dual_progress_svg(no_goals, cfg) is None)

block = render_mod.render_block(data, cfg, [])
ok("README 出现三级门槛", all(k in block for k in ("出发门槛", "咖啡师 FIRE", "完全 FIRE")))
ok("README 标出主进度", "主进度" in block)
ok("README 出现全职小节", "阶段 A 首选方案" in block)
ok("README 明说全职不改变目标", "全职**不改变** FIRE 目标" in block)
ok(
    "外推文案说「咖啡师 FIRE 门槛」而不是含糊的「不工作门槛」",
    "后达到**咖啡师 FIRE 门槛**" in block,
)
ok(
    "外推段给出全职的第二条外推",
    "阶段 A 若有全职收入" in block,
)
# 断言绑在「小节里有没有这个数」上，而不是某一行长什么样——
# 2026-11-05 把表格压成一句话时，这条曾经因为格式变了而误报失败。
ft_section = block.split("阶段 A 首选方案", 1)[1].split("</details>", 1)[0]
ok(
    "README 全职小节显示完整月开销（不包吃住）",
    "月开销 ¥1,461.00" in ft_section and "包吃住" not in ft_section,
)
ok("README 不再出现「备选城市」小节", "阶段 A 备选城市" not in block)

print("\n档位切换：月开销随 profile，目标随 target_profile")
# 2026-11-05 起北京已排除，用牡丹江常规档验证同一不变量：
# 临时试算「放宽到常规生活」时，月开销与门槛会变，但进度条分母不能跟着变。
cfg_normal = cfgmod.load()
cfg_normal["life_plan"]["profile"] = "mudanjiang-rent-normal"
data_normal = fire_mod.compute(
    cfg_normal, price=PRICE, btc=T.BTC, sp500=T.SP500, ndx100=T.NDX, history=[]
)
tgt_normal = data_normal["fire"]["target_cny"]
ok(
    "切到常规档后月开销 = ¥2,754（阶段 A 与门槛用）",
    abs(data_normal["fire"]["monthly_expense"] - 2754) < 1.0,
    str(data_normal["fire"]["monthly_expense"]),
)
ok(
    "切到常规档后目标仍钉在极简档 ¥205,953.49",
    abs(tgt_normal - 205953.49) < 0.01,
    str(tgt_normal),
)
ok(
    "life_plan 摘要标出 target_profile = mudanjiang-rent-minimal",
    (data_normal.get("life_plan") or {}).get("target_profile") == "mudanjiang-rent-minimal",
    str((data_normal.get("life_plan") or {}).get("target_profile")),
)
# 目标公式必须用 target_profile 的净支出反算得回来；
# 若误用当前档位的 net_monthly_expense（常规档 ¥2,031），公式与结果会对不上。
_f = data_normal["fire"]
ok(
    "切到常规档时目标公式仍自洽（base = ¥738，不是 ¥2,031）",
    abs(_f["target_net_monthly_expense"] * 12 / _f["withdrawal_rate"] - _f["target_cny"]) < 0.01,
    f'base {_f.get("target_net_monthly_expense")} vs net {_f.get("net_monthly_expense")}',
)
ok(
    "常规档下 target_net_monthly_expense 与 net_monthly_expense 确实不同",
    abs(_f["target_net_monthly_expense"] - _f["net_monthly_expense"]) > 1.0,
    f'{_f["target_net_monthly_expense"]} vs {_f["net_monthly_expense"]}',
)
ok(
    "切到常规档不污染极简档目标",
    abs(data["fire"]["target_cny"] - target) < 0.01,
)
# 岗位块必须按「岗位所在城市」算阶段 A 开销，不随激活 profile 变。
ok(
    "切激活 profile 后，fulltime 盈余不变（仍 ¥1,278.33）",
    abs(data_normal["fulltime"]["surplus_monthly_cny"] - data["fulltime"]["surplus_monthly_cny"]) < 0.01
    and abs(data_normal["fulltime"]["surplus_monthly_cny"] - 1278.33) < 1.0,
    f'{data_normal["fulltime"]["surplus_monthly_cny"]} vs {data["fulltime"]["surplus_monthly_cny"]}',
)
# 出发门槛用当前 profile 的月开销算空窗期，所以换档位会改变门槛。
# 常规档月开销 ¥2,754 → 空窗 3–6 月 ¥8,262–16,524 → 门槛 ¥60,062–118,324（搬家费同为 ¥1,800）。
gate_normal = data_normal.get("departure") or {}
ok(
    "切到常规档出发门槛更高（空窗期按 ¥2,754 算）",
    gate_normal.get("low_cny", 0) > gate["low_cny"],
    f'{gate_normal.get("low_cny")} vs {gate["low_cny"]}',
)
ok(
    "常规档出发门槛 ≈ ¥60,062–118,324（引擎实算）",
    abs(gate_normal.get("low_cny", 0) - 60062) < 1 and abs(gate_normal.get("high_cny", 0) - 118324) < 1,
    f'{gate_normal.get("low_cny")} – {gate_normal.get("high_cny")}',
)
# 常规档兼职是负的：¥723 − ¥2,754 = −¥2,031。这条钉死「兜底必须按极简档」。
ok(
    "常规档兼职盈余为负（−¥2,031），说明兜底必须按极简档",
    abs(
        lifeplan_mod.labor_income(cfg_normal)["net_monthly_cny"]
        - lifeplan_mod.monthly_total(cfg_normal)
        + 2031
    )
    < 1.0,
)

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
three = render_mod.curve_svg(HIST, cfg, gate["low_cny"], 1461 * 12 / 0.043)
ok(
    "给完全 FIRE 门槛时画出第三条线",
    'class="line-full"' in three and 'class="line-dep"' in three and 'class="line-fire"' in three,
)
ok("三条线各有末端标注", three.count('r="3.5"') == 3, str(three.count('r="3.5"')))

print("\nhistory 逐日留档")
from scripts import update as update_mod  # noqa: E402

snap = update_mod.upsert_snapshot([], data)
ok("upsert_snapshot 写入 departure_cny", snap[0].get("departure_cny") == gate["low_cny"],
   str(snap[0].get("departure_cny")))
ok("upsert_snapshot 仍写 target_cny", snap[0].get("target_cny") == data["fire"]["target_cny"])
ok(
    "upsert_snapshot 写入 full_fire_cny（完全 FIRE 逐日留档）",
    snap[0].get("full_fire_cny") == data["full_fire"]["target_cny"],
    str(snap[0].get("full_fire_cny")),
)

print("\n静态页卡片")
from scripts import site as site_mod  # noqa: E402
import tempfile  # noqa: E402

with tempfile.TemporaryDirectory() as tmp:
    html = site_mod.build_page(data, cfg, [snap[0]], Path(tmp))
# progress_low 是比率（0.2811），pct() 只格式化不乘 100 —— 曾经漏乘，
# 页面上显示成 0.28%。这里按「和 README 一致」钉死。
want_dep = f'{data["departure"]["progress_low"] * 100:.2f}%'
ok("静态页出发门槛完成度按百分数显示", f"<dd>{want_dep}</dd>" in html, want_dep)
ok("静态页咖啡师 FIRE 完成度仍在", f'<dd>{data["assets"]["progress_pct"]:.2f}%</dd>' in html)
ok("静态页出现三级门槛", all(k in html for k in ("出发门槛", "咖啡师 FIRE", "完全 FIRE")))
ok("静态页标出主进度", "★" in html)
ok(
    "静态页完全 FIRE 完成度出现",
    f'<dd>{data["full_fire"]["progress_pct"]:.2f}%</dd>' in html,
)

print()
if failures:
    print(f"失败 {len(failures)} 项：")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print(f"全部通过（出发门槛 ¥{gate['low_cny']:,.2f}–¥{gate['high_cny']:,.2f}，"
      f"全职净收入 ¥{ft['net_monthly_cny']:,.2f}，FIRE 目标 ¥{target:,.2f}）")
