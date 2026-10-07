# Data Dictionary

只记录实际读取的字段。缺失 = 字段不存在、null、空白字符串、空列表或空字典。
CSV 原始 dtype 为 str；数值统计单独解析为数字，不改写原始数据。示例截断至 160 字符，完整前 5 行见 outputs/inspection_summary.json。

## reviews

| 字段名 | 数据类型（实际观测次数） | 含义 | 示例 | 缺失率 | 后续用途 |
| --- | --- | --- | --- | --- | --- |
| user_id | str: 111011 | 匿名用户标识 | "AFSKPY37N3C43SOI5IEXEK5JSIYA" | 0.0000% | ID |
| parent_asin | str: 111011 | 父商品标识；metadata 关联键 | "B08NP38C66" | 0.0000% | ID |
| rating | str: 111011 | 交互评分，合法整数等级 1–5 | "5.0" | 0.0000% | EDA |
| timestamp | str: 111011 | 评论发生时间，Unix 毫秒；展示统一使用 UTC | "1615921830551" | 0.0000% | 时间 |

## metadata

| 字段名 | 数据类型（实际观测次数） | 含义 | 示例 | 缺失率 | 后续用途 |
| --- | --- | --- | --- | --- | --- |
| main_category | str: 9951, NoneType: 49 | 商品页面记录的主类目，可能不同于数据文件分类 | "Amazon Home" | 0.4900% | EDA |
| title | str: 10000 | 商品标题 | "AISEN Carburetor AIR Filter Tune UP KIT for C1U-K43 Echo PB-2155 ES-2100 12520020660 12520020661 12520020662 12520020663 12520020664 12520020665" | 0.0000% | 潜在特征 |
| average_rating | float: 10000 | 采集时页面平均评分；有未来信息风险 | 3.8 | 0.0000% | EDA |
| rating_number | int: 10000 | 采集时页面累计评分数；有未来信息风险 | 8 | 0.0000% | EDA |
| features | list: 10000 | 商品卖点列表 | ["Fits for Echo PB-2155 Leaf Debris Blower ES-2100 Shredder", "Replaces for Echo 12520020660,12520020661,12520020662,12520020663,12520020664,12520020665", "Repl | 13.0500% | 潜在特征 |
| description | list: 10000 | 商品描述列表 | ["From the manufacturer", "Orbit is North America’s premier company for residential watering. With a presence in over 180 countries and 6 continents, we offer t | 39.0900% | 潜在特征 |
| price | float: 5592, NoneType: 4408 | 采集时商品页面价格，美元；不是历史价格序列 | 18.26 | 44.0800% | 潜在特征 |
| images | list: 10000 | 商品或评论图片对象列表 | [{"thumb": "https://m.media-amazon.com/images/I/51s-QQrfDGL._AC_US75_.jpg", "large": "https://m.media-amazon.com/images/I/51s-QQrfDGL._AC_.jpg", "variant": "MAI | 0.0100% | 暂不使用 |
| videos | list: 10000 | 视频对象列表 | [{"title": "Most affordable Smart Home Sprinkler Device on the Market. . . EASY TO USE!", "url": "https://www.amazon.com/vdp/96c59112ea7a49589e4ad59a4e049231?re | 46.1300% | 暂不使用 |
| store | str: 9857, NoneType: 143 | 页面店铺名称；不直接等同品牌 | "AISEN" | 1.4300% | EDA |
| categories | list: 10000 | 商品分类层级列表 | ["Patio, Lawn & Garden", "Outdoor Power Tools", "Replacement Parts & Accessories", "Lawn Mower Parts & Accessories", "Lawn Mower Accessories", "Tune-Up Kits"] | 0.0000% | EDA |
| details | dict: 10000 | 商品详情字典；可能含 Brand，不新增原始 brand 字段 | {"Package Dimensions": "4.57 x 3.03 x 1.34 inches", "Item Weight": "6.7 ounces", "Manufacturer": "AISEN", "Best Sellers Rank": {"Patio, Lawn & Garden": 302812,  | 0.6700% | 潜在特征 |
| parent_asin | str: 10000 | 父商品标识；metadata 关联键 | "B074C2TTV8" | 0.0000% | ID |
| bought_together | NoneType: 10000 | 页面推荐搭配商品 | 不存在/无法计算 | 100.0000% | 暂不使用 |
| subtitle | NoneType: 2 | 可选字段；本子集中观测值均为 null，语义暂不确认 | 不存在/无法计算 | 100.0000% | 暂不使用 |
| author | NoneType: 2 | 可选字段；本子集中观测值均为 null，语义暂不确认 | 不存在/无法计算 | 100.0000% | 暂不使用 |

## 不存在的重点字段

5-core 交互文件中没有 asin、verified_purchase、helpful_vote、评论 title/text。
metadata 没有顶层 brand；仅检查真实 details.Brand 的可用率，不把 store 假定为品牌。
