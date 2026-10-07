"""报告只使用本次真实响应及数据库结果；零商品的缺失率不能写成 0%。"""
from datetime import datetime
from zoneinfo import ZoneInfo

from src.realtime.config import REPORT_DIR, DATABASE_FILE
from src.reporting import table


def rates(result):
    return [[field,info['missing_count'],info['denominator'],
             f'{info["missing_rate"]:.2%}' if info['missing_rate'] is not None else '无法计算（无商品）']
            for field,info in result['missing_statistics'].items()]


def generate_reports(result,rows):
    REPORT_DIR.mkdir(exist_ok=True)
    success=result['outcome']=='success'
    observation='真实商品 HTML 已获取；本次字段是否可得以实际缺失率为准。' if success else (
        '本次取得错误响应，没有可用的商品搜索 HTML。不能据此判断正常搜索页是否依赖 JS，'
        '也不能证明其商品数据接口存在或不存在。未执行浏览器加载/网络面板侦察；收到失败响应后停止对应网络尝试。')
    source=f'''# Realtime Source Analysis

## 本次实际请求

| 项目 | 实际值 |
| --- | --- |
| URL / 页面类型 | {result['requested_url']} / Amazon.com 关键词搜索 |
| keyword | {result['keyword']} |
| 请求方式 | {result['request_method']}；默认 python-requests User-Agent，无浏览器身份伪装 |
| HTTP status | {result.get('status_code')} |
| 请求收到响应 | {result['response_received']} |
| HTTP 2xx 成功 | {result['http_success']} |
| 重定向 | {result.get('redirects',[])} |
| final URL | {result.get('final_url')} |
| Content-Type | {result.get('content_type')} |
| 响应字节 | {result.get('response_bytes')} |
| 页面标题 | {result['page_title']} |
| CAPTCHA / Robot Check / 403 | {result['captcha']} / {result['robot_check']} / {result['forbidden_403']} |
| 自动访问说明注释 | {result['automated_access_notice']} |
| 搜索商品候选卡片 | {result['candidate_count']} |

请求不使用登录、代理池、重试、指纹伪装、验证码处理。侦察是本次唯一一次实际网络请求；collector 通过 --replay 离线复用该响应，没有再次请求 Amazon。代码保留单次 live 入口，但本次未在限制后运行它。

## 初始 HTML 与 JavaScript

{observation}

本次原始响应保存在 `{result['raw_file']}`，SHA-256 `{result['raw_sha256']}`。观察到的失败层是 HTTP / 上游页面响应，不是商品清洗或 SQLite 异常。没有看到验证码和 Robot Check，不代表 Amazon 没有自动访问限制。503 的具体根因无法确认。

## 页面接口侦察与技术选择

错误 HTML 注释提示联系 Amazon 自动访问支持，并链接 Marketplace/Product Advertising API 文档；它没有提供本次 garden hose 商品的 JSON 数据，也不是可直接调用的无授权搜索接口。没有观察到页面加载中的商品数据接口，不能把“未验证”写成“没有接口”。未登录、未申请 API 凭证、未调用这些文档推荐的 API。

最终 V1 保留 **requests + BeautifulSoup**：普通请求已能保存真实服务器响应，足够验证低成本传输、失败停止与原始响应审计。此选择不代表 requests 商品采集已成功。没有证据要求浏览器渲染，也没有成功可用的直接 API，因此不为展示框架改用 Playwright/API；特别是不在失败响应后切换方式继续尝试。

## 字段来源与本次验证范围

本次没有实际商品字段。parser 的待验证提取规则为：候选 `[data-component-type="s-search-result"]`；ASIN 来自 data-asin；标题来自 h2；美元价格来自商品卡 .a-price 内的展示价格；rating 来自星级说明文本；评价量来自 customerReviews 链接内的明确整数；product_url 来自直接商品链接并标准化；位置来自候选卡片顺序；crawl_time/keyword 来自采集上下文。

这些选择器是后续真实成功页面的候选规则，不声称已通过真实商品页验证。原始错误页没有上述商品数据，成功提取能力当前仍未验证。不会用零商品结果证明解析器正确。

## 环境限制

侦察环境为 macOS Python 3.9.6，requests 2.32.5、BeautifulSoup 4.15.0 均已存在，无需安装。urllib3 给出 LibreSSL 2.8.3 的 NotOpenSSLWarning，完整保留在侦察执行输出中；没有隐藏 warning 或关闭 TLS 证书校验。该请求仍实际收到 HTTP 响应，不能直接把 503 归因于此 warning。
'''
    dictionary='''# Realtime Data Dictionary

本次没有商品数据，以下是目标字段和已实现的表结构；字段来源中的 DOM 规则尚未由真实成功搜索页验证。数据类型是预期 Python / SQLite 类型，不是零行表中观测到的实际值类型。

'''+table([
        ['crawl_time','str / TEXT','实际请求开始时间，UTC ISO 8601，带微秒','该次快照请求时点；重放保留原时点','否'],
        ['keyword','str / TEXT','固定配置 garden hose','采集关键词','否'],
        ['search_position','int / INTEGER','前 20 个可识别候选卡片的 DOM 顺序，从 1 开始','本次结果卡片的位置，重复 ASIN 保存首次出现位置','否'],
        ['asin','str / TEXT','候选卡片 data-asin；校验十位大写字母/数字','当前商品标识；不是已验证的 parent_asin','否；无效候选拒绝并记录'],
        ['title','str / TEXT','候选卡 h2 文本','当前展示商品标题','是'],
        ['price','float / REAL','当前商品卡明确美元展示价格','USD 页面展示价，不含未展示的运费等，不是历史价格','是；未知不填 0'],
        ['rating','float / REAL','商品卡星级描述，如 n out of 5 stars','当前展示平均评分，校验 1–5','是'],
        ['review_count','int / INTEGER','商品卡评价链接中的明确整数文本','页面当前评价量；未确认具体 ratings/reviews 标签时不混称评论全文数','是；不猜测 K+ 等缩写'],
        ['product_url','str / TEXT','直接商品链接；校验域名/ASIN并去跟踪参数','https://www.amazon.com/dp/ASIN；无法验证直接链接时 NULL','是'],
    ],['字段','数据类型','来源','业务含义','允许缺失'])+'''

search_position ≠ Amazon 官方 Search Rank。它仅在这次请求上下文、可识别卡片范围内有意义，可能包含广告，不等同自然搜索排名；不同地点、设备和排序设置可能影响结果。

price 是采集时当前展示价格，不是过去时间序列价格。review_count 是当前展示评价数量，不是销量。没有从结果卡获得 parent_asin 映射，不能直接把当前 ASIN 当成历史父商品关联键。

缺失率分母为实际进入字段清洗的商品行数；拒绝的无效 ASIN 候选另行统计候选缺失/非法数量。没有商品时缺失率为 NULL/无法计算，禁止写成 0%。转换异常、重复 ASIN 和拒绝原因记录在本次 result.json；原始页面保留，不修改。
'''
    local_time=datetime.fromisoformat(result['crawl_time']).astimezone(ZoneInfo('Asia/Shanghai')).isoformat()
    collection=f'''# Goal

验证 Amazon Garden 实时竞品采集的最小链路：数据源侦察 → 单页普通采集 → 保守解析与校验 → SQLite 快照/运行审计。最多 20 个候选商品，不追求规模，不做 EDA、模型或定时任务。

# Source Analysis

来源 `{result['requested_url']}`。技术保留 requests + BeautifulSoup；本次仅侦察 GET 一次，再用 collector --replay 处理同一真实响应，防止在错误响应后重复访问。详细证据见 realtime_source_analysis.md。

本次 outcome：**{result['outcome']}**。响应类型 {result.get('content_type')}；页面标题 {result['page_title']}。CAPTCHA={result['captcha']}、Robot Check={result['robot_check']}、403={result['forbidden_403']}。失败层为 HTTP/页面响应；503 根因未验证，未用浏览器、API、代理或身份切换进行后续尝试。

# Collection Result

- 请求时间 UTC：{result['crawl_time']}；Asia/Shanghai：{local_time}。
- keyword：{result['keyword']}。
- HTTP 状态：{result.get('status_code')}；final URL：{result.get('final_url')}。
- 页面候选数：{result['candidate_count']}；选取候选数：{result['selected_candidate_count']}（上限 20）。
- 成功解析商品数：{result['parsed_count']}；去重后：{result['unique_parsed_count']}。
- 该次 collector 执行是否发起请求：{result['request_performed_this_execution']}（离线处理本次真实侦察响应）。
- 错误：{result['errors']}。
- 原始响应：`{result['raw_file']}`；响应元数据：`{result['response_metadata_file']}`。
- raw SHA-256：`{result['raw_sha256']}`；实际响应 {result.get('response_bytes')} 字节。

# Data Quality

{table(rates(result),['字段','缺失数量','统计分母','缺失率'])}

没有商品，所以字段缺失率无法计算；不把无结果误写为零缺失或 100% 缺失。候选 ASIN 缺失率：{result['candidate_asin_missing_rate']}；非法 ASIN 候选数 {result['invalid_asin_count']}；duplicate ASIN 数 {result['duplicate_asin_count']}。转换异常：{result['conversion_issues']}。

位置按卡片顺序转整数；ASIN 严格校验；价格不明保留 NULL；rating 范围校验；评价数仅转换明确整数；URL 验证 Amazon.com 域名和对应 ASIN后标准化。同次重复 ASIN 保存首次出现位置。以上成功商品分支尚无真实商品可验证，不使用模拟商品证明成功。

# Storage

SQLite：`{DATABASE_FILE}`。

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

实际本次写入 search_snapshots：**{result['inserted_rows']} 行**，storage_status={result['storage_status']}。collection_runs 单独保存真实 HTTP 状态、raw 路径、质量统计和失败原因；这不是商品数据。相同请求重放以 crawl_time+keyword 判定已记录，避免重复运行审计；不把 asin 设成跨时间唯一主键。

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

运行出口：collector exit code **{result['exit_code']}**。3 表示采集源不可用，不能写成成功 exit 0；数据库/原始响应/字段验证审计另行执行。当前只能推进失败审计与离线重放维护，未具备成功商品采集的工程化依据。
'''
    for name,text in [('realtime_source_analysis.md',source),('realtime_data_dictionary.md',dictionary),('realtime_collection_v1.md',collection)]:
        (REPORT_DIR/name).write_text(text,encoding='utf-8')
