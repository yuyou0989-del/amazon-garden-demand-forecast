# Amazon requests 503 根因控制变量实验

实验时间：2026-10-07 09:40:36–09:40:54 UTC；关键词固定 `garden hose`。本次人工发起 **4 次**顶层实验（A/B 各一次 requests GET，C/D 各一次 `page.goto`）；没有重试、刷新、代理、stealth、CAPTCHA 处理或额外商品入库。浏览器按页面正常加载资源；HTTP 自动跳转和页面自身的后续文档请求另外记录，**不能把 4 次人工发起误写成整个浏览器会话只有 4 个底层 HTTP 请求**。四组分别使用新 requests Session 或新 Chrome 浏览器 context；网络环境未主动切换。两次 requests 间约 3.6 秒，其余开始时点见各 metadata。

| Experiment | Client | Requested Market | Final Market | Status | Products | Result |
| --- | --- | --- | --- | ---: | ---: | --- |
| A | requests 2.32.5 | amazon.com | amazon.com | 503 | 0 | 2,671-byte Amazon 错误页 |
| B | requests 2.32.5 | amazon.sg | amazon.sg | 503 | 0 | 521-byte `Website Temporarily Unavailable` |
| C | Playwright + 本机 Chrome | amazon.com | amazon.sg | 200 | 48 候选 | 先 302，再新加坡商品页 |
| D | Playwright + 本机 Chrome | amazon.sg | amazon.sg | 200 | 48 候选 | 直接新加坡商品页 |

## 原始证据与每组路径

证据根目录：`data/realtime/diagnostics/`。每组独立目录保存 `response.body`、`response_metadata.json`、`redirect_chain.json`、`headers.json`；C/D 另有 `dom.html` 和 `screenshot.png`。headers.json 保留实际获取的完整响应头，报告仅列诊断字段，不公开 Cookie 值。四组 body SHA-256 均与 metadata 一致，截图与 DOM 已实际查看，正式 `search_snapshots` 仍为 20 行、`collection_runs` 仍为 2 行，旧 requests 原始 503 HTML SHA 未变。

- **A**：`www.amazon.com/s?k=garden+hose` → **503**，无重定向；标题 `Sorry! Something went wrong!`，错误图片 alt 含 `Something went wrong on our end`。HTML 注释提到 automated access/API，是通用模板文字；没有 CAPTCHA、Robot Check 或针对本请求的明确封禁说明。
- **B**：`www.amazon.sg/s?k=garden+hose` → **503**，无重定向；标题和图片 alt 为 `Website Temporarily Unavailable`。没有 CAPTCHA、Robot Check 或明确访问控制文字。
- **C**：`www.amazon.com/s?k=garden+hose` → **302**（Location 指向 Amazon.sg）→ `www.amazon.sg/s?...showmri` **200**（`AkamaiGHost`，Content-Length 1428，Set-Cookie 名 `ak_bmsc`）→ 同站搜索文档再次 **200**（Set-Cookie 名 `session-id`），最终浏览器地址为 `https://www.amazon.sg/s?k=garden+hose&ref=mr_direct_us_sg_sg`。第一次 Amazon.sg 200 之后的同站文档请求不是 HTTP 3xx；仅调用过一次 `page.goto`，后续请求由页面/浏览器发起，确切机制无法凭已保存证据确定。原始事件列表还包含一条 media-amazon GIF，被诊断捕获器归进 document 事件；`redirect_chain_reviewed.json` 单独校正搜索文档列表，原记录保留。`page.goto` 返回的 `response.body()` 为 **0 bytes**，不能用它判断最终页面无商品；最终 `dom.html`（1,062,771 bytes）和截图直接显示 48 个候选商品。此组中最终完整 HTML 响应体未单独保存，不能假称 body 大小等于 DOM 大小。
- **D**：`www.amazon.sg/s?k=garden+hose` → **200**，无重定向；最终响应 body **1,040,406 bytes**，DOM **1,095,716 bytes**，标题 `Amazon.sg : garden hose`，48 个候选商品。C/D 均未见 CAPTCHA、Robot Check、强制登录或明确访问限制。

## HTTP 诊断字段

| 组／响应 | Server | Content-Type | Content-Length | Location | Retry-After | Via | X-Cache | Set-Cookie |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A 503 | `Server` | `text/html` | 无 | 无 | 无 | CloudFront | `Error from cloudfront` | 无 |
| B 503 | `Server` | `text/html` | 无 | 无 | 无 | CloudFront | `Error from cloudfront` | 无 |
| C Amazon.com 302 | `Server` | 无 | `0` | Amazon.sg `...showmri` | 无 | CloudFront | `Miss from cloudfront` | 无 |
| C Amazon.sg 首个 200 | `AkamaiGHost` | `text/html` | `1428` | 无 | 无 | 无 | `NotCacheable from child` | `ak_bmsc` |
| C Amazon.sg 后续 200 | `Server` | `text/html;charset=UTF-8` | 无 | 无 | 无 | 无 | `NotCacheable from child` | `session-id` |
| D Amazon.sg 200 | `Server` | `text/html;charset=UTF-8` | 无 | 无 | 无 | CloudFront | `Miss from cloudfront` | `session-id` |

“无”表示**本次完整响应头中不存在**，不同于旧 Stage 2A 没保存 header。A/B 均有 `x-amz-rid`、`edge-cache-control: no-store,no-cache,stale-if-error=0,stale-while-revalidate=0`、`X-Amz-Cf-Pop`；A 为 SIN52-P1，B 为 SIN2-P2。D 200 也经过 CloudFront，POP 为 SIN2-P2。A/B 的 `X-Cache: Error from cloudfront` 与 `Via: CloudFront` 确认 CDN 路径标记了错误，**不能单凭头部证明 503 由 CloudFront 自身生成还是转发上游错误**。HTTP body 传输可能经过解压，保存的 body 字节数不应反推 Content-Length。

请求 Cookie：C 的 Amazon.com 302、首个 Amazon.sg 200 及 D 的直接 Amazon.sg 200，浏览器诊断记录为未携带 Cookie；C 后续同站 200 请求带 Cookie。requests A/B 使用新 Session，响应中未见 Set-Cookie；当时未完整保存 requests 发出的请求头，因此只确认默认 `python-requests/2.32.5` User-Agent，不推断更多请求差异。出现 `ak_bmsc` 这个 Cookie 名、`AkamaiGHost` 或 CDN 差异本身，均不足以证明特定安全机制触发。没有手动修改 Cookie 或登录。

## 控制变量分析

1. **同一最终 marketplace：**直接 Amazon.sg 的 B=requests 503、D=Playwright 200，是本实验最有价值的对照。目标站点和关键词相同，客户端/请求上下文与时间仍不同。C 最终也是 Amazon.sg 200，但路径先经 Amazon.com 302 及站点提示，不是与 B 完全同一路径。
2. **同一 client 的市场差异：**requests A(com)=503、B(sg)=503，因此失败并非只在 Amazon.com 出现。Playwright C 请求 com 会自动转 sg，D 直接 sg；两者最终均成功于 sg，**没有**获得 Playwright 留在 com 的商品响应，不能比较它在两个最终市场上的成功率。
3. **503 是否只在 Amazon.com：**否，B 在 Amazon.sg 也 503。
4. **requests 在 Amazon.sg：**一次 503，521-byte 临时不可用页。
5. **Playwright 访问 Amazon.com 是否“必然”转 sg：**本次 C 以及更早的单次探针都观察到 302，但样本不足以说“必然”。没有主动更改地域路由。
6. **503 头/body 是否给出内部根因：**CDN Via/X-Cache、错误模板和两个不同 Amazon 页面可见；没有具体访问拒绝代码、Retry-After、CAPTCHA 或 Robot Check。上游、边缘、策略及瞬时故障未能隔离。
7. **Cookie／redirect／marketplace：**C 的 .com 有 302，A 没有；B/D 都直达 .sg 却一败一成。D 首次 .sg 请求不带 Cookie 仍成功，所以“必须先有 Cookie 才能成功”不受本次 D 支持；但其余浏览器请求差异没有逐项控制。

### CONFIRMED ROOT CAUSE

**Amazon 内部为什么返回 503：未确认。** 可以确认的是失败发生在 HTTP 响应层，绝非本地解析器或 SQLite 造成；A/B 的 503 都通过 CloudFront 路径返回。内部生成点和决策条件没有外部直接证据。

### STRONGLY SUPPORTED

在这组相近时间、同一请求市场 `amazon.sg` 的直接访问中，**客户端/浏览器请求上下文与结果高度相关**：B=requests 503，D=Chrome 200。A 也 503、C 经跳转后 200，方向一致。“仅 Amazon.com 市场导致 503”被 B 否定。关联不等于证明 User-Agent、TLS、Cookie、IP 或某个反爬规则是根因。

### POSSIBLE

请求头/默认 UA、TLS/HTTP 协议表现、会话状态、CDN/上游路由及服务器短时状态都可能影响结果。A/B 错误经 CloudFront，C 曾收到带 `ak_bmsc` 的 Akamai 页面，再取得商品页；这些是排障线索，非内部机制证明。本实验未完整保存 requests 发出头，也未测公网出口 IP，无法单独排除某项网络差异。

### RULED OUT / NOT SUPPORTED

- **不支持**“503 只发生在 Amazon.com”；B 是 Amazon.sg 503。
- **不支持**“HTML 解析失败导致 503”或“没有 JS 就必然无法在新加坡站拿到商品”；HTTP 状态先于解析，之前已保存的成功 Amazon.sg 初始 HTML 包含商品字段。
- **不支持**把 CAPTCHA/Robot Check 当成本次四组已观察到的明确拒绝方式；均未出现。
- **不能声称** Amazon 确定封锁 requests、封了 IP、User-Agent 一定是原因、Cookie 一定是原因，或 Playwright 绕过了反爬。没有实施代理、伪装、绕过或额外试探。

**最终结论：**已定位到同一目标市场下的客户端/请求上下文层面稳定的**本次差异**，并排除“只有 Amazon.com 会 503”的简单解释。仅四次人工发起请求不足以证明长期稳定性，也不能从外部确认 Amazon 内部为何返回 503。

## Interview Debugging Story

**现象与任务：**最初普通 requests 请求 Amazon.com 搜索返回 503，随后 Playwright 经 302 到 Amazon.sg 得到商品。初始假设包括市场路由、客户端请求上下文和服务端瞬时故障；503 只是 HTTP 错误，不能立刻叫“反爬”。

**行动与证据：**保存原始 HTML、完整本次响应头、重定向链、浏览器截图和 DOM。设计 2×2：同一关键词、requests 与本机 Chrome、分别请求 Amazon.com 和 Amazon.sg，每组一次、独立会话，近时间完成，失败后不重试。结果 A/B=503，C/D=200；C 经 302 到 sg，B/D 的直接 sg 对照最关键。A/B 都带 CloudFront Error 标记；C/D 有正常商品。未更改代理、指纹或地区设置。

**结果与边界：**排除市场单独解释和本地解析错误；支持“客户端/请求上下文与结果相关”，但浏览器与 requests 同时在多项协议和头部上不同，无法认定内部策略、UA 或 IP。生产环境下一步先按 marketplace 与 client 监控 HTTP 状态、重定向和 X-Cache，保留有限原始错误样本；如有授权的受控测试环境，可同时间同目标单变量比较完整请求/响应头，否则评估授权数据源。遇明确限制则停止直接页面路径。

### 30秒版本

> 我没有把 503 直接判成反爬，而是保存了错误 body、响应头和重定向。四组近时间测试中，requests 对美国和新加坡站都 503；普通 Chrome 从美国站跳新加坡站后 200，直达新加坡站也 200。最关键是同一个新加坡站，requests 失败、浏览器成功，所以市场本身解释不了全部差异。两次 503 的 X-Cache 都是 `Error from cloudfront`，但这不证明 CloudFront 是内部根因。我们定位了客户端请求上下文关联，尚不能说是 UA、Cookie、IP 或某条反爬规则。

### 90秒深挖版本

> 最初 requests 访问 Amazon.com 得 503，而 Playwright 最终显示 Amazon.sg 商品。一个常见误判是“requests 被封、浏览器绕过了”，但两条路径的最终站点不同，而且没有明确访问控制证据。我先留存响应体、HTTP 头、截图与链路，并固定关键词做 2×2：requests 与 Chrome，分别发起一次 Amazon.com 和 Amazon.sg，全部普通默认设置、不重试。A 和 B 都 503，A 是 Amazon 错误模板，B 是 521 字节临时不可用页；C 从 .com 302 到 .sg，D 直达 .sg，浏览器最终都取得 48 个商品候选。B 与 D 的请求市场、最终市场相同，状态却不同，说明这次客户端或其请求上下文与结果高度相关，市场单独解释被否定。A/B 的 Via 都指向 CloudFront，X-Cache 为 Error from cloudfront；D 的 X-Cache 是 Miss from cloudfront。C 中间还有一个带 `ak_bmsc` Cookie 的 AkamaiGHost 响应，但不能据此说具体哪个安全组件拒绝 requests。我们没完整比较请求头、TLS 或出口 IP，也没做同一时点重复测量，所以不能证明内部规则。生产上我会按市场和客户端监控 503，保存有限原始错误证据，并在有授权的受控条件下逐项比较；若出现明确限制，就停止该路径，选择合规数据源。

**追问 1：为什么不能看到 503 就判断反爬？** 503 只表示这次 HTTP 服务不可用；可能来自边缘、上游或短时服务问题。本次没有明确 CAPTCHA、Robot Check、封禁原因或内部判定日志。

**追问 2：为什么 Playwright 成功不代表绕过反爬？** C 的最终市场变成 Amazon.sg；D 的同市场对照仅显示浏览器上下文关联成功，并未证明哪项浏览器特性或安全机制起作用。没有进行绕过动作。

**追问 3：怎么设计控制变量？** 固定关键词、时间窗口、网络与目标市场，分别改变 client 和 requested market，每组只一次，记录实际 final market、状态、头与重定向。该设计仍未固定所有请求头/TLS 和底层路由，所以只能作关联判断。

**追问 4：为什么不用代理直接解决？** 代理同时改变出口网络、地域和可能的路由，会扩大混杂变量，并可能绕过访问限制；与本实验定位根因和保持合规的目标相反。

**追问 5：503 和解析失败有什么区别？** 503 是服务器/中间层返回的 HTTP 状态，在本地 parser 运行前就可观察；解析失败通常发生在 2xx 页面已到手之后，会表现为候选数 0 或字段缺失，需保存原始 HTML 排查选择器。

**追问 6：线上突然大量 503 怎么监控和处理？** 按 requested/final market、client、状态和时间监控错误率及连续失败，抽样保留头/body/redirect/request ID，区分网络异常、503 与 2xx 解析异常。对明确限制立即停采；对偶发服务故障做受控退避和人工排查，避免自动高频重试，并评估官方授权数据源与业务降级方案。
