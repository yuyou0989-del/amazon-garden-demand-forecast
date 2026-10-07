# Stage 5 RandomForest 与 Baseline

Train：2020-01～2021-12，120,000 行；Test：2022-01～2022-12，60,000 行。沿用原始 `split`，没有随机切分。目标：`future_interaction_count`。

## 模型

仅使用 11 个 Stage 3 历史特征：`lag_1`, `lag_2`, `lag_3`, `rolling_mean_3`, `rolling_mean_6`, `rolling_std_3`, `historical_interaction_mean`, `historical_interaction_max`, `active_months_history`, `historical_rating_mean`, `historical_rating_count`。
`interaction_count`、`parent_asin`、2023 metadata 不进入 X；target 仅作 y。
固定参数：`n_estimators=150`, `max_depth=12`, `min_samples_leaf=5`, `random_state=42`, `n_jobs=-1`。仅训练一次。

## 总体比较

lag_1 Baseline MAE：0.995867；RandomForest MAE：0.935867。
绝对改善（Baseline − RF）：+0.059999；相对改善：+6.02%。

## 真实 target 分段

| 区间 | 样本数 | Baseline MAE | RF MAE | 改善 |
|---|---:|---:|---:|---:|
| target = 0 | 32,905 | 0.395928 | 0.515057 | -0.119130 |
| target = 1–3 | 20,829 | 1.215613 | 0.866915 | +0.348698 |
| target >= 4 | 6,266 | 3.415895 | 3.374898 | +0.040997 |

## 绝对误差分布

| 方法 | median | P90 | P95 | max |
|---|---:|---:|---:|---:|
| lag_1 Baseline | 1.000000 | 3.000000 | 4.000000 | 40.000000 |
| RandomForest | 0.523251 | 2.116948 | 3.216521 | 36.749322 |

## Feature importance

| 排名 | 特征 | importance |
|---:|---|---:|
| 1 | lag_1 | 0.790433 |
| 2 | historical_interaction_mean | 0.066034 |
| 3 | rolling_mean_3 | 0.029814 |
| 4 | historical_interaction_max | 0.019840 |
| 5 | historical_rating_mean | 0.016684 |
| 6 | rolling_mean_6 | 0.015807 |
| 7 | active_months_history | 0.014592 |
| 8 | historical_rating_count | 0.014474 |
| 9 | rolling_std_3 | 0.012406 |
| 10 | lag_2 | 0.010196 |
| 11 | lag_3 | 0.009720 |

重要性仅表示该模型对历史特征的依赖，不代表因果关系。

## 2022 真实案例

案例依固定行序选择：改善差值最大、恶化差值最大、其余高热度中 target 最大。仅比较预测误差，不推断商品变化原因。

| 案例 | parent_asin | month | target | lag_1 prediction | RF prediction | Baseline abs error | RF abs error |
|---|---|---|---:|---:|---:|---:|---:|
| RF 明显更好 | B0BPD5MS27 | 2022-11-01 | 30 | 61.000000 | 41.500905 | 31.000000 | 11.500905 |
| RF 明显更差 | B0BPD5MS27 | 2022-10-01 | 61 | 50.000000 | 34.243767 | 11.000000 | 26.756233 |
| 高热度 | B087NMB7VD | 2022-07-01 | 71 | 43.000000 | 40.220168 | 28.000000 | 30.779832 |

## 验证与限制

运行前核对固定行数、月份、cohort、11 特征无 NaN/无穷值及 Stage 4 Baseline MAE；运行后核对 60,000 个连续预测及负值数量。
负预测数：0；出现时业务输出 clip 到 0，未取整。
数据为 5-core interaction，目标是热度代理指标，不是真实销量；模型仅在该固定 cohort 和 2022 测试期得到本报告结果。
