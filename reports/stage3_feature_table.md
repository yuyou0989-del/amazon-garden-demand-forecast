# Stage 3 Feature Table

- 来源：官方 Patio_Lawn_and_Garden 完整 5-core 扫描所得 Stage 1.5 `interactions` 表；固定 2019 cohort CSV 及数据库成员相互核对。没有读取 metadata。
- 粒度：parent_asin × UTC 自然月；2019-01 至 2019-12 只用于历史预热，完整零交互月保留。
- 正式行数：180,000；商品数：5,000；月份：2020-01-01 至 2022-12-01。
- Train：120,000 行（2020-01～2021-12）；Test：60,000 行（2022-01～2022-12）。
- 源区间 2019～2022 有 452,626 条 cohort interaction；完整网格的无记录月记 interaction_count=0。
- target：future_interaction_count = 当前行 month 内真实 interaction_count；在月初预测该月。`interaction_count` 是审计/标签来源列，**不得作为模型特征**。
- 特征列：lag_1, lag_2, lag_3, rolling_mean_3, rolling_mean_6, rolling_std_3, historical_interaction_mean, historical_interaction_max, active_months_history, historical_rating_mean, historical_rating_count。lag/rolling/expanding/rating 均只用 T 前数据；rolling_std_3 使用样本标准差 ddof=1。
- 缺失值：2019 完整预热使正式月份的历史特征缺失数为 0；未对任何历史特征做模型方便型填补。零交互月的 interaction_count=0 是源文件计数口径。
- target：均值 1.6830；中位数 1；p90 4；p95 7；最大 94。
- zero-target rate：45.9578%；train 41.5158%；test 54.8417%。

| 字段 | 缺失率 |
| --- | ---: |
| parent_asin | 0.0000% |
| month | 0.0000% |
| interaction_count | 0.0000% |
| lag_1 | 0.0000% |
| lag_2 | 0.0000% |
| lag_3 | 0.0000% |
| rolling_mean_3 | 0.0000% |
| rolling_mean_6 | 0.0000% |
| rolling_std_3 | 0.0000% |
| historical_interaction_mean | 0.0000% |
| historical_interaction_max | 0.0000% |
| active_months_history | 0.0000% |
| historical_rating_mean | 0.0000% |
| historical_rating_count | 0.0000% |
| future_interaction_count | 0.0000% |
| split | 0.0000% |

- 泄漏验证：完整网格/分区/当前月 target/禁用 metadata 全量通过；12 条独立源事件重算 lag、rolling、expanding、rating timestamp<T、target 均通过；2022 样本未用同月 target 计算特征。固定 seed=42，12 条商品月由源事件/时间戳独立抽查；详见终端验证输出。
- 边界：源数据已按全时期 5-core 资格筛选；事件 timestamp 近似预测时可见时间，未证明线上真实入库时点。零 interaction 不等于零销量、零需求或在售。

## 连续六个月真实样例

parent_asin：`1754164498`；2019 历史已在上一月特征中。

```text
     month  interaction_count  lag_1  lag_2  lag_3  rolling_mean_3  historical_rating_mean  future_interaction_count split
2020-01-01                  4      3      3      4        3.333333                4.918919                         4 train
2020-02-01                  3      4      3      3        3.333333                4.878049                         3 train
2020-03-01                  1      3      4      3        3.333333                4.886364                         1 train
2020-04-01                  1      1      3      4        2.666667                4.888889                         1 train
2020-05-01                  1      1      1      3        1.666667                4.891304                         1 train
2020-06-01                  2      1      1      1        1.000000                4.829787                         2 train
```
