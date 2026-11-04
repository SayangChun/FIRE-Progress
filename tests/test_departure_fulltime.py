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

print("\n全职净收入（北京起点）")
ft = lifeplan_mod.fulltime_income(cfg)
ok("开启时返回 dict", isinstance(ft, dict))
ok(
    "毛收入 = 周工时 × 52÷12 × 时薪",
    abs(ft["gross_monthly_cny"] - 40 * 52 / 12 * 20) < 0.02,
    str(ft["gross_monthly_cny"]),
)
ok(
    "净收入 = 毛收入 − 增量消耗",
    abs(ft["net_monthly_cny"] - (ft["gross_monthly_cny"] - ft["cost_monthly_cny"])) < 0.02,
    str(ft["net_monthly_cny"]),
)
ok("净收入约 ¥3,456.67", abs(ft["net_monthly_cny"] - 3456.67) < 0.05, str(ft["net_monthly_cny"]))
ok(
    "宿舍在馆内：餐食与交通增量均为 0",
    abs(ft["meal_cny"]) < 0.01 and abs(ft["transport_cny"]) < 0.01,
    f'{ft["meal_cny"]} / {ft["transport_cny"]}',
)
ok(
    "月占用 173.33 小时（坐岗无通勤）",
    abs(ft["occupied_hours_per_month"] - 40 * 52 / 12) < 0.5,
    str(ft["occupied_hours_per_month"]),
)

off_ft = variant(**{"fire.fulltime.enabled": False})
ok("关闭时返回 None", lifeplan_mod.fulltime_income(off_ft) is None)

print("\n全职盈余")
ok(
    "盈余 = 净收入 − 月开销（不是 − 净月开销）",
    abs((ft["net_monthly_cny"] - monthly) - 1995.67) < 0.05,
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
# 关掉包吃住后必须退回「自付全款」的盈余（北京：¥3,456.67 − ¥4,084 = −¥627.33），且目标仍不变
no_rb = variant(**{"fire.fulltime.room_and_board_covered": False})
data_no_rb = fire_mod.compute(no_rb, price=PRICE, btc=T.BTC, sp500=T.SP500, ndx100=T.NDX, history=[])
ok(
    "关掉包吃住后阶段 A 盈余退回 −¥627.33（北京自付全款）",
    # 不包吃住时用「岗位所在城市」的完整月开销（北京 ¥4,084），
    # 不是当前激活 profile 的牡丹江 ¥1,461。
    abs(data_no_rb["fulltime"]["surplus_monthly_cny"] - (-627.33)) < 0.05,
    str(data_no_rb["fulltime"]["surplus_monthly_cny"]),
)
ok("关掉包吃住后目标仍不变", abs(data_no_rb["fire"]["target_cny"] - 205953.49) < 0.01)
ok(
    "compute 的 fulltime 阶段 A 开销按北京 profile 算 ≈¥569（不是牡丹江 ¥556）",
    abs(data["fulltime"]["stage_a_monthly_expense"] - 569) < 1.0,
    str(data["fulltime"]["stage_a_monthly_expense"]),
)
ok(
    "compute 的 fulltime 标记 room_and_board_covered",
    data["fulltime"]["room_and_board_covered"] is True,
)
ok(
    "包吃住后盈余 ≈ ¥2,887.67（净 ¥3,456.67 − 北京阶段 A ¥569）",
    abs(data["fulltime"]["surplus_monthly_cny"] - 2887.67) < 1.0,
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

print("\n牡丹江备选城市")
mdj = data.get("fulltime_mudanjiang")
ok("compute 带 fulltime_mudanjiang（备选城市）", isinstance(mdj, dict))
ok("牡丹江备选不改变 FIRE 目标", abs(data["fire"]["target_cny"] - target) < 0.01)
ok(
    "牡丹江备选阶段 A 个人开销也≈¥556（同 covered_keys 扣除）",
    abs(mdj["stage_a_monthly_expense"] - 556) < 1.0,
    str(mdj["stage_a_monthly_expense"]),
)
ok(
    "牡丹江备选净收入 ≈ ¥2,739.33（¥17/h × 173.33h − 通勤 ¥43.33 − 餐食 ¥154 − 装备 ¥10）",
    abs(mdj["net_monthly_cny"] - 2739.33) < 1.0,
    str(mdj["net_monthly_cny"]),
)
ok(
    "牡丹江备选盈余 ≈ ¥2,183.33（净 ¥2,739.33 − 阶段 A ¥556），低于北京 ¥2,900.67",
    abs(mdj["surplus_monthly_cny"] - 2183.33) < 1.0,
    str(mdj["surplus_monthly_cny"]),
)
mdj_proj = mdj.get("projection")
ok("牡丹江备选外推存在", isinstance(mdj_proj, dict))
ok(
    "北京起点外推比牡丹江备选更早达标（攒钱更快）",
    ft_proj["days_to_target"] < mdj_proj["days_to_target"],
    f'{ft_proj["days_to_target"]} vs {mdj_proj["days_to_target"]}',
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
ok("README 出现牡丹江备选小节", "阶段 A 备选城市" in block)
ok("牡丹江备选小节标为备选城市", "备选城市" in block and "牡丹江" in block)
ok("外推段给出牡丹江备选的第二条外推", "备选城市：牡丹江图书馆保安" in block)

print("\n城市切换：月开销随 profile，目标随 target_profile")
cfg_bj = cfgmod.load()
cfg_bj["life_plan"]["profile"] = "beijing-rent-minimal"
data_bj = fire_mod.compute(cfg_bj, price=PRICE, btc=T.BTC, sp500=T.SP500, ndx100=T.NDX, history=[])
tgt_bj = data_bj["fire"]["target_cny"]
ok(
    "切到北京 profile 后月开销 = ¥4,084（阶段 A 与门槛用）",
    abs(data_bj["fire"]["monthly_expense"] - 4084) < 1.0,
    str(data_bj["fire"]["monthly_expense"]),
)
# 核心：换城市不能把进度条分母一起拖走。target_profile 钉在牡丹江。
ok(
    "切到北京 profile 后目标仍钉在牡丹江口径 ¥205,953.49",
    abs(tgt_bj - 205953.49) < 0.01,
    str(tgt_bj),
)
ok(
    "life_plan 摘要标出 target_profile = mudanjiang-rent-minimal",
    (data_bj.get("life_plan") or {}).get("target_profile") == "mudanjiang-rent-minimal",
    str((data_bj.get("life_plan") or {}).get("target_profile")),
)
# 目标公式必须用 target_profile 的净支出反算得回来；
# 若误用当前城市的 net_monthly_expense（北京 ¥3,361），公式与结果会对不上。
_f = data_bj["fire"]
ok(
    "切到北京 profile 时目标公式仍自洽（base = ¥738，不是 ¥3,361）",
    abs(_f["target_net_monthly_expense"] * 12 / _f["withdrawal_rate"] - _f["target_cny"]) < 0.01,
    f'base {_f.get("target_net_monthly_expense")} vs net {_f.get("net_monthly_expense")}',
)
ok(
    "北京 profile 下 target_net_monthly_expense 与 net_monthly_expense 确实不同",
    abs(_f["target_net_monthly_expense"] - _f["net_monthly_expense"]) > 1.0,
    f'{_f["target_net_monthly_expense"]} vs {_f["net_monthly_expense"]}',
)
ok(
    "切到北京 profile 不污染牡丹江目标",
    abs(data["fire"]["target_cny"] - target) < 0.01,
)
# 想看「独自在北京不工作」的参考值，必须同时把 target_profile 也切过去。
cfg_bj_ref = cfgmod.load()
cfg_bj_ref["life_plan"]["profile"] = "beijing-rent-minimal"
cfg_bj_ref["life_plan"]["target_profile"] = "beijing-rent-minimal"
data_bj_ref = fire_mod.compute(
    cfg_bj_ref, price=PRICE, btc=T.BTC, sp500=T.SP500, ndx100=T.NDX, history=[]
)
tgt_bj_ref = data_bj_ref["fire"]["target_cny"]
ok(
    "显式切 target_profile 时，北京独自不工作参考目标 ≈ ¥937,953",
    abs(tgt_bj_ref - 937953.49) < 5.0,
    str(tgt_bj_ref),
)
# 岗位块必须按「岗位所在城市」算阶段 A 开销，不随激活 profile 变。
# 否则同一个北京岗的盈余会在 ¥2,901 与 ¥2,888 之间无故跳动。
ok(
    "切激活 profile 后，北京块盈余不变（仍 ¥2,887.67）",
    abs(data_bj["fulltime"]["surplus_monthly_cny"] - data["fulltime"]["surplus_monthly_cny"]) < 0.01
    and abs(data_bj["fulltime"]["surplus_monthly_cny"] - 2887.67) < 1.0,
    f'{data_bj["fulltime"]["surplus_monthly_cny"]} vs {data["fulltime"]["surplus_monthly_cny"]}',
)
ok(
    "切激活 profile 后，牡丹江块盈余不变（仍 ¥2,183.33）",
    abs(
        data_bj["fulltime_mudanjiang"]["surplus_monthly_cny"]
        - data["fulltime_mudanjiang"]["surplus_monthly_cny"]
    )
    < 0.01
    and abs(data_bj["fulltime_mudanjiang"]["surplus_monthly_cny"] - 2183.33) < 1.0,
)
# 出发门槛用当前 profile 的月开销算空窗期，所以换城市会改变门槛。
# 北京月开销 ¥4,084 → 空窗 3–6 月 ¥12,252–24,504 → 门槛 ¥77,252–139,504。
gate_bj = data_bj.get("departure") or {}
ok(
    "切到北京 profile 出发门槛更高（空窗期按北京月开销）",
    gate_bj.get("low_cny", 0) > gate["low_cny"],
    f'{gate_bj.get("low_cny")} vs {gate["low_cny"]}',
)
ok(
    "北京出发门槛 ≈ ¥77,252–139,504（引擎实算）",
    abs(gate_bj.get("low_cny", 0) - 77252) < 1 and abs(gate_bj.get("high_cny", 0) - 139504) < 1,
    f'{gate_bj.get("low_cny")} – {gate_bj.get("high_cny")}',
)
# 北京兼职是负的：¥723 − ¥4,084 = −¥3,361。这条钉死「兜底链不能只写退回兼职」。
ok(
    "北京兼职盈余为负（−¥3,361），说明兜底必须换城市",
    abs(
        lifeplan_mod.labor_income(cfg_bj)["net_monthly_cny"]
        - lifeplan_mod.monthly_total(cfg_bj)
        + 3361
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
