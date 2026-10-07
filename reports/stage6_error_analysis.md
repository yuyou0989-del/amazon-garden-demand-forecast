# Stage 6B：RandomForest 预测误差与异常候选

Stage 5 未保存逐行预测或模型文件；本次仅以同一 Stage 3 数据、同一 11 个特征、同一固定参数和时间切分重现一次预测，没有调参或训练其他模型。
2022 Test：60,000 行；复核 RF MAE：0.935867。
`signed_error = actual − prediction`；正值为 underprediction（低估），负值为 overprediction（高估），零为 exact。

## 阈值与数量

绝对误差 P90 = 2.116948；P95 = 3.216521；P99 = 6.793128。
规则：`absolute_error > P95`。候选 3,000 行，占 Test 5.0000%。严格大于，不包含等于阈值的行。
全部 Test：underprediction 19,475；overprediction 40,525；exact 0。
P95 候选：underprediction 2,218；overprediction 782；exact 0。

## 最大绝对误差 Top 10

| parent_asin | month | actual | prediction | signed_error | absolute_error | direction |
|---|---|---:|---:|---:|---:|---|
| B09RJTP3C9 | 2022-07-01 | 61 | 24.250678 | +36.749322 | 36.749322 | underprediction |
| B0C576GBM7 | 2022-05-01 | 50 | 15.257581 | +34.742419 | 34.742419 | underprediction |
| B0C7JJP6JT | 2022-05-01 | 53 | 19.690355 | +33.309645 | 33.309645 | underprediction |
| B09TYLKWTY | 2022-07-01 | 56 | 23.312251 | +32.687749 | 32.687749 | underprediction |
| B087NMB7VD | 2022-07-01 | 71 | 40.220168 | +30.779832 | 30.779832 | underprediction |
| B09TYLKWTY | 2022-08-01 | 21 | 51.734555 | -30.734555 | 30.734555 | overprediction |
| B087NMB7VD | 2022-09-01 | 11 | 38.477962 | -27.477962 | 27.477962 | overprediction |
| B0BH3JBW3C | 2022-08-01 | 42 | 14.590694 | +27.409306 | 27.409306 | underprediction |
| B0BPD5MS27 | 2022-10-01 | 61 | 34.243767 | +26.756233 | 26.756233 | underprediction |
| B08TCH7NLW | 2022-06-01 | 6 | 32.643423 | -26.643423 | 26.643423 | overprediction |

## 候选中最大低估 Top 5

| parent_asin | month | actual | prediction | signed_error | absolute_error | direction |
|---|---|---:|---:|---:|---:|---|
| B09RJTP3C9 | 2022-07-01 | 61 | 24.250678 | +36.749322 | 36.749322 | underprediction |
| B0C576GBM7 | 2022-05-01 | 50 | 15.257581 | +34.742419 | 34.742419 | underprediction |
| B0C7JJP6JT | 2022-05-01 | 53 | 19.690355 | +33.309645 | 33.309645 | underprediction |
| B09TYLKWTY | 2022-07-01 | 56 | 23.312251 | +32.687749 | 32.687749 | underprediction |
| B087NMB7VD | 2022-07-01 | 71 | 40.220168 | +30.779832 | 30.779832 | underprediction |

## 候选中最大高估 Top 5

| parent_asin | month | actual | prediction | signed_error | absolute_error | direction |
|---|---|---:|---:|---:|---:|---|
| B09TYLKWTY | 2022-08-01 | 21 | 51.734555 | -30.734555 | 30.734555 | overprediction |
| B087NMB7VD | 2022-09-01 | 11 | 38.477962 | -27.477962 | 27.477962 | overprediction |
| B08TCH7NLW | 2022-06-01 | 6 | 32.643423 | -26.643423 | 26.643423 | overprediction |
| B09TPV23DT | 2022-05-01 | 3 | 22.281012 | -19.281012 | 19.281012 | overprediction |
| B082BHVY2Y | 2022-10-01 | 11 | 29.527661 | -18.527661 | 18.527661 | overprediction |

## 重复进入候选的商品 Top 10

| parent_asin | anomaly month count |
|---|---:|
| B0BPD5MS27 | 11 |
| B0BTM794R7 | 11 |
| B078CXX1LM | 9 |
| B08PBR26YW | 9 |
| B08TGW54N5 | 9 |
| B08ZKJQRVS | 9 |
| B09RJTP3C9 | 9 |
| B09VPTQ1ZR | 9 |
| B06Y46B73L | 8 |
| B0719NR5L3 | 8 |

## 证据边界

P95 来自 2022 Test，只用于事后模型误差分析，不是已部署的生产报警阈值；不得用该 Test 阈值继续调整 RandomForest，再在同一 Test 宣称性能提升。生产环境应先从 Train/Validation 的历史误差确定阈值，再应用于未来未见数据。
候选表示预测误差大，不证明商品热度变化的原因；interaction 也不等于销量。


## Prediction Bias / Direction Analysis

全部 Test：mean signed_error = +0.063467；median = -0.194852；sum = +3808.013063。
| 方向 | count | mean magnitude | median | P90 | P95 | total magnitude |
|---|---:|---:|---:|---:|---:|---:|
| underprediction | 19,475 | 1.539411 | 0.858965 | 3.457740 | 4.948746 | 29980.030674 |
| overprediction | 40,525 | 0.645824 | 0.390877 | 1.394241 | 2.033791 | 26172.017611 |

| 真实 target 区间 | rows | mean signed_error | under count | over count | MAE |
|---|---:|---:|---:|---:|---:|
| target = 0 | 32,905 | -0.515057 | 0 | 32,905 | 0.515057 |
| target = 1–3 | 20,829 | +0.259445 | 14,340 | 6,489 | 0.866915 |
| target >= 4 | 6,266 | +2.450046 | 5,135 | 1,131 | 3.374898 |

在这 60,000 行中，高估 40,525 次、低估 19,475 次；平均残差显示总体平均低估。低估平均幅度 1.539411，高估平均幅度 0.645824；应结合分段表判断方向和大小，不能只凭高估次数较多就下结论。
这些是 2022 Test 的事后残差描述；不能证明未来数据也有相同偏差，不能推断误差原因或真实销量，也不能据此回头调参后在同一 Test 宣称改进。
