# Realtime Data Dictionary

首轮 requests 503 没有商品；后续已保存的 Amazon.sg 200 页面可离线解析前 20 个商品。下表中 SQLite 商品字段的类型已用这 20 行实际值核对；新加坡站规则只经这一次成功页验证。

| 字段 | 数据类型 | 来源 | 业务含义 | 允许缺失 |
| --- | --- | --- | --- | --- |
| crawl_time | str / TEXT | 实际请求开始时间，UTC ISO 8601，带微秒 | 该次快照请求时点；重放保留原时点 | 否 |
| keyword | str / TEXT | 固定配置 garden hose | 采集关键词 | 否 |
| search_position | int / INTEGER | 前 20 个可识别候选卡片的 DOM 顺序，从 1 开始 | 本次结果卡片的位置，重复 ASIN 保存首次出现位置 | 否 |
| asin | str / TEXT | 候选卡片 data-asin；校验十位大写字母/数字 | 当前商品标识；不是已验证的 parent_asin | 否；无效候选拒绝并记录 |
| title | str / TEXT | 候选卡 h2 文本 | 当前展示商品标题 | 是 |
| price | float / REAL | 当前商品卡明确的展示价格；本次为 S$ | 本次 SGD 页面展示价，不含未展示的运费等，不是历史价格 | 是；未知不填 0 |
| rating | float / REAL | 商品卡星级描述，如 n out of 5 stars | 当前展示平均评分，校验 1–5 | 是 |
| review_count | int / INTEGER | 商品卡评价链接 aria-label 中的完整整数 ratings；无则仅接受页面完整整数 | 页面当前评分数量，不是文字评论数或销量 | 是；不猜测 K+ 等缩写 |
| product_url | str / TEXT | 直接商品链接；校验域名/ASIN并去跟踪参数 | 与本次站点一致的 https://www.amazon.sg/dp/ASIN；无法验证直接链接时 NULL | 是 |
| marketplace | str / TEXT | 最终页面域名，存为 amazon.sg | 当前快照所属站点，防止跨市场混算 | 成功快照否 |
| currency | str / TEXT | Amazon.sg 商品卡 S$ 显示，记录 SGD | price 的币种；没有换汇 | 成功快照否 |
| collection_method | str / TEXT | 本次运行元数据 playwright | 采集路径审计 | 成功快照否 |

search_position ≠ Amazon 官方 Search Rank。它仅在这次请求上下文、可识别卡片范围内有意义，可能包含广告，不等同自然搜索排名；不同地点、设备和排序设置可能影响结果。

price 是采集时当前展示价格，不是过去时间序列价格。review_count 是当前展示评价数量，不是销量。没有从结果卡获得 parent_asin 映射，不能直接把当前 ASIN 当成历史父商品关联键。

缺失率分母为实际进入字段清洗的商品行数；拒绝的无效 ASIN 候选另行统计候选缺失/非法数量。没有商品时缺失率为 NULL/无法计算，禁止写成 0%。转换异常、重复 ASIN 和拒绝原因记录在本次 result.json；原始页面保留，不修改。
