# FIRE-Progress 实现方案

本文档回答四件事：**数据从哪来**、**怎么算**、**怎么自动跑**、**README 展示什么**。
所有口径与代码一一对应，改口径只改 `config.yaml`。

---

## 0. 结论速览

| 项 | 结论 |
| --- | --- |
| FIRE 目标资产 | **¥204,000.00**（731.00 × 12 ÷ 4.3%） |
| FIRE 类型 | **咖啡师 FIRE** —— 兼职净收入先抵扣月开销，资产只覆盖剩余部分 |
| 月开销来源 | `config.yaml` 的 `life_plan` 段逐项推导（不再硬编码） |
| 当前资产 | 比特币市值 + 标普500基金市值 |
| 比特币持仓 | 读取 [SayangChun/0.1BTC](https://github.com/SayangChun/0.1BTC) 的 `data/holdings.csv`（**每周手动更新**） |
| 标普500持仓 | 读取 [SayangChun/sp500-dca](https://github.com/SayangChun/sp500-dca) 的 `data/portfolio.json` |
| 估值行情 | BTC/USDT 现货价 × USD/CNY 汇率，全部折算为人民币 |
| 运行位置 | **GitHub Actions** |
| 密钥 | **完全不需要** —— 两个数据源都是公开仓库，行情走公开接口 |
| 展示 | README 自动生成区块 + 进度条 SVG + 进度曲线 SVG + 资产构成 + 月开销明细 + 收益曲线 SVG + 每小时被动收入 |
| 生活规划 | [FIRE-LIFE-PLAN.md](FIRE-LIFE-PLAN.md)（城市/住房/饮食/医疗） |


---

## 1. 目标与口径

### 1.1 计算规则（唯一权威定义）

```
月开销     = Σ life_plan.profiles[profile].items[].monthly      （逐项相加，见 §1.2）
兼职净收入 = 毛收入 − 工作增量消耗                                （见 §1.3，可为 0）
组合需覆盖 = 月开销 − 兼职净收入
           = 1664 − 723.00
           = 731.00 元/月

FIRE 目标资产 = 组合需覆盖 × 12 ÷ 提取率
             = 731.00 × 12 ÷ 0.043
             = 204,000.00 元

当前资产     = 比特币市值 + 标普500基金市值 + 纳指100基金市值
完成度       = 当前资产 ÷ FIRE 目标资产
距离目标     = FIRE 目标资产 − 当前资产
```

> 兼职净收入为 0（`fire.labor_income.enabled = false`）时，公式退化为
> 传统 FIRE 的「月开销 × 12 ÷ 提取率」，两种口径共用同一套代码。
>
> 若 `fire.monthly_expense` 填了数字，则以该值为准（用于临时试算），
> 结果里标记 `override=true`，README 会标注「手工覆盖值」。
> 正式口径应保持 `null`，即完全由逐项预算推导。

### 1.1.1 两段式：另一个口径（不参与目标计算）

上面的公式是**永续**口径——假设兼职一直做下去、资产永不耗尽。实际计划是两段式的
（阶段 A 云南省内独立期 → 阶段 B 北京家庭期，见 [FIRE-ROADMAP.md](FIRE-ROADMAP.md)），
阶段 A 有明确退出条件，因此不需要永续。`fire.py` 另有一组纯函数回答「这笔钱够撑多久」：

```
年净支出   = 组合需覆盖 × 12
永续线 k   = 年净支出 ÷ 实际收益率
可支撑年数 = ln(k / (k − P)) / ln(1 + r)      P < k 时有效
永续条件   = P ≥ k
临界收益率 = 年净支出 ÷ P
```

| 函数 | 作用 |
| --- | --- |
| `capital_for_years(exp, years, rate)` | 年金现值：给定年数，需要多少本金 |
| `years_from_capital(cap, exp, rate)` | 反向：给定本金能撑多少年（`None` = 永续） |
| `critical_rate(exp, cap)` | 永续所需的最低实际收益率 |
| `two_phase(cfg, capital, annual_net_expense)` | 打包成 `compute()` 的 `two_phase` 字段 |
| `allocation_split(cfg, btc, sp500)` | 比特币 / 标普500 占比，**只做展示** |

> ⚠️ **这些函数绝不参与 `target_cny` 的计算。**
> `tests/test_two_phase.py` 钉死了一条：资产扩大 100 倍，目标必须一动不动，
> 而 `two_phase.years` 必须跟着变。
>
> 之所以要这样分开，是因为两者回答的问题不同：
> 目标公式 → 「还要攒多少」（进度条）；两段式 → 「这笔钱够撑多久」（决策）。

### 1.1b 全职情景与出发门槛

阶段 A 是全职工作（任一符合判据的轻松岗都算），
多了两个函数，**同样都不参与 `target_cny`**：

| 函数 | 作用 | 为什么不进目标 |
| --- | --- | --- |
| `lifeplan.fulltime_income(cfg, key)` | 全职净收入。`key="fulltime"` 读省内口径（净 **¥2,739.33**，独自租房、不包吃住） | 净收入 > 月开销，代进公式得 **负数**。负数不是「超额完成」，是公式在这里没有答案——它算的是「资产要多大才能替代工资」，而全职本身就有工资 |
| `lifeplan.departure_gate(cfg)` | 出发门槛 = 医疗应急 + 空窗期月开销（不含一次性支出） | 它回答「能不能走」，与「能不能不工作」是两个问题，混进同一个百分比会两边都读错 |

```
出发门槛 low  = 医疗应急 low  + 月开销 × 空窗月数 low      # 不含搬家/押金等一次性支出
出发门槛 high = 医疗应急 high + 月开销 × 空窗月数 high    # include_one_off=false 时 moving=0
全职盈余      = 全职净收入 − 阶段 A 个人开销   # 不包吃住，= 完整月开销 ¥1,454
```

> ⚠️ 当前只有一个省内口径变体：¥17/h、通勤 ¥2/日、餐补 ¥154/月，
> 净收入 **¥2,739.33**；`room_and_board_covered: false`，阶段 A 开销 = 完整 **¥1,454**，
> 盈余 **¥1,285.33**。`fire.fulltime` 显式写 `life_plan_profile: mudanjiang-rent-minimal`，
> 阶段 A 开销按「岗位所在城市」算，不随当前激活 profile 变。
>
> 备选路径：`monthly_excluding()` 保留「包吃住扣覆盖项」的计算能力，
> 当前配置 `room_and_board_covered: false`，不触发。

**`profile` 与 `target_profile` 的分工**

| 配置项 | 决定什么 | 影响 |
| --- | --- | --- |
| `life_plan.profile` | 阶段 A 在哪个城市 | 月开销、阶段 A 个人开销、出发门槛 |
| `life_plan.target_profile` | 两个 FIRE 门槛按哪个城市算 | `target_cny` / `full_fire_target_cny`、进度条分母 |

默认 `target_profile = profile`。阶段 A 只落在云南省内，
两者正常情况下一致；但这个字段仍然**显式钉在 yunnan-rent-minimal 档**，原因是：
临时切到常规档（`mudanjiang-rent-normal`，¥2,754）试算时，月开销会用于
出发门槛与阶段 A 盈余，但进度条分母不能被试算值一起拖走。若不拆开，
目标会从 ¥204,000.00 跳到 ¥566,791——那个数不是目标，
是「常规档不工作」的假设值。

代码落点：`lifeplan.target_profile_name()`；`summary()` 同时返回
`net_monthly_expense`（当前城市）与 `target_net_monthly_expense`（基准城市），
`fire.compute()` 用后者算 `target_cny`。

> ⚠️ **`_net_after_labor` 仍然只读 `labor_income`（兼职兜底）。**
> 一旦有人把 `fulltime_income()` 的结果传进去，目标会变成负数并静默通过所有下游计算，
> 看板上完全看不出来。`tests/test_departure_fulltime.py` 钉死了这一条：
> 「把全职塞进 `_net_after_labor` 必须报错」。
>
> 全职只影响「多久到」，不影响「到多少」：`compute()` 用同一份资产、同一个
> `projection()`，只把盈余并进 `contribution.sp500_cny_per_day`，算出第二条外推。
>
> README 的进度条由 `render.dual_progress_svg()` 生成；没有 `departure` 字段时返回 `None`，
> 调用方退回 `progress_svg()` 单条，展示行为与单线进度条一致。

### 1.2 月开销从哪来（life_plan）

「月开销」是整个模型里最主观的输入，直接决定 FIRE 目标，因此**不写成常量**，
而是放在 `config.yaml` 的 `life_plan` 段里逐项列出，每项都标注依据：

```yaml
life_plan:
  profile: hegang-rent-minimal
  profiles:
    hegang-rent-minimal:
      items:
        - {key: rent, group: 住房与水电燃气, label: 房租, monthly: 520, note: "..."}
        - {key: heating, ..., monthly: 100, note: "¥27.5/㎡ × 87% 计费面积 × 50㎡ ÷ 12"}
```

口径：

| 规则 | 说明 |
| --- | --- |
| 只统计 FIRE 后的经常性支出 | 不是当前的生活成本 |
| **一次性支出不进月开销** | 搬家、押金、家具、购房款不产生永续现金流，摊进「组合需覆盖 × 12 ÷ 提取率」会**同时虚增月开销与目标**。它们单列在 `life_plan.one_off`，用「目标 + 一次性支出」另算 |
| 逐项标注依据 | 凡估算值一律写明「估算」 |
| 方案可切换 | 改 `profile` 一行即可；方案名写错会**直接报错**，不静默回落 |

详细的生活规划（城市选择、住房、饮食、医疗保障、敏感性分析）见
[FIRE-LIFE-PLAN.md](FIRE-LIFE-PLAN.md)。

**为什么不做「静默回落」**：月开销是 FIRE 目标的分母来源。
如果 `profile` 写错却悄悄取了个默认值，目标会跑偏而看板上完全看不出来——
报错比错数安全。

### 1.3 兼职净收入（咖啡师 FIRE）

口径在 `config.yaml` 的 `fire.labor_income` 段，由 `scripts/lifeplan.py` 的
`labor_income()` 计算。它只影响目标的分母，不参与资产侧任何计算。

```yaml
labor_income:
  enabled: true
  hourly_wage: 15          # 保守值，刻意取低
  hours_per_week: 12       # 每周 3 天 × 4 小时
  work_days_per_week: 3
  transport_per_day: 2.0   # 公交往返
  commute_hours_per_day: 1.0
  meal_increment_monthly: 25.0
  gear_monthly: 6.0
```

| 规则 | 说明 |
| --- | --- |
| **月工时按 52 周 ÷ 12** | 不按「每月 4 周」，后者会少算约 8% |
| **只扣工作增量消耗** | 交通、在外吃饭的**差额**、装备摊销。餐食按全价扣等于把生活费算两遍 |
| **交通按天数算** | 跟 `work_days_per_week` 走，不跟工时走（每天 8 小时但天数不变 → 交通不变） |
| **净收入 ≤ 0 直接报错** | 这份工在财务上是倒贴的，不该静默算出 0 |
| **净收入 ≥ 月开销直接报错** | 那意味着不用攒钱就能 FIRE，实务上一定是时薪或工时填错 |
| **缺字段直接报错** | `enabled: true` 时不能省略任何必填项，否则净收入会静默算成 0 |

等效时薪（含通勤）只用于展示、不参与目标计算——它说明「名义净时薪 ¥13.90 的
真实代价是 ¥11.12」，因为通勤占掉了 20% 的时间却不产生任何收入。

⚠️ **工时不确定**：3 天/周只是当前假设（他明确说过排班不确定）。每增减一天（4h），
目标变动约 ¥70,140——比时薪更敏感。2 / 3 / 4 天对应 ¥276,093 / ¥204,000.00 / ¥135,814，
见规划书 §7.4。

回归测试见 `tests/test_labor_income.py`。

### 1.4 计入范围

| 计入 | 不计入 |
| --- | --- |
| `0.1BTC` 仓库中的比特币持仓 | 法币、其他币种 |
| `sp500-dca` 仓库中的标普500基金市值 | 其他一切资产 |
| 纳指100 场外基金（份额在 `config.yaml`，净值抓东方财富） | |

三项资产等权处理，不设侧重。**纳入标准是「长期不动用」，不是「能不能变现」**——
日常现金要参与周转，所以不计入。这条标准决定了卖出后变成现金时进度会下跌，
那不是资产减少，是口径边界（见 README 的「计入范围」）。

---

## 2. 数据来源

### 2.1 比特币持仓 · 0.1BTC 仓库

**仓库**：`SayangChun/0.1BTC` · **文件**：`data/holdings.csv`

CSV 格式：

```csv
date,location,btc,note
2026-09-20,binance,0.00785078,"Binance账户；均价 $68,163.56/BTC"
2026-09-20,okx,0.0152673,"OKX账户；均价 $68,158.3/BTC"
```

| 字段 | 说明 |
| --- | --- |
| `date` | 快照日期 `YYYY-MM-DD` |
| `location` | `binance` / `okx` / `hot` / `other`（历史数据里还有 `cold` / `exchange`） |
| `btc` | 该位置当时的持仓数量 |
| `note` | 备注，可能含「均价 $xx/BTC」 |

**聚合规则（必须与其仓库自己的 `scripts/update_readme.py` 保持一致）**：

> 取**日期最新**的那一天，把该天所有 `location` 相加，即为当前持仓。
> 未出现在最新那天的 `location` 视为 0，**不做 carry-forward**。

这条规则有一个副作用：**更新时每个账户都得写一遍**，只写一个账户会导致其余账户被清零。
这是 `0.1BTC` 仓库的既有约定，本项目只是复现它，不要改成「每个 location 各取最新一行」——
两者结果会不一样。

以当前数据为例，最新日期是 `2026-09-20`，只有 `binance` 与 `okx` 两行：

```
0.00785078 + 0.0152673 = 0.02311808 BTC
```

更早的 `2026-08-20` 那天的 `cold` / `exchange` 行**不参与**当前持仓计算。

**数据时效**：该文件由本人**每周手动更新**，所以持仓数量存在延迟，**不是实时数据**。
实现上做了三件事：

1. 看板顶部固定显示快照日期与距今天数；
2. 超过 `max_stale_days`（默认 14 天）自动告警；
3. 估值仍按最新行情实时折算 —— 即「数量滞后、估值实时」。

**成本推算**：备注里的「均价 $xx/BTC」会被解析出来，按持仓量加权得到美元成本，
再按**当前汇率**折算成人民币。这是估算值（真实成本取决于买入当时的汇率），
README 会明确标注。若任一账户解析不出均价，则整块成本数据不输出——宁可不出数，也不编数。

### 2.2 标普500基金 · sp500-dca 仓库

| 文件 | 用途 | 取值字段 |
| --- | --- | --- |
| `data/portfolio.json` | 主数据 | `total.market_value` / `total.invested` / `total.profit` |
| `data/timeline.json` | 逐日时间线（备用） | `[{date, invested, market_value, profit}]` |

- 读取方式：`https://raw.githubusercontent.com/SayangChun/sp500-dca/main/...`
- 该仓库已用 GitHub Actions 每小时抓天天基金净值，**这里只消费结果，不重复劳动**。
- 天然滞后：QDII 净值 T+1 晚间披露，所以这里的数据比行情慢约 1 个交易日，属正常。

### 2.3 行情与汇率

持仓数量来自仓库，但估值必须用实时行情折算：

| 用途 | 首选 | 备选 |
| --- | --- | --- |
| BTC/USDT | `api.binance.com/api/v3/ticker/price` | `data-api.binance.vision`、OKX `market/ticker` |
| USD/CNY | `open.er-api.com/v6/latest/USD` | `api.frankfurter.dev/v1/latest` |

均为**公开接口、无需鉴权**，按 `config.yaml` 的顺序逐个尝试，全部失败才用兜底汇率并标注。
折算公式：`BTC/CNY = BTC/USDT × USD/CNY`。

### 2.4 网络实测（2026-09-24，本机在北京）

| 目标 | 结果 | 说明 |
| --- | --- | --- |
| `api.github.com` / `raw.githubusercontent.com` | ✅ | 读两个持仓仓库没问题 |
| `open.er-api.com` | ✅ | USD/CNY ≈ 6.72 |
| `api.binance.com` | ⚠️ 时通时不通 | 走代理时通，直连会 10s 超时 |
| `www.okx.com` | ❌ | 域名解析到 `198.18.x.x`（代理 fake-IP）后连接失败 |

**结论：行情抓取不要依赖本地网络，放在 GitHub Actions 的海外 Runner 上。**
持仓数据本身走 GitHub raw，本地也能读，所以本地用 `--mock` 即可完整验证逻辑。

---

## 3. 计算逻辑

代码位置：`scripts/fire.py`。数据流：

```
0.1BTC/holdings.csv ──► 最新日期各账户求和 ──► BTC 数量 ─┐
                                                          ├─► × 实时 BTC/CNY ─┐
BTC/USDT × USD/CNY ──────────────────────────────────────┘                    │
                                                                               ├─► 当前资产 ─┐
sp500-dca/portfolio.json ──► total.market_value ──────────────────────────────┘             │
                                                                                             ├─► 完成度
config.yaml/life_plan ──► Σ items ──► 月开销 1750 ──► × 12 ÷ 4.3% ──► FIRE 目标 ─────────────┘
```

关键实现细节：

0. **月开销由 `life_plan` 逐项推导**（见 §1.2），`fire.py` 通过
   `lifeplan.resolve_monthly(cfg)` 拿到 `(月开销, 规划摘要)`。
   规划摘要会写进 `data/latest.json` 并渲染到 README，所以「目标是怎么算出来的」是可追溯的。
   注意 `fire.monthly_expense` 现在是 `null`——**任何直接读它的代码都会拿到 None**，
   必须走 `resolve_monthly()`。

1. **一律折算成人民币**。BTC 用「USDT 价 × USD/CNY」换算，避免依赖离岸人民币盘口。
2. **进度历史自己存**。`data/history.json` 按天去重保存
   `{date, total_cny, progress_pct, btc_cny, sp500_cny, ndx100_cny, target_cny, basis_cny, profit_cny, fx_usd_cny}`，
   曲线与外推都基于它。**每天的分项必须当天记**——比特币本金要历史汇率、纳指要当天净值，
   事后无法精确重建。
   不能直接复用 `sp500-dca` 的 timeline，那是纯基金口径；也不能复用 `0.1BTC` 的曲线，
   那是纯比特币数量口径（且不折算人民币）。
3. **成本是估算，且要标注**。比特币成本从备注均价推算（见 §2.1），标普500成本取仓库的
   `invested`（精确值）。README 会说明哪一部分是估算。
4. **外推要标清楚**。口径是「真实定投额 + 已有持仓的复利增长」，不用历史增速，且：
   - 只统计投进三项资产的定投额（`contribution`）；每月储蓄里转存现金缓冲的部分
     **不进分子、不进外推**。`timeline.monthly_contribution` 记的是储蓄能力，不是定投额，
     两者相差约 ¥198/月，见路线图 §2.2；
   - 按当前市值加权预期年化，同时给**悲观 / 基准 / 乐观**三档（比特币占七成，单点没有意义）；
   - 超过 10 年时只显示「超过 10 年」，并说明该尺度下外推已无参考意义；
   - README 里固定附注「这不是预测」，并说明为什么不用近 30 天增速；
   - 可通过 `display.show_projection: false` 整个关掉。
5. **每小时被动收入 = 当前市值 × 预期年化回报 ÷ 8760**（`fire.passive_income()`）。
   加权年化按**市值**加权，不是各资产算术平均——73% 仓位压在比特币上时，两种算法差 2.4 个百分点。
   三条硬约束：
   - **它绝不参与 FIRE 目标**。目标只看月开销与提取率；把回报率 500% 塞进去，目标一动不动
     （`tests/test_passive_income.py` 钉住了这条）。
   - **必须同时给出「提取率口径」的对照数**。预期回报是「平均能涨多少」，
     提取率是「能安全花多少」，前者远高于后者是正常的；只给前者会让人以为现在就能靠它生活。
   - **必须给出悲观/乐观区间**。当前假设下加权年化 10.4%，换成两端是 0.8% 与 20.7%——
     这个跨度说明它是个量级参考，不是能拿去做预算的数。
   假设放在 `config.yaml` 的 `expected_return` 段，缺项时返回 `None`（不猜默认值）。

---

## 4. 自动化跟踪方式

### 4.1 工作流

`.github/workflows/update.yml`，两个 Job：

```
verify  ──►  用 tests/fixtures 的样例数据跑一遍（不联网）
             + 跑提交门控的回归测试（22 项）
             + 跑生活规划口径的回归测试（31 项）
             + 跑兼职收入口径的回归测试（26 项）
             + 跑分子口径的回归测试（19 项）
             + 跑被动收入口径的回归测试（20 项）
             + 跑两段式口径的回归测试（20 项）
             ↓ 全部通过才继续
update  ──►  读持仓仓库 + 抓行情 → 重算 → 写 README/曲线 → git commit & push
```

- 触发：
  - `push` 到 `main` —— 带 `paths-ignore: [data/**, README.md, reports/**]`，
    排除机器人自己改的那几个路径，避免「提交 → 触发 → 再提交」的循环
  - `cron: "0 * * * *"`（每小时）
  - `workflow_dispatch`（可勾选 force 强制重写）
- 权限：`contents: write`（提交需要）
- 并发：`concurrency` 串行化，避免两次运行互相覆盖
- **密钥：无。** 两个数据源都是公开仓库，行情是公开接口。
- 校验：`verify` 里除了冒烟检查，还跑两个回归测试——
  `tests/test_commit_gate.py`（14 项）与 `tests/test_life_plan.py`（26 项）。
  这两段逻辑改错了都不会报错，只会让数字悄悄跑偏（提交变多 / FIRE 目标虚增），
  所以必须靠测试守住。

#### 提交门控

阈值 = `max(min_commit_delta_cny, 上次总资产 × min_commit_delta_ratio)`，
当前配置为 `max(¥1, 0.3%)`；另外**跨天必定提交一次**，保证曲线每天至少一个点。

| 资产规模 | 阈值 |
| --- | ---: |
| ¥1,000 | ¥3 |
| ¥13,535 | ¥40.61 |
| ¥500,000 | ¥1,500 |

> **为什么用比例而不是固定金额**：固定金额不随资产规模变化。
> 固定金额不随资产规模变化：资产 ¥13.5k 时「变动 ¥1 即提交」只占 0.0074%，
> 而比特币小时级波动就有 0.1%~0.5% —— 结果几乎每小时都提交，约 **720 次/月**；
> 等资产涨到几十万，同一个金额又小到失去意义。
> 按比例门控预计 **2~4 次/天**。

> 为什么是每小时而不是每天：`sp500-dca` 的提交记录已经验证过——
> GitHub 的 schedule 事件实际比计划时间晚 4.5~5.5 小时。每小时轮询把最大滞后压到约 1 小时。
> 虽然比特币持仓是周更的，但估值需要实时行情，所以高频轮询仍有意义。

### 4.2 容错设计

| 情况 | 行为 |
| --- | --- |
| 某个行情源失败 | 自动换下一个源，README 底部标注实际使用的来源 |
| `holdings.csv` 读取/解析失败、但有历史值 | **沿用上次成功值**，并在 README 顶部打出告警 |
| `holdings.csv` 读取失败、且无历史值 | **绝不当成 0**，明确告警「本次进度未计入比特币，实际被低估」 |
| 快照超过 14 天未更新 | 保留数据，但在 README 顶部告警 |
| 备注里没有均价 | 不输出成本与盈亏，不编造数字 |
| `sp500-dca` 读取失败 | 沿用上次成功值并告警 |
| 单个来源异常 | 不影响其他来源，整体流程不中断 |

「拿不到数据」和「持有 0 枚」是两件事，代码里严格区分——否则进度会凭空倒退且无痕迹。
`holdings.csv` 里若存在 BOM，首列名会变成 `\ufeffdate` 导致所有行被静默丢弃，
解析层已做 BOM 剥离。

### 4.3 隐私

⚠️ **本仓库是公开仓库，`privacy.mode: full` 会把精确持仓金额公开到分**，
包括比特币的数量、成本与盈亏。这是 `0.1BTC` 仓库本身就公开的信息，但本仓库会额外
把它们折算成人民币金额并展示。

如果想只公开进度、不公开金额，把 `config.yaml` 改成：

```yaml
privacy:
  mode: masked
```

README 会只保留完成度进度条与百分比，金额显示为「已隐藏」。

---

## 5. README 展示内容

README 中 `<!-- FIRE:START -->` 与 `<!-- FIRE:END -->` 之间由脚本重写，
其余部分（口径说明、数据节奏、免责声明）是人工撰写的，不会被覆盖。

自动区块包含：

1. **更新时间**：最近一次运行的时间戳（纯文本）
2. **数据新鲜度**：比特币快照日期与距今天数、基金最新净值日
3. **进度条**：`reports/progress.svg` —— 自绘 SVG，为**三线**
   （出发门槛 / 咖啡师 FIRE / 完全 FIRE），由 `dual_progress_svg()` 读 `data.goals` 生成；
   主进度那一条由 `display.primary_progress` 指定并标 ★，没有 `goals` 时退回单条
4. **核心指标表**：三个门槛 + 三个完成度 + 当前资产 + 距离主进度
5. **进度曲线**：`reports/curve.svg` —— 紧跟指标表，回答「是怎么走到这里的」。
   纯手写 SVG，带暗色模式适配；**三条线**（出发门槛蓝、咖啡师 FIRE 橙、完全 FIRE 紫），
   竖虚线只标 FIRE 目标变化——台阶来自分母变化，不是资产涨跌。
   ⚠️ 出发门槛与完全 FIRE 门槛在部分早期记录里没有 `departure_cny` / `full_fire_cny`，
   那段按当前门槛折算，是反事实、不是历史实测。
   **图注明写这是反事实**（门槛不含行情，是政策数字，可以这么折算；
   FIRE 目标随兼职口径变过三次，必须逐日留档，不能折算）。
   放在这个位置是因为它与进度条是同一个问题的两种时态（现在 vs 历史），
   而收益曲线涉及本金，逻辑上属于「投入与盈亏」，仍留在后面
6. **月开销明细**（折叠）：`life_plan` 的逐项预算，按分组带小计与占比，
   外加「一次性支出」表。作用是让「目标资产」的来历可追溯——
   读者不必相信一个数字，可以直接看它是怎么加出来的
7. **资产构成表**：比特币与标普500的市值与占比
8. **持仓明细**（折叠）：比特币按账户列出数量与均价；基金列出市值、投入、份额、净值
9. **投入与盈亏**：含「比特币成本为估算值」的标注；紧跟**收益曲线**
   （`reports/profit.svg`，双面板：上为累计投入 vs 当前市值，下为累计收益率）
10. **每小时被动收入**：当前市值 × 预期年化回报 ÷ 8760，附加权年化、四条时间尺度换算、
    月开销覆盖率、悲观/乐观区间，以及**按 4.3% 提取率口径的对照数**。
    放在「外推」之前——两者都是往前看的内容，但这一项是当前持仓的直接推论，
    假设比「定投与收益率恒定」更硬
11. **外推**：定投额 + 资产增值，带三档区间与「非预测」标注
12. **数据源告警**（有异常时才出现）
13. **页脚**：两个数据源仓库链接 + 本次实际使用的行情源与汇率源

---

## 6. 代码结构与数据流

```
FIRE-Progress/
├── README.md                    # 展示层（自动区块 + 人工说明）
├── config.yaml                  # 唯一的口径与开关入口（含 life_plan 逐项预算）
├── requirements.txt             # 仅 PyYAML（HTTP 用标准库，减少 CI 故障点）
├── docs/
│   ├── DESIGN.md                # 本文档（实现方案）
│   ├── FIRE-WHY.md              # 为什么做这件事（不参与计算）
│   ├── FIRE-LIFE-PLAN.md        # 生活规划书（城市/住房/饮食/医疗/敏感性）
│   ├── FIRE-ROADMAP.md          # 两段式时间线（够撑多久）
│   └── FIRE-SPENDING-CHECKLIST.md # 支出候选清单（130+ 项逐项判定）
├── scripts/
│   ├── config.py                # 配置加载（支持 cfg.a.b 点号访问）
│   ├── net.py                   # 极简 HTTP：JSON 与纯文本两种抓取，5xx 重试
│   ├── lifeplan.py              # 生活规划：月开销逐项汇总、校验、一次性支出
│   ├── fire.py                  # 计算核心：目标、进度、成本、外推、两段式
│   ├── fmt.py                   # 金额格式化（三个渲染器共用一份）
│   ├── charts.py                # 三张 SVG：进度条、进度曲线、收益曲线
│   ├── blocks.py                # README 各小节文案，各返回一段 markdown
│   ├── render.py                # 组装：按顺序拼接小节 → 替换进手写 README
│   ├── site.py                  # GitHub Pages 静态页（手机端）
│   ├── update.py                # 主入口：抓取 → 计算 → 落盘 → 渲染 → 出图
│   └── sources/
│       ├── btc_repo.py          # 读取 0.1BTC 仓库的 holdings.csv
│       ├── sp500.py             # 读取 sp500-dca 仓库的 portfolio.json
│       ├── ndx100.py            # 抓东方财富 pingzhongdata 净值，算纳指100 市值
│       └── price.py             # BTC 价格 + USD/CNY 汇率
├── data/
│   ├── history.json             # 按天的进度快照（曲线数据源）
│   └── latest.json              # 最近一次结果（兜底缓存，必须入库）
├── reports/                     # 三张 SVG（由 Actions 生成，入库供 README 引用）
├── site/                        # 静态页生成结果（gitignore，只存在于 CI 与本地）
├── tests/
│   ├── fixtures/                # 样例数据，供 --mock 使用
│   ├── test_commit_gate.py      # 提交门控
│   ├── test_departure_fulltime.py # 出发门槛与全职情景
│   ├── test_fire_core.py        # 分子口径（加资产不改目标）
│   ├── test_labor_income.py     # 兼职收入（只扣增量）
│   ├── test_life_plan.py        # 月开销与一次性支出
│   ├── test_passive_income.py   # 被动收入（不参与目标）
│   ├── test_site.py             # 静态页（资产遍历、隐私遮蔽）
│   └── test_two_phase.py        # 两段式
└── .github/workflows/update.yml
```

**渲染层的四个文件各管一件事**：`charts.py` 只画图、`blocks.py` 只写小节、
`render.py` 只管顺序，`fmt.py` 放共用格式化——改哪一层去哪个文件，不用通读。
四个模块的输出由 `render.render_block()` 统一组装。

> `net.py` 而不是 `http.py`：脚本目录会进入 `sys.path[0]`，叫 `http.py` 会
> **覆盖标准库的 `http` 包**，导致 `urllib.request` 导入失败。这个问题已经出现过。

> **进度标识全部自绘 SVG，不用 shields.io 徽章**：shields.io 是不可控的外部服务，
> 大陆网络下时通时不通（本地实测直连与代理均不可达）；而且 badge 的 label 含中文时
> 若不 URL 编码，会直接返回「404 badge not found」。
> 文本进度条（`█░▎`）同样不可靠——这些块字符在 Unicode 里的东亚宽度是
> **Ambiguous**，中文环境按全角渲染、英文环境按半角，一旦 fallback 到不同字体，
> 整条进度条就会宽度错乱。SVG 按坐标绘制，与字体、与外部服务都无关。

> `net.py` 而不是 `http.py`：脚本目录会进入 `sys.path[0]`，叫 `http.py` 会
> **覆盖标准库的 `http` 包**，导致 `urllib.request` 导入失败。这个问题已经出现过。

> **进度标识全部自绘 SVG，不用 shields.io 徽章**：shields.io 是不可控的外部服务，
> 大陆网络下时通时不通（本地实测直连与代理均不可达）；而且 badge 的 label 含中文时
> 若不 URL 编码，会直接返回「404 badge not found」。
> 文本进度条（`█░▎`）同样不可靠——这些块字符在 Unicode 里的东亚宽度是
> **Ambiguous**，中文环境按全角渲染、英文环境按半角，一旦 fallback 到不同字体，
> 整条进度条就会宽度错乱。SVG 按坐标绘制，与字体、与外部服务都无关。

---

## 7. 已知限制

1. **比特币持仓有周级延迟**：手动维护，快照日之间可能相差 7 天以上，期间的进度变化只反映行情，不反映新增持仓。
2. **聚合规则的副作用**：更新 `holdings.csv` 时必须把每个账户都写一遍，漏写会导致该账户被当作 0。这是上游仓库的约定。
3. **比特币成本是估算**：按备注均价 × 当前汇率折算，与真实人民币成本存在偏差。
4. **历史只有从启用那天开始**：进度曲线无法回溯，只能往后积累。
5. **外推的可信度**：定投额度变化、收益率假设、行情波动都会让它失真，已明确标注为非预测并给出三档区间。
6. **改口径会造成进度曲线的台阶**：FIRE 目标 = 组合需覆盖 × 12 ÷ 提取率，
   所以每次下调月开销或上调兼职收入，完成度都会「跳升」——其中大部分是**分母变小**，不是资产增长。
   `curve.svg` 会在口径调整日画竖虚线，README 里也写了对应说明。
   **不要为了「让曲线好看」去回填历史**——那等于篡改过去的口径。
7. **月开销是估算值**：`life_plan` 的每项金额都来自公开数据折算，不是实地报价。
   真实区间大致为 ¥206,000 – ¥373,000（见 FIRE-LIFE-PLAN.md §7）。

---

## 8. 上线步骤

```bash
# 1. 本地验证（不联网，用样例数据）
pip install -r requirements.txt
python scripts/update.py --mock
python tests/test_commit_gate.py
python tests/test_life_plan.py

# 2. 推送
git remote add origin https://github.com/SayangChun/FIRE-Progress.git
git push -u origin main
```

**不需要配置任何 Secrets。** 推送本身就会触发工作流，无需手动操作；
若想跳过阈值立即重算，可在 Actions 页面用 `workflow_dispatch` 勾选 force。

首次跑完建议核对三件事：

1. 比特币数量与 `0.1BTC` 仓库 README 显示的是否一致；
2. 完成度是否落在预期区间；
3. 页脚标注的行情源 —— 如果显示的不是首选源，说明发生了自动降级（正常，但要知情）。
