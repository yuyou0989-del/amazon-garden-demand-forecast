# Stage 4 Baseline 评估

仅评估 Stage 3 固定 cohort 的 2022-01 至 2022-12 `split=test`；60,000 行、5,000 个 parent_asin。无随机切分。
目标为当前月 `future_interaction_count`。当前月 `interaction_count` 仅为审计列，本脚本未读取。

## Baseline 与总体指标

`lag_1` 为上个月计数；`rolling_mean_3` 为预测月之前三个完整月的均值。二者由 Stage 3 历史特征表提供；本阶段只复制特征作预测，不使用 test target 构造特征。

Target mean: 1.332817；median: 0.000000；zero rate: 54.841667%。

| Baseline | Prediction mean | MAE | 手工 MAE |
|---|---:|---:|---:|
| lag_1 | 1.345117 | 0.995867 | 0.995867 |
| rolling_mean_3 | 1.353950 | 1.014000 | 1.014000 |

## 按真实 target 分段

| 区间 | 样本数 | lag_1 MAE | rolling_mean_3 MAE |
|---|---:|---:|---:|
| target = 0 | 32,905 | 0.395928 | 0.450651 |
| target = 1~3 | 20,829 | 1.215613 | 1.104630 |
| target >= 4 | 6,266 | 3.415895 | 3.671082 |

## 最佳 Baseline

`best_baseline_name = lag_1`；`best_baseline_MAE = 0.995867`。下一阶段复杂模型至少应与该 2022 test 基准比较。

## 真实案例

准确案例取非零 target 中两个 Baseline 绝对误差之和最小的一行；明显错误案例取该和最大的一行。

| 案例 | parent_asin | month | lag_1 | rolling_mean_3 | actual target | prediction_lag1 | prediction_rolling3 | abs error lag1 | abs error rolling3 |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| 准确 | B00004RBDU | 2022-01-01 | 2.000000 | 2.000000 | 2 | 2.000000 | 2.000000 | 0.000000 | 0.000000 |
| 明显错误 | B087NMB7VD | 2022-09-01 | 51.000000 | 55.000000 | 11 | 51.000000 | 55.000000 | 40.000000 | 44.000000 |

## 验证

60,000 行、12 个 2022 月份、5,000 个商品、商品-月份唯一；目标与预测无 NaN/无穷值；两种 MAE 与独立逐行绝对误差求和一致。预测仅来自预先构造的历史特征。
