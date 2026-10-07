# Goal

验证 Amazon Garden 实时竞品采集的最小链路：数据源侦察 → 单页普通采集 → 保守解析与校验 → SQLite 快照/运行审计。最多 20 个候选商品，不追求规模，不做 EDA、模型或定时任务。

# Source Analysis

来源 `https://www.amazon.com/s?k=garden+hose`。技术保留 requests + BeautifulSoup；本次仅侦察 GET 一次，再用 collector --replay 处理同一真实响应，防止在错误响应后重复访问。详细证据见 realtime_source_analysis.md。

本次 outcome：**source_unavailable**。响应类型 text/html；页面标题 Sorry! Something went wrong!。CAPTCHA=False、Robot Check=False、403=False。失败层为 HTTP/页面响应；503 根因未验证，未用浏览器、API、代理或身份切换进行后续尝试。

# Collection Result

- 请求时间 UTC：2026-10-07T08:45:20.394324+00:00；Asia/Shanghai：2026-10-07T16:45:20.394324+08:00。
- keyword：garden hose。
- HTTP 状态：503；final URL：https://www.amazon.com/s?k=garden+hose。
- 页面候选数：0；选取候选数：0（上限 20）。
- 成功解析商品数：0；去重后：0。
- 该次 collector 执行是否发起请求：False（离线处理本次真实侦察响应）。
- 错误：['http_503']。
- 原始响应：`data/realtime/raw/garden_hose_20261007T084520394324Z.html`；响应元数据：`data/realtime/raw/garden_hose_20261007T084520394324Z.response.json`。
- raw SHA-256：`470de24561f8fdb4c965acb40542fe9fad14e1843793a497a3bacd906d05544c`；实际响应 2671 字节。

# Data Quality

| 字段 | 缺失数量 | 统计分母 | 缺失率 |
| --- | --- | --- | --- |
| crawl_time | 0 | 0 | 无法计算（无商品） |
| keyword | 0 | 0 | 无法计算（无商品） |
| search_position | 0 | 0 | 无法计算（无商品） |
| asin | 0 | 0 | 无法计算（无商品） |
| title | 0 | 0 | 无法计算（无商品） |
| price | 0 | 0 | 无法计算（无商品） |
| rating | 0 | 0 | 无法计算（无商品） |
| review_count | 0 | 0 | 无法计算（无商品） |
| product_url | 0 | 0 | 无法计算（无商品） |

没有商品，所以字段缺失率无法计算；不把无结果误写为零缺失或 100% 缺失。候选 ASIN 缺失率：None；非法 ASIN 候选数 0；duplicate ASIN 数 0。转换异常：[]。

位置按卡片顺序转整数；ASIN 严格校验；价格不明保留 NULL；rating 范围校验；评价数仅转换明确整数；URL 验证 Amazon.com 域名和对应 ASIN后标准化。同次重复 ASIN 保存首次出现位置。以上成功商品分支尚无真实商品可验证，不使用模拟商品证明成功。

# Storage

SQLite：`data/realtime/amazon_garden_realtime.db`。

```sql
search_snapshots(
  id INTEGER PRIMARY KEY,
  crawl_time TEXT NOT NULL,
  keyword TEXT NOT NULL,
  search_position INTEGER NOT NULL,
  asin TEXT NOT NULL,
  title TEXT,
  price REAL,
  rating REAL,
  review_count INTEGER,
  product_url TEXT,
  UNIQUE(crawl_time, keyword, asin)
)
```

实际本次写入 search_snapshots：**0 行**，storage_status=already_recorded。collection_runs 单独保存真实 HTTP 状态、raw 路径、质量统计和失败原因；这不是商品数据。相同请求重放以 crawl_time+keyword 判定已记录，避免重复运行审计；不把 asin 设成跨时间唯一主键。

不同 crawl_time、不同 keyword 可以保存同一 ASIN；V1 当前仅 garden hose，keyword 维度为后续兼容保留。搜索快照关联其采集运行。失败响应不会向商品表插入 NULL ASIN 占位行。

# Business Meaning

未来成功快照可用于监控同类商品、比较当前价格和展示评分/评价量、跟踪可识别搜索卡片位置变化。需要同一市场/上下文的重复快照，并保留广告、地点和页面规则等限制。

与历史需求热度模型只能做明确时点的补充分析：历史 Amazon Reviews 数据用于历史时间序列和之后的模型训练；实时数据用于未来竞品快照。当前 ASIN 与历史 parent_asin 的对应关系尚未验证，2026 年快照不能回填为 2020–2022 年历史特征，禁止修改既定历史建模口径。

# Evidence Boundary

- search_position ≠ Amazon 官方 Search Rank。
- review_count ≠ sales。
- 当前 price ≠ 历史 price。
- 单次 snapshot 不能证明趋势，需要多个时间点的可比采集才能分析变化。
- 本次没有取得任何商品，不能做价格、排名、评价量或竞品趋势结论。
- 错误页和失败审计保留为真实工程结果，不伪造成功数据。

运行出口：collector exit code **3**。3 表示采集源不可用，不能写成成功 exit 0；数据库/原始响应/字段验证审计另行执行。当前只能推进失败审计与离线重放维护，未具备成功商品采集的工程化依据。


## Realtime V1 最终补充：已保存的 Playwright 成功页面

本节是 **2026-10-07T09:09:18.742Z 的另一条运行记录**；上文 503 和 0 商品只描述更早的 requests 运行，保留原始失败审计。浏览器从 Amazon.com 收到 302 后到达 Amazon.sg，最终 HTTP 200；本节离线读取已保存的 `garden_hose_playwright_20261007T090918742000Z.initial.html`，没有再次访问 Amazon。

该 HTML 有 48 个候选卡片；只解析前 20 个，成功 20 个，重复 ASIN 0。`search_snapshots` 本次快照 20 行、全表 20 行，全部标记 `marketplace=amazon.sg`、`currency=SGD`、`collection_method=playwright`；price/rating 为 SQLite REAL，review_count 为 INTEGER。保留的九个商品字段与新增三个上下文字段的缺失率在这 20 行中均为 0%。本次完整 ratings 数从页面链接的 `aria-label` 读取；不把页面可见的 K 缩写猜成精确值，也不把 ratings 数当销量。SQLite 完整性检查为 ok，外键检查为空。

离线复跑命令：`python3 -B -m src.realtime.replay_saved_html --html data/realtime/raw/garden_hose_playwright_20261007T090918742000Z.initial.html`；重复运行核对同一 20 行，不增加快照。最终退出码 **0**，仅表示本次离线解析、字段入库与验证完成；美国站的实时商品采集尚未成功验证。503 与成功页的差异及证据边界见 `reports/realtime_failure_diagnosis.md`。
