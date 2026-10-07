# Realtime Failure Diagnosis（离线证据）

本报告只复核已保存的两次采集证据，没有新增 Amazon 请求。requests 发生于 2026-10-07 08:45:20 UTC；Playwright 发生于同日 09:09:18 UTC，属于不同时间和客户端环境，不是受控 A/B 实验。

## A. requests 503：原始证据

来源：`data/realtime/raw/garden_hose_20261007T084520394324Z.html`（2,671 bytes，SHA-256 `470de24561f8fdb4c965acb40542fe9fad14e1843793a497a3bacd906d05544c`）、同名 `.response.json`、`outputs/realtime/execution_record.md`、`reports/realtime_source_analysis.md`。元数据记录 HTTP **503**、无重定向、final URL `https://www.amazon.com/s?k=garden+hose`、requests 默认 User-Agent `python-requests/2.32.5`。已收到真实 HTTP 响应，因此失败不在 DNS 解析或建立连接之前。

原始记录只保存了 Content-Type 的值，没有保存完整 response headers；原始文件字节数不能反推响应中的 Content-Length：

| Response header | 已保存的证据 |
| --- | --- |
| Server | 未保存/无法判断 |
| Content-Type | `text/html`（单独保存在 response metadata） |
| Content-Length | 未保存/无法判断；原始 body 实测 2,671 bytes |
| Retry-After | 未保存/无法判断 |
| Via | 未保存/无法判断 |
| Cache / X-Cache | 未保存/无法判断 |
| Location | 未保存/无法判断；元数据仅证实本次无重定向 |
| 其他错误、网关、CDN 相关响应头 | 未保存/无法判断 |

HTML `<title>` 为 `Sorry! Something went wrong!`。页面主体的错误图片 alt 文本写着 `Sorry! Something went wrong on our end. Please go back and try again`，另有首页/搜索入口。HTML 注释含 `To discuss automated access to Amazon data` 和 API 文档链接；这是模板中的通用注释，不能证明此次 503 因自动访问策略而产生。路径含 `cs_503`、图片名含 `500_503.png`，但页面正文**没有明确写出** `503` 或 `Service Unavailable`；503 数值来自 HTTP 元数据。未发现 CAPTCHA、Robot Check、`proxy`、`gateway`、`temporary unavailable`、`retry later` 的明确页面文字；“try again”不等于服务端给出了 Retry-After。页面也没有本次请求专属的封禁原因。

**故障层判断：HTTP 响应层（已确认），Amazon 品牌错误页面（已确认）；无法在 CDN/边缘服务与 Amazon 应用层之间精确定位。** 这不是 DNS/连接失败，因为已收到 503 和 HTML。它也不是已证明的访问控制：没有明确 CAPTCHA、Robot Check 或针对该请求的封禁文字。页面模板和注释最多提示应检查服务端/中间层及访问策略，不能确定触发机制。urllib3 当时报告 LibreSSL 版本 warning，但 TLS 请求已取得 HTTP 响应，不能把 warning 直接当成 503 根因。

## B. Playwright 成功：原始证据

来源：`data/realtime/raw/garden_hose_playwright_20261007T090918742000Z.initial.html`（最终文档初始 HTTP body，1,047,120 bytes）、同 stem `.html`（DOM，1,120,549 bytes）、`.png` 截图、`.navigation.json` 和 `outputs/realtime/playwright_probe_run.log`。截图显示 Amazon.sg 商品结果和“Choosing your Amazon website”网站选择弹窗；未点击。Amazon.sg 页面可见商品卡片、S$ 价格和评分，不要求登录才可读该次页面。

- Initial URL：`https://www.amazon.com/s?k=garden+hose`。
- 已保存的 document network：Amazon.com GET **302**；随后 Amazon.sg document GET **200**。navigation metadata 中 redirects 记录原 Amazon.com URL 的 302；最终浏览器 URL 为 `https://www.amazon.sg/s?k=garden+hose&ref=mr_direct_us_sg_sg`。网络中请求的 Amazon.sg URL 带 `ref_`/`showmri`，最终地址栏 URL 略有不同；不把这个差异猜成另一轮导航。
- 最终 marketplace：Amazon.sg；保存的页面 S$ 价格按 SGD 入库；navigation response status **200**；标题 `Amazon.sg : garden hose`；DOM loaded=True。无 CAPTCHA、Robot Check、403 或强制登录证据。
- 初始 HTML 与 DOM 都含 **48** 个搜索卡片；前 **20** 个目标字段离线解析完全相同。商品核心字段已在本次新加坡站初始 HTML 中，不能据此判断美国站正常页是否相同。

## C. 变量对照

| 变量 | requests | Playwright |
| --- | --- | --- |
| client | Python requests 2.32.5，默认 UA | Playwright CLI + 本机 Chrome，普通隔离上下文 |
| initial host | www.amazon.com | www.amazon.com |
| final host | www.amazon.com | www.amazon.sg |
| status | 503 | 200（前置 Amazon.com 302） |
| 保存的 HTML size | 2,671 bytes 错误 body | 1,047,120 bytes 初始商品 HTML；1,120,549 bytes DOM |
| 商品 | 0 | 页面候选 48，前 20 解析成功 |
| CAPTCHA | 未见 | 未见 |
| Robot Check | 未见 | 未见 |
| 站点 | 美国域名错误页 | 新加坡域名商品页 |

### CONFIRMED

两次请求的最终站点、状态码和页面类型不同。requests 从 Amazon.com 收到 503 品牌错误 HTML；Playwright 从 Amazon.com 经 302 到 Amazon.sg，再收到 200 商品 HTML。Playwright 成功的是**新加坡站**，没有证明美国站商品搜索可访问。错误发生在收到 HTTP 响应之后，不是本地 parser 或 SQLite 导致。新加坡站前 20 个商品字段在初始 HTML 已存在，因此本次商品提取不依赖 JS 创建核心卡片。

### LIKELY / POSSIBLE（未隔离验证）

客户端请求上下文和目标市场不同，任何一项都**可能**影响服务器结果，例如时间、地区/站点选择、会话 Cookie、请求头或服务端瞬时状态。既有证据缺少 requests 完整响应头、两条路径的可比请求头/会话以及同市场的配对结果，无法给这些可能性排序或选出单一根因。错误页的 automated access 注释可能提示某类访问政策，但只是模板文字。

### NOT PROVEN

不能声称“Amazon 一定封锁 requests”、IP 一定被封、User-Agent 或 Cookie 一定导致 503、JavaScript 是成功的必要条件、Playwright 绕过了反爬、503 一定来自某个 CDN/网关或 Amazon 应用子系统。也不能用新加坡站的成功率代替美国站的可用性。

## D. 面试回答（约 30–60 秒）

> 我先看 HTTP 层：requests 实际收到了 503 和 2,671 字节的 Amazon 错误 HTML，所以不是 DNS 或本地解析失败。我保存了原始响应；页面有通用的 automated access 注释，但没有 CAPTCHA 或针对这次请求的封禁原因，因此不能把 503 直接等同于反爬。之后的一次普通 Playwright 导航，从 Amazon.com 收到 302，实际落在 Amazon.sg，最终 200 并拿到商品。两次既换了客户端，又换了最终市场，无法据此说浏览器或 JS 解决了 503。下一步如果有合规的测试条件，我会用低频、同时间和同市场的配对请求，完整保存请求/响应头与重定向链，逐一控制变量；若网站明确限制自动访问，就停止直接页面采集，评估授权数据源。

**追问 1：怎么证明不是 requests 的 User-Agent 导致？** 目前不能证明，也不能说就是它。现有实验同时改变了客户端、时间和最终市场，并未保存完整可比请求头。需要在允许的测试条件下固定目标市场与其他条件，记录完整 HTTP 证据，再做低频单变量比较；本次不继续请求。

**追问 2：为什么不直接上代理？** 代理会改变网络位置与市场路由，增加变量，反而削弱根因分析；遇到明确访问限制时也不应借它规避。先保存证据、厘清授权与市场口径，必要时改用合规数据源。

**追问 3：为什么 Playwright 成功不能证明它“绕过了反爬”？** 浏览器结果是经 302 到 Amazon.sg 的 200，而失败请求停留在 Amazon.com；目标站点已经不同。没有看到可归因于反爬的明确拒绝原因，也没有同一目标市场的受控对照。成功只证明该次新加坡站页面可读。
