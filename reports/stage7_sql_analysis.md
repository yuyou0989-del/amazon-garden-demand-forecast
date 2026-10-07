# Stage 7A：Realtime SQLite SQL Analysis

数据库：`data/realtime/amazon_garden_realtime.db`；SQLite 3.51.0。以只读模式执行，分析前后数据库 SHA-256 相同。
`collection_runs` 有 2 条运行审计；商品表有 1 个有效快照、20 行商品。失败运行不计为商品快照。
运行审计：HTTP 200 / success_other_marketplace: 1 次；HTTP 503 / source_unavailable: 1 次。

## A. 当前快照概况

每个 keyword + marketplace + currency 取最后一个有商品的 crawl_time；SQL AVG/MIN/MAX 跳过 NULL，另列非空样本数。
| keyword | marketplace | currency | crawl_time | products | priced | avg_price | min_price | max_price | rated | avg_rating | review_count known | avg_review_count |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| garden hose | amazon.sg | SGD | 2026-10-07T09:09:18.742Z | 20 | 20 | 73.41 | 30.01 | 145.43 | 20 | 4.31 | 20 | 12,639.15 |

## B. 当前搜索结果前 10 个商品

按 search_position 升序；这里的位置只是该次采集到的搜索结果卡片顺序。
| position | asin | title | price | rating | review_count |
|---:|---|---|---:|---:|---:|
| 1 | B0DZSGJ9FD | Flexi Hose Expandable Garden Hose with 8 Function Nozzle, 25FT - Lightweight Retractable Garden Hose, Water Hose - No-Kink Flexibility, 3/4 Inch Solid Brass Fittings and Double Latex Core | 68.61 | 4.1 | 19510 |
| 2 | B0FTZWS873 | Flexi Hose with 8 Function Nozzle, 50FT - Lightweight Expandable Garden Hose, No-Kink Flexibility, 3/4 Inch Solid Brass Fittings and Double Latex Core - Black and Green | 77.96 | 4.2 | 1258 |
| 3 | B0DRK9P1VG | Heavy Duty 5/8 in (5/20.3 cm) Garden Hose, 7.6 m Flexible Water Hose, Lightweight Bend Resistant Hybrid Hose, Leak Proof Hose, Male to Female Fittings, Safe for | 30.01 | 4.4 | 1752 |
| 4 | B00HPXVA8G | GARDENA 18066-20 Hose, Comfort HighFLEX 0.5 inch (13 mm) (1/2 inch) Inner Diameter 98.8 ft (30 m) Length | 81.38 | 4.6 | 25168 |
| 5 | B000NUTNOG | Gardena 4647-U 33-Foot Spiral Coil Garden Hose and Nozzle Set | 84.36 | 4.3 | 2159 |
| 6 | B01MTAQKR1 | Flexzilla Garden Hose Kit with Quick Connect Attachments, 1/2 in. x 50 ft., Heavy Duty, Lightweight, ZillaGreen - HFZG12050QN | 54.08 | 4.3 | 2702 |
| 7 | B0DZSK67T3 | Flexi Hose with 8 Function Nozzle, 152 cm – Lightweight Expandable Garden Hose, Flexible Without Knot, 3/4 Inch Solid Brass Fittings and Double Latex Core | 76.66 | 4.1 | 19510 |
| 8 | B0DP3PXS3H | Pocket Hose Head UV w/Pocket Pivot, Expandable Garden Hose 25 FT w/10 Pattern Thumb Sprayer AS-SEEN-ON-TV 650psi 3/4in Ultra-Light Solid Copper Anodized Aluminum Fittings No-Kink No-Lead, Black | 62.88 | 4.2 | 16622 |
| 9 | B0D5B62DTP | Garden Hose Reel 14M, Compact & Portable Hose Pipe Reel with 7 Adjustable Spray Gun Nozzles, Manual Retractable Garden Water Hose Reel,Outdoor Flexible Hose Reel Set for Garden Patios and Balconies | 60.33 | 4.2 | 700 |
| 10 | B0DPZKMKWV | Kohree 75 FT RV Water Hose, 5/8" Premium Drinking Water Hose, Leak Free, No Odor, No Kink, 75 Foot Garden Hose with Storage Bag, Ideal for RV, Camper, Garden - Blue | 92.45 | 4.3 | 34 |

## C. 当前价格区间

先检查本次真实价格：最小 30.01、最大 145.43 SGD；现有 20 个价格中 50–100 区间较密集，故为当前 SGD 快照用 <50、50–<75、75–<100、>=100 四档；SQL CASE 另设 Unknown，未知价格不填 0。
| price band (SGD) | products | rated | avg_rating | review_count known | avg_review_count |
|---|---:|---:|---:|---:|---:|
| <50 | 2 | 2 | 4.70 | 2 | 877.00 |
| 50–<75 | 9 | 9 | 4.26 | 9 | 10,996.44 |
| 75–<100 | 8 | 8 | 4.30 | 8 | 18,850.38 |
| >=100 | 1 | 1 | 4.20 | 1 | 1,258.00 |

## D. 多快照变化

查询以 `(keyword, marketplace, asin)` 分组，用 SQLite `LAG()` 取前次记录；变化量均为当前值减前次值。若币种变化，price_change 为 NULL。位置差值为正表示卡片顺序数字变大。
当前真实变化结果：0 行。当前数据不足以进行真实趋势分析。

## 结论与证据边界

当前可以描述这一次 Amazon.sg / SGD 搜索结果的展示价格、评分、评价量和卡片顺序，以及各价格档的样本聚合；这只是本次页面快照。
review_count ≠ sales；search_position ≠ Amazon 官方 Search Rank；单次 snapshot 不能证明趋势；当前 Amazon.sg / SGD 结果不能直接代表 Amazon.com。所有 SQL 结果只基于现有真实 SQLite 商品行，没有伪造快照。
今后若同一 keyword、marketplace、asin 有多个可比采集时点，变化查询可描述展示价格、卡片位置和评价量的观测差值；这仍不能单独证明销量或变化原因。
