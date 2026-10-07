# Requests Result

Stage 2A：2026-10-07T08:45:20.394324+00:00，普通 requests GET Amazon.com garden hose。HTTP **503**，无重定向，final URL 为 https://www.amazon.com/s?k=garden+hose；原始错误 HTML **2671 bytes**；标题 `Sorry! Something went wrong!`；0 商品，0 商品入库。未见 CAPTCHA/Robot Check/403。HTML 注释提到自动访问支持，但 503 根因未确认。

原有 source_analysis、collection_v1、execution_record、503 HTML/response JSON 全部保留。

# Playwright Result

- 时间：2026-10-07T09:09:18.742Z；结束：2026-10-07T09:09:22.750Z。
- 已有 Playwright CLI 0.1.21 + 本机 Chrome，headed、默认隔离上下文；不导入个人登录 Cookie，不设置代理/自定义 User-Agent/stealth。未下载浏览器或安装依赖。
- 一次 page.goto，45 秒 DOM timeout；成功页最多等 10 秒既有 load，截图 timeout 10 秒。无刷新/额外接口调用。
- Initial URL：https://www.amazon.com/s?k=garden+hose。
- Navigation response status：**200**；redirect chain：[{'url': 'https://www.amazon.com/s?k=garden+hose', 'status': 302}]。
- Final URL：https://www.amazon.sg/s?k=garden+hose&ref=mr_direct_us_sg_sg；标题：Amazon.sg : garden hose；DOM loaded=True。
- DOM HTML：**1120549 bytes**；最终文档初始 HTTP body：**1047120 bytes**（不是 Amazon.com 的 302 body）。
- CAPTCHA=False；Robot Check=False；login_required=False；403=False；自动访问说明=False；导航错误=None。
- 截图可见网站选择弹窗（Visiting from Singapore?/Choosing your Amazon website）和底层商品；未点击返回美国站或其他按钮。普通 Sign in 入口并非强制登录。
- 全页候选卡片 **48**；只解析前 **20** 个；成功 **20**，去重后 **20**；重复 ASIN **0**。
- 实际站点 **www.amazon.sg**，币种 **SGD**，outcome=success_other_marketplace。浏览器成功不等于已取得 Amazon.com 美国站数据。

## Field Validation

| 字段 | 来源 / 本次解释 | 缺失数 / 分母 | 缺失率 |
| --- | --- | --- | --- |
| crawl_time | 导航前 UTC 时间 | 0 / 20 | 0.00% |
| keyword | 本次输入 garden hose | 0 / 20 | 0.00% |
| search_position | 前 20 个候选 DOM 顺序，非官方 Search Rank | 0 / 20 | 0.00% |
| asin | 卡片 data-asin，10 位大写字母/数字 | 0 / 20 | 0.00% |
| title | 卡片 h2 文本 | 0 / 20 | 0.00% |
| price | 卡片 .a-price 非删除价 .a-offscreen，S$ → SGD 数值；非历史价格 | 0 / 20 | 0.00% |
| rating | 星级 .a-icon-star-mini .a-icon-alt，1–5 | 0 / 20 | 0.00% |
| review_count | customerReviews 链接 aria-label 精确 ratings 数；非文本评论数量、非销量 | 0 / 20 | 0.00% |
| product_url | 卡片真实商品链接，保持 Amazon.sg 域名并标准化 /dp/ASIN | 0 / 20 | 0.00% |

页面可见的 (19.5K) 等是缩写，不能反推精确整数。本次同一链接 aria-label 实际有 `19,510 ratings` 等精确值，因此读取真实属性；没有伪造或四舍五入补数。若无精确属性且只见 K 缩写，仍保留 NULL 并记录转换问题。
转换问题：[]；非法 ASIN：0。

## Raw Evidence

- raw_file：`data/realtime/raw/garden_hose_playwright_20261007T090918742000Z.html`。
- initial_html_file：`data/realtime/raw/garden_hose_playwright_20261007T090918742000Z.initial.html`。
- screenshot_file：`data/realtime/raw/garden_hose_playwright_20261007T090918742000Z.png`。
- metadata_file：`data/realtime/raw/garden_hose_playwright_20261007T090918742000Z.navigation.json`。

## Network Observation

实际完成响应 129；resource types={'document': 2, 'stylesheet': 12, 'image': 72, 'script': 15, 'font': 21, 'xhr': 6, 'fetch': 1}；HTTP statuses={'302': 1, '200': 128}；failed requests=0。
仅被动记录页面自身请求；未批量调用内部接口。以下 contains product data 是有限的 HTML/JSON 结构标记检查，不代表接口公开授权或完全排除其他字段。Cookie 标记只表示该次请求是否携带自动生成的会话 Cookie，不记录 Cookie 值。

| endpoint（移除 query） | method | content type | 商品结构标记 | Cookie / Authorization |
| --- | --- | --- | --- | --- |
| https://www.amazon.sg/cross_border_interstitial_sp/mr-render | POST | text/html | False | True / False |
| https://m.media-amazon.com/images/G/01/csm/showads.v2.js | GET | application/x-javascript | False | False / False |
| https://www.amazon.sg/portal-migration/hz/glow/get-rendered-toaster | GET | text/html;charset=UTF-8 | False | True / False |
| https://www.amazon.sg/cross_border_interstitial_sp/mr-metric | POST | text/html | False | True / False |
| https://www.amazon.sg/cart/add-to-cart/patc-config | GET | application/json;charset=UTF-8 | False | True / False |
| https://www.amazon.sg/cart/add-to-cart/patc-template | GET | text/html;charset=UTF-8 | False | True / False |
| https://www.amazon.sg/cart/add-to-cart/get-cart-items | GET | application/json;charset=UTF-8 | False | True / False |

初始文档候选数 48；初始 HTML 与 DOM 前 20 个商品的全部目标字段解析结果一致=True。核心字段来源判定 **initial_html**；本次新加坡页不需要等待 JS 才能获得这些核心商品字段。不能由此推断美国正常页面，也不能推断页面所有功能不需要 JS。

未发现经本次响应验证、适合直接使用的商品数据 API。看到的 XHR 为跨站提示、地区提示和购物车配置/模板/空列表等；部分携带会话 Cookie，未观察到 Authorization 请求头，不能据此证明接口不需要会话或具备公开采集许可。

## SQLite

- 新增商品 snapshot：20；本次记录商品 20；总商品 20；collection_runs 共 2。
- collection_runs 追加 collection_method（旧记录 requests，本次 playwright）、marketplace、currency；旧字段保留，新旧审计不覆盖。商品通过 crawl_time+keyword 外键关联实际站点和币种，不把 SGD 当 USD。
- 商品唯一键 UNIQUE(crawl_time,keyword,asin) 保留；一个 run 对应一个实际市场；查询必须 JOIN collection_runs 并筛选 marketplace/currency。未将 ASIN 设为跨时间唯一主键。
- integrity_check=ok；外键错误=[]；重复键=0；实际值与解析行一致=True。实际 SELECT 前五行及 typeof/PRAGMA 见本次 verification.json。

# Comparison

requests 是美国域名的 503 错误页；Playwright 经美国域名 302 自动转到新加坡站 200 商品页。两次时间、浏览器协议栈、Cookie、响应市场等上下文不同，不能把差异归因于 JavaScript，也不能声称 Playwright 绕过了 503。没有第二次导航验证美国站，也没有更改地区、登录或访问控制。

# Source Decision

对于当前 **Amazon.com 美国站** 目标：暂停扩大直接页面采集；优先评估满足使用条件、市场覆盖和授权要求的官方/合法数据来源，或先确认可接受的目标市场。不要为了保持美国站而改代理、地区参数或浏览器指纹。
Playwright 在本次只提供一次浏览器侦察和证据保存，不能据此强行将其选为生产采集器。若以后明确选择新加坡站，已保存的初始 HTML 足以支持离线解析；普通 requests 能否获取同等成功页仍未测试，直接商品 API 也未验证。不继续网络测试或 Stage 2B。

当前三个主要问题：目标市场发生重定向；选择器仅单页验证、未来稳定性未知；只有单次快照且 ratings 口径/地区/广告等上下文需要可比性约束。

search_position ≠ Amazon 官方 Search Rank；review_count ≠ sales；当前 price ≠ 历史 price；单次 snapshot 不能证明趋势；2026 新加坡快照不回填历史美国建模特征。

探针离线处理 exit code **0**；0 仅表示证据保存、解析入库及校验完成，不表示美国站采集成功。
