# Realtime Source Analysis

## 本次实际请求

| 项目 | 实际值 |
| --- | --- |
| URL / 页面类型 | https://www.amazon.com/s?k=garden+hose / Amazon.com 关键词搜索 |
| keyword | garden hose |
| 请求方式 | requests GET；默认 python-requests User-Agent，无浏览器身份伪装 |
| HTTP status | 503 |
| 请求收到响应 | True |
| HTTP 2xx 成功 | False |
| 重定向 | [] |
| final URL | https://www.amazon.com/s?k=garden+hose |
| Content-Type | text/html |
| 响应字节 | 2671 |
| 页面标题 | Sorry! Something went wrong! |
| CAPTCHA / Robot Check / 403 | False / False / False |
| 自动访问说明注释 | True |
| 搜索商品候选卡片 | 0 |

请求不使用登录、代理池、重试、指纹伪装、验证码处理。侦察是本次唯一一次实际网络请求；collector 通过 --replay 离线复用该响应，没有再次请求 Amazon。代码保留单次 live 入口，但本次未在限制后运行它。

## 初始 HTML 与 JavaScript

本次取得错误响应，没有可用的商品搜索 HTML。不能据此判断正常搜索页是否依赖 JS，也不能证明其商品数据接口存在或不存在。未执行浏览器加载/网络面板侦察；收到失败响应后停止对应网络尝试。

本次原始响应保存在 `data/realtime/raw/garden_hose_20261007T084520394324Z.html`，SHA-256 `470de24561f8fdb4c965acb40542fe9fad14e1843793a497a3bacd906d05544c`。观察到的失败层是 HTTP / 上游页面响应，不是商品清洗或 SQLite 异常。没有看到验证码和 Robot Check，不代表 Amazon 没有自动访问限制。503 的具体根因无法确认。

## 页面接口侦察与技术选择

错误 HTML 注释提示联系 Amazon 自动访问支持，并链接 Marketplace/Product Advertising API 文档；它没有提供本次 garden hose 商品的 JSON 数据，也不是可直接调用的无授权搜索接口。没有观察到页面加载中的商品数据接口，不能把“未验证”写成“没有接口”。未登录、未申请 API 凭证、未调用这些文档推荐的 API。

最终 V1 保留 **requests + BeautifulSoup**：普通请求已能保存真实服务器响应，足够验证低成本传输、失败停止与原始响应审计。此选择不代表 requests 商品采集已成功。没有证据要求浏览器渲染，也没有成功可用的直接 API，因此不为展示框架改用 Playwright/API；特别是不在失败响应后切换方式继续尝试。

## 字段来源与本次验证范围

本次没有实际商品字段。parser 的待验证提取规则为：候选 `[data-component-type="s-search-result"]`；ASIN 来自 data-asin；标题来自 h2；美元价格来自商品卡 .a-price 内的展示价格；rating 来自星级说明文本；评价量来自 customerReviews 链接内的明确整数；product_url 来自直接商品链接并标准化；位置来自候选卡片顺序；crawl_time/keyword 来自采集上下文。

这些选择器是后续真实成功页面的候选规则，不声称已通过真实商品页验证。原始错误页没有上述商品数据，成功提取能力当前仍未验证。不会用零商品结果证明解析器正确。

## 环境限制

侦察环境为 macOS Python 3.9.6，requests 2.32.5、BeautifulSoup 4.15.0 均已存在，无需安装。urllib3 给出 LibreSSL 2.8.3 的 NotOpenSSLWarning，完整保留在侦察执行输出中；没有隐藏 warning 或关闭 TLS 证书校验。该请求仍实际收到 HTTP 响应，不能直接把 503 归因于此 warning。
