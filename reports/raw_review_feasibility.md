# Raw Review Feasibility

## 官方明确提供的信息

- 数据集：McAuley Lab Amazon Reviews 2023；类目 Patio_Lawn_and_Garden。
- 官方文件：`Patio_Lawn_and_Garden.jsonl.gz`；[下载地址](https://mcauleylab.ucsd.edu/public_datasets/data/amazon_2023/raw/review_categories/Patio_Lawn_and_Garden.jsonl.gz)。
- [官方类目表](https://amazon-reviews-2023.github.io/main.html)给出约 16.5M reviews，这是四舍五入数量；本地没有读取全量原始评论，不把它写成精确行数。
- [官方 Hugging Face 未压缩 JSONL 镜像](https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023/blob/main/raw/review_categories/Patio_Lawn_and_Garden.jsonl)显示约 7.75 GB。这是网页展示的舍入大小，不是本地完整解压验证的字节数；没有确认 gzip 解压结果与镜像逐字节一致。
- 官方字段表列出 rating、title、text、images、asin、parent_asin、user_id、timestamp、helpful_vote、verified_purchase。官网 Quick Start 个别示例使用 sort_timestamp/helpful_votes，与字段表不同，因此代码以下面的本地真实字段为准。

## 本地实际验证的信息

检查时间 UTC：2026-10-07T08:19:24.929130+00:00。

- HEAD：压缩文件 **2,160,005,181 字节**（约 2.160 GB），ETag `"80bf103d-62bdbaf6db88e"`。
- 决策阈值：1,500,000,000 字节；实际文件也超过 1.5 GiB，未完整下载。
- 实际 Range 请求 bytes 0–4194303，服务器返回对应 Content-Range，仅传输 **4,194,304 字节**。
- gzip 前缀顺序读取并保存 **2,000 条**真实评论；这是 schema 样本，不是完整 gzip、不包含完整商品历史。
- 样本文件：`data/raw/raw_review_schema_sample.jsonl`，1,093,954 字节；SHA-256 `1d8a7a5d3b0a74d2b71c5012e9b9626c1c00a65726e09c81ebc2199a63c84c2f`。
- 样本中 verified_purchase=True 有 1450 条；只证明字段及布尔类型存在，不估计类目购买验证比例。

| 真实字段 | 样本实际类型 | 字段出现记录数 |
| --- | --- | --- |
| rating | float | 2000 |
| title | str | 2000 |
| text | str | 2000 |
| images | list | 2000 |
| asin | str | 2000 |
| parent_asin | str | 2000 |
| user_id | str | 2000 |
| timestamp | int | 2000 |
| helpful_vote | int | 2000 |
| verified_purchase | bool | 2000 |

timestamp 是 Unix 毫秒，实际整数值可正常转换。响应头保存在 data/raw/raw_review_schema_range_headers.txt，机器可读证据保存在 outputs/raw_review_probe.json。

## 原始 review 最近时期统计的边界

以下数字仅来自上述前 2000 条 schema 样本，源顺序可能按用户排列，不代表类目年度数量，也不能与全量 5-core 总数直接比较。

| 年（UTC） | 样本 interaction 数 | 样本活跃 parent_asin | 样本活跃 user 数 |
| --- | --- | --- | --- |
| 2018 | 100 | 99 | 55 |
| 2019 | 216 | 214 | 87 |
| 2020 | 397 | 393 | 132 |
| 2021 | 514 | 501 | 161 |
| 2022 | 413 | 405 | 136 |
| 2023 | 36 | 36 | 24 |

原始 review **全量**的年度 interaction、商品及用户精确数量：无法计算，未完整扫描。

## 推测及尚未验证的信息

完整 raw 数据可能能补充更丰富的 verified-review 目标，但当前样本不能证明同一商品的完整历史、采集覆盖或所有字段在全量文件中的稳定性。只有完整扫描才可得到某个随机商品范围的完整 raw 历史。gzip 不具备可直接按商品 ID 定位的通用索引，不能任意 Range 一个中间片段就称为完整商品样本。

没有推断源文件规模之外的下载时长，没有把 2023 年数量下降归因为真实市场需求或已证实的采集错误。

## 本次决策

字段补充有价值，但完整 raw 超出预算；只确认 schema，正式分析继续使用完整官方 5-core。候选升级目标优先为 `future_verified_interactions`，定义为未来窗口内 verified_purchase=True 的 raw 评论数；当前 **正式 target 是 future_interaction_count**，因为不能把局部 raw 样本的购买验证状态拼接为全量交互的状态。

原始 review 不包含真实销量。任何 verified review 计数依然是需求热度代理，而不是 sales、units_sold 或 revenue。
