# Amazon Garden 竞品监控与需求热度预测系统

**Amazon Garden Competitor Monitoring & Demand Proxy Forecasting**

## Project Overview

本项目面向 Amazon Garden 运营场景，由两条独立链路组成：一条用 Amazon Reviews 2023 的历史 rating interaction 预测商品月度**需求热度代理指标**，另一条保存 Amazon.sg 当前搜索结果，分析竞品页面状态。项目覆盖公开数据获取与质量检查、原始响应留存、SQLite 存储与 SQL、商品 × 月特征工程、Baseline 与 RandomForest 评估、误差诊断。

预测目标 `future_interaction_count` 是当前预测月份内的 **review/rating interaction count proxy**，不是 `units_sold` 或真实 `sales`；公开数据不含商品真实销量。实时商品也尚未接入历史模型。

## System Architecture

```text
Historical（历史热度代理预测）
Amazon Reviews 2023 · Patio_Lawn_and_Garden 5-core
  → cleaning / data-quality audit
  → 2019 历史确定的 5,000 个 parent_asin
  → parent_asin × UTC month 完整零值网格
  → 历史特征工程
  → lag_1 / rolling_mean_3 Baseline
  → 固定参数 RandomForest
  → 2022 Test 误差与方向分析

Realtime（当前竞品状态）
Amazon search · garden hose
  → requests probe 与原始 503 留存
  → requests × marketplace 控制变量诊断
  → Playwright 单页成功采集 / 离线 HTML 重放
  → SQLite 商品快照与运行审计
  → GROUP BY / CASE / LAG() SQL 分析
  → future: repeated snapshot monitoring（尚未实现）
```

两条链路目前**没有商品级 JOIN**：历史 `parent_asin` 与实时 `asin` 的直接交集为 0，且没有可信的父子商品映射。它们共同服务 Garden 竞品监控，但不能声称实时 20 个商品已经进入历史模型。证据见 [Stage 6A 关联核查](reports/stage6_data_integration.md)。

## Dataset & Scope

| 项目 | 实际口径 |
|---|---|
| 历史来源 | McAuley Lab [Amazon Reviews 2023](https://amazon-reviews-2023.github.io/main.html)，`Patio_Lawn_and_Garden` 类目；完整 5-core 文件实际扫描 **3,441,178** 条 interaction |
| 正式 cohort | 只由 2019 年历史决定，固定 **5,000 个 `parent_asin`**；不是按 2020–2022 表现挑选 |
| 时间与粒度 | UTC 自然月；2019 warm-up；Train 2020-01～2021-12；Test 2022-01～2022-12；`parent_asin × month` |
| 建模表 | **180,000** 行：Train **120,000**，Test **60,000**；无 interaction 的月也保留，计数为 0 |
| 实时来源 | `garden hose` 搜索；最终有效页面为 **Amazon.sg / SGD**；SQLite 中 **1** 个有效商品快照、**20** 个商品 |

历史 5-core 每条包含 `user_id`、`parent_asin`、`rating`、`timestamp`，不包含 `verified_purchase`；实际预测使用 interaction count，不声称 verified review count。原始文件与抽样/范围记录见 [数据质量报告](reports/data_quality_report.md)、[建模口径](reports/modeling_scope.md)。

## Features

预测月份开始前可获得、并实际进入 RandomForest 的 11 个历史特征：

`lag_1`、`lag_2`、`lag_3`、`rolling_mean_3`、`rolling_mean_6`、`rolling_std_3`、`historical_interaction_mean`、`historical_interaction_max`、`active_months_history`、`historical_rating_mean`、`historical_rating_count`。

`interaction_count` 是当前月**审计列**，`future_interaction_count` 是目标；二者均不进入模型输入。`parent_asin` 只用于识别商品。2023 metadata 累计字段未回填为历史特征。构造与泄漏检查见 [Stage 3 特征表](reports/stage3_feature_table.md)、[leakage audit](reports/leakage_audit.md)。

## Modeling

| 2022 Test，60,000 行 | MAE |
|---|---:|
| 最佳简单 Baseline：`lag_1`（上月交互数） | **0.995867** |
| RandomForestRegressor | **0.935867** |

相对于 `lag_1`，RandomForest 的 Test MAE 下降 **0.059999（6.02%）**。只训练了一组固定参数：`n_estimators=150`、`max_depth=12`、`min_samples_leaf=5`、`random_state=42`、`n_jobs=-1`；没有根据 Test 结果反复调参。其 impurity-based `feature_importances_` 中 `lag_1` 为 **0.790433（约 79%）**，表示模型依赖程度，不是因果效应。

采用按月时间切分，是因为目标是在月初预测未来一个月；随机打散商品月行会让训练阶段看到测试日期之后的观察，不能模拟该预测时点。结果见 [Baseline](reports/stage4_baseline.md)、[RandomForest](reports/stage5_random_forest.md)。

## Error Analysis

2022 Test 的 RF 绝对误差 P95 为 **3.216521**；定义 `absolute_error > P95` 后有 **3,000 / 60,000** 个事后异常候选。全体 Test 中高估 **40,525** 次，平均高估幅度 **0.645824**；低估 **19,475** 次，平均低估幅度 **1.539411**。因此不能只凭高估次数断定整体系统性高估。`target=0` 的月份在本次预测中偏向小幅高估；`target>=4` 的月份更常被低估。

该 P95 来自 **2022 Test 的 post-hoc error analysis**，不是已部署的生产阈值。不能据此调整模型，再回到同一 Test 宣称无偏性能提升。详见 [误差与方向分析](reports/stage6_error_analysis.md)。

## Realtime Collection & SQL

初次普通 `requests` 请求 Amazon.com 搜索返回 **503**；控制变量实验中，`requests → Amazon.sg` 也返回 **503**，而普通 Playwright/Chrome 直达 Amazon.sg 返回 **200**，从 Amazon.com 出发的浏览器路径经 **302** 到 Amazon.sg 后也取得正常页面。实验支持“本次客户端/请求上下文与结果相关”，**不能证明具体反爬规则、IP、User-Agent 或 Cookie 是根因**；没有代理或验证码绕过。原始 HTML、响应头、重定向链和截图已保留，见 [控制变量报告](reports/realtime_root_cause_experiment.md)。

成功页前 20 个真实商品经离线重放写入 `data/realtime/amazon_garden_realtime.db`；快照带 `crawl_time`、`marketplace=amazon.sg`、`currency=SGD`、`collection_method=playwright`。SQL 模块以只读方式用 `GROUP BY` 汇总页面字段、`CASE WHEN` 划分基于本次价格分布的区间、`LAG()` 准备同关键词/市场/ASIN 的跨快照对比。**目前只有一个有效快照，`LAG()` 实际返回 0 行，没有真实趋势结论。**详见 [Realtime V1](reports/realtime_collection_v1.md) 与 [Stage 7A SQL](reports/stage7_sql_analysis.md)。

## Engineering / Data Quality

- **失败可审计：**503 的 raw HTML、HTTP metadata 与运行状态留存；失败运行不伪装成商品行。控制变量实验的四组请求分别保存证据。
- **原始响应与可重放：**成功浏览器 HTML 和截图留存；离线 parser 重放、重复运行的幂等检查已经执行。
- **SQLite 快照：**`search_snapshots` 用 `(crawl_time, keyword, asin)` 唯一约束，同一 ASIN 可在不同时间再次保存；`collection_runs` 独立记录采集成败。市场、币种和采集时间随快照保存。
- **时间泄漏防护：**2019 决定 cohort；月度零交互行不丢弃；lag、rolling、历史评分只使用预测月之前的数据；Train/Test 按时间分开；metadata 的 2023 累计值不进入模型。
- **数据质量边界：**未知价格保留 NULL，不用 0 代替；异常先报告。SQL 只读分析前后数据库 SHA-256 相同。详见 [质量报告](reports/data_quality_report.md)、[Stage 3 验证](reports/stage3_feature_table.md)。

项目从仓库根目录运行，建议 Python 3.9+。`requirements.txt` 固定 Python 依赖；Playwright 浏览器采集当时使用单独的浏览器/CLI 环境，并非下列离线分析的必要依赖。公开仓库**不包含**大型官方原始文件、历史 SQLite、商品月 CSV、实时 SQLite 或浏览器原始响应（后者含会话/响应头审计信息），不会用模拟数据填补。要从真实来源重建历史输入，先按 [官方数据入口](https://amazon-reviews-2023.github.io/main.html) 获取权限与文件，并从仓库根目录按顺序执行：

```bash
python3 -m pip install -r requirements.txt
python3 -B -m src.download_data
python3 -B -m src.analyze_recent_period
python3 -B -m src.build_cohort
python3 -B -m src.build_product_month
```

`src.download_data` 会检查官方文件大小，下载该类目的约 60 MB 完整 5-core，并只读取 metadata 前缀；不会下载约 2 GB 的完整 raw reviews。后续历史建模命令依赖这些真实数据。实时 SQL 需本地已采集的 SQLite；仓库只提供采集、离线重放和分析代码及真实运行报告，**不能在全新克隆目录中直接重放未公开的 HTML 或运行 SQL 得到现有 20 行**。运行实时采集入口会访问外部页面，应与离线重放入口区分。

```bash
python3 -B -m src.evaluate_baselines
python3 -B -m src.train_random_forest
python3 -B -m src.analyze_prediction_errors
python3 -B -m src.analyze_realtime_sql
# 仅用已保存的成功 HTML 重放，不发网络请求：
python3 -B -m src.realtime.replay_saved_html --html data/realtime/raw/garden_hose_playwright_20261007T090918742000Z.initial.html
```

## Key Results

| 维度 | 已验证结果 |
|---|---|
| 历史数据 | Patio_Lawn_and_Garden 完整 5-core：3,441,178 条；正式 cohort：5,000 个父商品 |
| 建模样本 | 180,000 个商品月；2022 Test：60,000 行 |
| 预测比较 | `lag_1` MAE 0.995867；RF MAE 0.935867；相对改善 6.02% |
| 误差候选 | Test P95 3.216521；严格大于阈值的候选 3,000 行 |
| 实时采集 | Amazon.sg / SGD：1 个有效快照、20 个真实商品；Amazon.com 没有成功商品快照 |
| 数据关联 | 历史 `parent_asin` 与实时 `asin` 直接 overlap **0**；目前不做商品级 JOIN |
| SQL 趋势 | `LAG()` 查询已运行，真实跨快照变化行数 **0** |

## Limitations

- **Interaction proxy ≠ sales：**5-core rating/review interaction 不等于购买件数、GMV 或真实需求；零交互月也不等于零销量。
- **5-core selection bias：**数据经过全期活跃用户/商品筛选，不能代表完整 Amazon 交易或严格线上可见样本；事件时间也未证明等于真实入库可见时间。
- **Metadata coverage 与泄漏：**现有 metadata 前缀样本仅覆盖正式 cohort 的 **171 / 5,000** 个父商品；其 2023 累计属性不是 2020–2022 的历史特征，回填会造成时间泄漏风险。
- **实时市场与时间：**成功商品仅来自 Amazon.sg / SGD 的一次页面；不能直接代表 Amazon.com。单次 snapshot 不能建立价格、评价量或位置趋势。
- **页面指标：**`search_position` 只是本次采集卡片顺序，**不是 Amazon 官方 Search Rank**；`review_count` 是页面展示的 ratings 数，不是 sales；当前价格不是历史价格。
- **无法可信关联：**尚无可靠 `asin ↔ parent_asin` 映射；历史模型与实时 20 商品未在商品级融合。
- **缺少业务驱动变量：**没有同期历史价格、促销、广告、库存、官方排名、真实销量或流量特征；不能据此推断预测误差的业务原因。

## Production Roadmap

以下均为**future / proposed，尚未实现**：

1. 在授权和访问条件允许下，安排低频、可比的重复快照；记录市场、币种、关键词、时间与页面上下文，才能观察变化。
2. 建立可核验的商品主数据及 `asin ↔ parent_asin` 映射，核对父子变体和市场，再评估商品级融合。
3. 若能获得授权的内部销量、流量、广告、促销与库存数据，重定义业务目标并核对特征可见时点。
4. 在 Train/Validation 的历史时间滚动窗口做特征与模型选择，再用未见时期评估；异常阈值也应在验证期确定。
5. 增加 proxy 数据源健康监控、受控重试和告警；遇明确访问限制时停止对应采集路径。
6. 只有在规模和访问条件确有需要时，再评估 Scrapy 或分布式调度；另行设计 dashboard / monitoring layer。
