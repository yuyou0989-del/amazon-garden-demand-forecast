# Dataset Overview

| 数据 | 文件 | 行数 | 列数 | 字节数 |
| --- | --- | --- | --- | --- |
| 交互分析输入（固定商品范围） | data/interim/interactions_cohort.csv | 111011 | 4 | 6549959 |
| metadata 原始记录子集 | data/raw/meta_Patio_Lawn_and_Garden_first10000.jsonl | 10000 | 16 | 36079087 |

完整官方 5-core 文件实际扫描 3441178 行。

分析范围为 metadata 原始顺序第 1–10,000 行对应父商品在整个 5-core 文件中的全部交互；保留这些商品在 5-core 用户子集中的历史，不代表原始评论全集。未删除异常或重复记录。

# Time Coverage

最早："2006-01-12T01:31:56+00:00"；最晚："2023-09-07T15:30:43.844000+00:00"（UTC）。

跨度：6447.582498194444 天。Unix 毫秒转换，不自动纠正单位。

| 年（UTC） | interaction 数量 |
| --- | --- |
| 2006 | 4 |
| 2007 | 11 |
| 2008 | 21 |
| 2009 | 52 |
| 2010 | 110 |
| 2011 | 257 |
| 2012 | 528 |
| 2013 | 1849 |
| 2014 | 3410 |
| 2015 | 5291 |
| 2016 | 6533 |
| 2017 | 7346 |
| 2018 | 8845 |
| 2019 | 13220 |
| 2020 | 16873 |
| 2021 | 19623 |
| 2022 | 21461 |
| 2023 | 5577 |

不可解析时间：0；超出 [1996-01-01, 2023-10-01) 官方采集窗口：0。

# Product Coverage

交互唯一 parent_asin：2839；metadata 唯一 parent_asin：10000；唯一 user_id：94003。

asin 数量：不存在/无法计算；asin 与 parent_asin 关系：不存在/无法计算。

每个有效 parent_asin 的 interaction 数量分布：

| 统计量 | 值 |
| --- | --- |
| count | 2839 |
| min | 5 |
| max | 1275 |
| mean | 39.1021486438887 |
| p25 | 7.0 |
| p50 | 14.0 |
| p75 | 30.0 |
| p95 | 143.0999999999999 |
| p99 | 496.33999999999924 |

metadata 中没有所选 5-core 交互的记录：7161。这不等于零需求，可能只是被 5-core 用户/商品筛选排除。

# Review / Interaction Quality

| 原始 rating | 数量 |
| --- | --- |
| 1.0 | 8077 |
| 2.0 | 4363 |
| 3.0 | 7195 |
| 4.0 | 13524 |
| 5.0 | 77852 |

非法非空 rating：0；评分缺失率：0.0000%。

verified_purchase 比例：不存在/无法计算。

helpful_vote 分布：不存在/无法计算。

5-core 已由官方进行重复交互处理；本项目仍检查完全相同的行，不假定官方处理后必然无重复。

# Metadata Quality

商品记录数：10000；price 缺失率：44.0800%；average_rating 缺失率：0.0000%；rating_number 缺失率：0.0000%。

store 缺失率：1.4300%；顶层 brand：不存在；details.Brand 内容缺失率：26.1100%。

非法非空 price（无法转数值、非有限值或 ≤ 0）：0。

price 分布（全部可解析有限值，异常未删除）：

| 统计量 | 值 |
| --- | --- |
| count | 5592 |
| min | 0.9 |
| max | 6099.0 |
| mean | 82.51082618025751 |
| p25 | 14.99 |
| p50 | 26.17 |
| p75 | 59.99 |
| p95 | 289.99 |
| p99 | 1078.0445000000002 |

categories 内容缺失率：0.0000%；出现的层级标签数：564。

以下标签跨层级计数，单商品可计入多个标签：

| categories 标签（前 20） | 记录数 |
| --- | --- |
| Patio, Lawn & Garden | 9988 |
| Gardening & Lawn Care | 2812 |
| Outdoor Décor | 2810 |
| Patio Furniture & Accessories | 1258 |
| Outdoor Power Tools | 1109 |
| Replacement Parts & Accessories | 937 |
| Pots, Planters & Container Accessories | 762 |
| Plants, Seeds & Bulbs | 724 |
| Flags | 680 |
| Grills & Outdoor Cooking | 607 |
| Lawn Mower Parts & Accessories | 584 |
| Lawn Mower Replacement Parts | 506 |
| Pools, Hot Tubs & Supplies | 448 |
| Garden Sculptures & Statues | 421 |
| Watering Equipment | 365 |
| Outdoor Cooking Tools & Accessories | 362 |
| Parts & Accessories | 323 |
| Flowers | 291 |
| Patio Seating | 265 |
| Farm & Ranch | 246 |

main_category 实际分布（不要用它代替源文件类目或 categories 层级）：

| main_category | 记录数 |
| --- | --- |
| Amazon Home | 8342 |
| Baby | 6 |
| Automotive | 148 |
| Industrial & Scientific | 366 |
| None | 49 |
| AMAZON FASHION | 78 |
| All Beauty | 12 |
| Tools & Home Improvement | 585 |
| Arts, Crafts & Sewing | 22 |
| Sports & Outdoors | 102 |
| Office Products | 56 |
| Toys & Games | 49 |
| Pet Supplies | 90 |
| All Electronics | 21 |
| Health & Personal Care | 40 |
| Musical Instruments | 5 |
| Cell Phones & Accessories | 8 |
| Appliances | 4 |
| Grocery | 10 |
| Computers | 3 |
| Home Audio & Theater | 1 |
| Books | 2 |
| Amazon Devices | 1 |

# Missing Values

| 数据 | 字段 | 字段不存在 | null | 空白/空容器 | 总缺失 | 缺失率 |
| --- | --- | --- | --- | --- | --- | --- |
| reviews | user_id | 0 | 0 | 0 | 0 | 0.0000% |
| reviews | parent_asin | 0 | 0 | 0 | 0 | 0.0000% |
| reviews | rating | 0 | 0 | 0 | 0 | 0.0000% |
| reviews | timestamp | 0 | 0 | 0 | 0 | 0.0000% |
| metadata | main_category | 0 | 49 | 0 | 49 | 0.4900% |
| metadata | title | 0 | 0 | 0 | 0 | 0.0000% |
| metadata | average_rating | 0 | 0 | 0 | 0 | 0.0000% |
| metadata | rating_number | 0 | 0 | 0 | 0 | 0.0000% |
| metadata | features | 0 | 0 | 1305 | 1305 | 13.0500% |
| metadata | description | 0 | 0 | 3909 | 3909 | 39.0900% |
| metadata | price | 0 | 4408 | 0 | 4408 | 44.0800% |
| metadata | images | 0 | 0 | 1 | 1 | 0.0100% |
| metadata | videos | 0 | 0 | 4613 | 4613 | 46.1300% |
| metadata | store | 0 | 143 | 0 | 143 | 1.4300% |
| metadata | categories | 0 | 0 | 0 | 0 | 0.0000% |
| metadata | details | 0 | 0 | 67 | 67 | 0.6700% |
| metadata | parent_asin | 0 | 0 | 0 | 0 | 0.0000% |
| metadata | bought_together | 0 | 10000 | 0 | 10000 | 100.0000% |
| metadata | subtitle | 9998 | 2 | 0 | 10000 | 100.0000% |
| metadata | author | 9998 | 2 | 0 | 10000 | 100.0000% |

关键字段检查：

| 数据 | 关键字段 | 缺失率 |
| --- | --- | --- |
| reviews | parent_asin | 0.0000% |
| reviews | asin | 不存在/无法计算 |
| reviews | user_id | 0.0000% |
| reviews | timestamp | 0.0000% |
| reviews | rating | 0.0000% |
| metadata | parent_asin | 0.0000% |

# Duplicate Check

完全重复行（首条之外的记录）：reviews 0；metadata 0。

使用排序后的完整 JSON 表示比较，不仅依靠哈希；JSON 字段顺序不影响判定。

metadata 重复 parent_asin 的额外记录数：0。

# Review-Metadata Matching

按 parent_asin 匹配；匹配 interaction 行：111011/111011，行匹配率：100.0000%。

匹配唯一父商品：2839/2839，父商品匹配率：100.0000%。

该输入预先按 metadata 商品范围筛选，匹配率是流程完整性检查；不能据此宣称原始 Amazon 类目 metadata 全覆盖。

# Potential Problems

1. 5-core 仅保留活跃用户和商品，交互量与原始评论全集不同，存在选择偏差。
2. 固定 metadata 前 10,000 条有源文件排列偏差，不是类目随机样本。
3. asin、购买验证、helpful_vote 和评论文本缺失，无法分析变体或构造 verified review 目标。
4. price 缺失率为 44.0800%；价格、average_rating、rating_number 是采集时快照，不能直接作为历史预测特征。
5. 没有销售、库存、广告、上架/下架和价格历史；没有交互不能自动当成零需求。2023 年仅覆盖至数据采集截止时点，不能直接和完整年份比较。

# Stage 2 Recommendations

1. 先审查商品范围的代表性和历史覆盖；决定保留 5-core interaction proxy，还是扩充原始评论以获得 verified_purchase。
2. 明确缺失值、异常值和 metadata 唯一键的处理规则，再进行清洗；当前不自动删除。
3. 对商品 × 时间聚合，区分缺失观察和真实零值，检查月份覆盖及右截断。
4. 明确特征可用时点，防止采集快照和未来累计评分引入时间泄漏；采用时间切分。
5. 只有这些规则明确后才确定未来 interaction count 的代理目标；本阶段未训练模型。
