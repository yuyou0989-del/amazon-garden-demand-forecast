"""对已保存的实时 SQLite 快照执行只读 SQL 分析。"""

from __future__ import annotations

import hashlib
import sqlite3
from contextlib import closing
from pathlib import Path

from src.config import REPORT_DIR
from src.realtime.config import DATABASE_FILE


REPORT_PATH = REPORT_DIR / "stage7_sql_analysis.md"
REQUIRED_TABLE_COLUMNS = {
    "search_snapshots": {
        "crawl_time", "keyword", "marketplace", "currency", "asin",
        "search_position", "title", "price", "rating", "review_count",
    },
    "collection_runs": {
        "crawl_time", "keyword", "status_code", "outcome", "inserted_rows",
    },
}

# 对每组关键词/市场/币种，只取其最后一个实际有商品的 crawl_time。
LATEST_CTE = """
WITH latest AS (
    SELECT keyword, marketplace, currency, MAX(crawl_time) AS crawl_time
    FROM search_snapshots
    GROUP BY keyword, marketplace, currency
), current_snapshots AS (
    SELECT s.* FROM search_snapshots AS s
    JOIN latest AS l
      ON s.keyword = l.keyword AND s.marketplace = l.marketplace
     AND s.currency = l.currency AND s.crawl_time = l.crawl_time
)
"""

OVERVIEW_SQL = LATEST_CTE + """
SELECT keyword, marketplace, currency, crawl_time,
       COUNT(*) AS product_count,
       COUNT(price) AS priced_count,
       AVG(price) AS avg_price, MIN(price) AS min_price, MAX(price) AS max_price,
       COUNT(rating) AS rated_count, AVG(rating) AS avg_rating,
       COUNT(review_count) AS review_count_known,
       AVG(review_count) AS avg_review_count
FROM current_snapshots
GROUP BY keyword, marketplace, currency, crawl_time
ORDER BY keyword, marketplace, currency
"""

TOP_SQL = LATEST_CTE + """
, ranked AS (
    SELECT keyword, marketplace, currency, crawl_time,
           search_position, asin, title, price, rating, review_count,
           ROW_NUMBER() OVER (
               PARTITION BY keyword, marketplace, currency, crawl_time
               ORDER BY search_position, asin
           ) AS row_number
    FROM current_snapshots
)
SELECT keyword, marketplace, currency, crawl_time,
       search_position, asin, title, price, rating, review_count
FROM ranked WHERE row_number <= 10
ORDER BY keyword, marketplace, currency, search_position
"""

# 实测 SGD 价格为 30.01–145.43；50–100 区间较密集，所以划四档。
# NULL 单列，SQL AVG() 会跳过缺失评分/评价数，不把未知价格填 0。
PRICE_BAND_SQL = LATEST_CTE + """
, banded AS (
    SELECT keyword, marketplace, currency, crawl_time, rating, review_count,
           CASE WHEN price IS NULL THEN 'Unknown'
                WHEN price < 50 THEN '<50'
                WHEN price < 75 THEN '50–<75'
                WHEN price < 100 THEN '75–<100'
                ELSE '>=100' END AS price_band,
           CASE WHEN price IS NULL THEN 5
                WHEN price < 50 THEN 1
                WHEN price < 75 THEN 2
                WHEN price < 100 THEN 3
                ELSE 4 END AS band_order
    FROM current_snapshots
)
SELECT keyword, marketplace, currency, crawl_time, price_band,
       COUNT(*) AS product_count, COUNT(rating) AS rated_count,
       AVG(rating) AS avg_rating, COUNT(review_count) AS review_count_known,
       AVG(review_count) AS avg_review_count
FROM banded
GROUP BY keyword, marketplace, currency, crawl_time, price_band, band_order
ORDER BY keyword, marketplace, currency, crawl_time, band_order
"""

# 差值为当前减前次；位置差值为正表示搜索卡片顺序数字变大。
# 若未来同一市场出现币种变化，价格差记 NULL，避免跨币种直接相减。
CHANGE_SQL = """
WITH previous_values AS (
    SELECT keyword, marketplace, currency, asin, crawl_time,
           price AS current_price, search_position AS current_search_position,
           review_count AS current_review_count,
           LAG(crawl_time) OVER ordered AS previous_crawl_time,
           LAG(currency) OVER ordered AS previous_currency,
           LAG(price) OVER ordered AS previous_price,
           LAG(search_position) OVER ordered AS previous_search_position,
           LAG(review_count) OVER ordered AS previous_review_count
    FROM search_snapshots
    WINDOW ordered AS (
        PARTITION BY keyword, marketplace, asin ORDER BY crawl_time
    )
)
SELECT keyword, marketplace, currency, asin,
       previous_crawl_time, crawl_time AS current_crawl_time,
       previous_price, current_price,
       CASE WHEN previous_currency = currency
            THEN current_price - previous_price ELSE NULL END AS price_change,
       previous_search_position, current_search_position,
       current_search_position - previous_search_position AS position_change,
       previous_review_count, current_review_count,
       current_review_count - previous_review_count AS review_count_change
FROM previous_values
WHERE previous_crawl_time IS NOT NULL
ORDER BY keyword, marketplace, asin, current_crawl_time
"""


def format_number(value: object, decimals: int = 2) -> str:
    return "NULL" if value is None else f"{value:,.{decimals}f}"


def format_text(value: object) -> str:
    return "NULL" if value is None else str(value).replace("|", "\\|").replace("\n", " ")


def format_table(rows: list[sqlite3.Row], columns: list[str]) -> list[str]:
    return [
        "| " + " | ".join(columns) + " |",
        "|" + "|".join("---" for _ in columns) + "|",
        *("| " + " | ".join(format_text(row[column]) for column in columns) + " |"
          for row in rows),
    ]


def run_queries() -> dict:
    database = DATABASE_FILE.resolve()
    if not database.is_file():
        raise FileNotFoundError(database)
    before_hash = hashlib.sha256(database.read_bytes()).hexdigest()
    # mode=ro + query_only 双重保证：不会写入或迁移采集数据库。
    with closing(sqlite3.connect(f"file:{database}?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        for table, required in REQUIRED_TABLE_COLUMNS.items():
            found = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
            missing = required - found
            if missing:
                raise ValueError(f"{table} 缺少字段：{sorted(missing)}")
        run_count = connection.execute("SELECT COUNT(*) FROM collection_runs").fetchone()[0]
        run_statuses = connection.execute("""
            SELECT status_code, outcome, COUNT(*) AS run_count
            FROM collection_runs GROUP BY status_code, outcome
            ORDER BY status_code, outcome
        """).fetchall()
        snapshot_count = connection.execute("""
            SELECT COUNT(*) FROM (
                SELECT keyword, marketplace, currency, crawl_time
                FROM search_snapshots
                GROUP BY keyword, marketplace, currency, crawl_time
            )
        """).fetchone()[0]
        product_rows = connection.execute("SELECT COUNT(*) FROM search_snapshots").fetchone()[0]
        overview = connection.execute(OVERVIEW_SQL).fetchall()
        top = connection.execute(TOP_SQL).fetchall()
        bands = connection.execute(PRICE_BAND_SQL).fetchall()
        changes = connection.execute(CHANGE_SQL).fetchall()
    after_hash = hashlib.sha256(database.read_bytes()).hexdigest()
    if before_hash != after_hash:
        raise AssertionError("SQLite 文件在只读分析期间发生变化")
    if sum(row["product_count"] for row in overview) > product_rows:
        raise AssertionError("当前快照商品数超过数据库商品总行数")
    if sum(row["product_count"] for row in bands) != sum(row["product_count"] for row in overview):
        raise AssertionError("价格区间未覆盖全部当前商品")
    return {
        "database": database, "sqlite_version": sqlite3.sqlite_version,
        "run_count": run_count, "run_statuses": run_statuses,
        "snapshot_count": snapshot_count, "product_rows": product_rows,
        "overview": overview, "top": top, "bands": bands,
        "changes": changes, "database_sha256": after_hash,
    }


def write_report(result: dict) -> None:
    overview = result["overview"]
    top = result["top"]
    bands = result["bands"]
    changes = result["changes"]
    overview_rows = [
        f"| {row['keyword']} | {row['marketplace']} | {row['currency']} | {row['crawl_time']} | "
        f"{row['product_count']} | {row['priced_count']} | "
        f"{format_number(row['avg_price'])} | {format_number(row['min_price'])} | "
        f"{format_number(row['max_price'])} | {row['rated_count']} | "
        f"{format_number(row['avg_rating'])} | {row['review_count_known']} | "
        f"{format_number(row['avg_review_count'])} |"
        for row in overview
    ]
    top_rows = [
        f"| {row['search_position']} | {row['asin']} | {format_text(row['title'])} | "
        f"{format_number(row['price'])} | {format_number(row['rating'], 1)} | "
        f"{format_text(row['review_count'])} |"
        for row in top
    ]
    band_rows = [
        f"| {row['price_band']} | {row['product_count']} | {row['rated_count']} | "
        f"{format_number(row['avg_rating'])} | {row['review_count_known']} | "
        f"{format_number(row['avg_review_count'])} |"
        for row in bands
    ]
    change_columns = [
        "keyword", "marketplace", "asin", "previous_crawl_time", "current_crawl_time",
        "previous_price", "current_price", "price_change", "previous_search_position",
        "current_search_position", "position_change", "previous_review_count",
        "current_review_count", "review_count_change",
    ]
    run_status_text = "；".join(
        f"HTTP {row['status_code']} / {row['outcome']}: {row['run_count']} 次"
        for row in result["run_statuses"]
    )
    price_min = min((row["min_price"] for row in overview if row["min_price"] is not None), default=None)
    price_max = max((row["max_price"] for row in overview if row["max_price"] is not None), default=None)
    lines = [
        "# Stage 7A：Realtime SQLite SQL Analysis", "",
        f"数据库：`{result['database']}`；SQLite {result['sqlite_version']}。"
        "以只读模式执行，分析前后数据库 SHA-256 相同。",
        f"`collection_runs` 有 {result['run_count']} 条运行审计；商品表有 "
        f"{result['snapshot_count']} 个有效快照、{result['product_rows']} 行商品。"
        "失败运行不计为商品快照。",
        f"运行审计：{run_status_text}。",
        "", "## A. 当前快照概况", "",
        "每个 keyword + marketplace + currency 取最后一个有商品的 crawl_time；"
        "SQL AVG/MIN/MAX 跳过 NULL，另列非空样本数。",
        "| keyword | marketplace | currency | crawl_time | products | priced | avg_price | min_price | max_price | rated | avg_rating | review_count known | avg_review_count |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        *overview_rows,
        "", "## B. 当前搜索结果前 10 个商品", "",
        "按 search_position 升序；这里的位置只是该次采集到的搜索结果卡片顺序。",
        "| position | asin | title | price | rating | review_count |",
        "|---:|---|---|---:|---:|---:|", *top_rows,
        "", "## C. 当前价格区间", "",
        f"先检查本次真实价格：最小 {format_number(price_min)}、最大 {format_number(price_max)} SGD；"
        "现有 20 个价格中 50–100 区间较密集，故为当前 SGD 快照用 "
        "<50、50–<75、75–<100、>=100 四档；"
        "SQL CASE 另设 Unknown，未知价格不填 0。",
        "| price band (SGD) | products | rated | avg_rating | review_count known | avg_review_count |",
        "|---|---:|---:|---:|---:|---:|", *band_rows,
        "", "## D. 多快照变化", "",
        "查询以 `(keyword, marketplace, asin)` 分组，用 SQLite `LAG()` 取前次记录；"
        "变化量均为当前值减前次值。若币种变化，price_change 为 NULL。"
        "位置差值为正表示卡片顺序数字变大。",
        f"当前真实变化结果：{len(changes)} 行。" + (
            "当前数据不足以进行真实趋势分析。" if not changes else ""
        ),
    ]
    if changes:
        lines += ["", *format_table(changes, change_columns)]
    lines += [
        "", "## 结论与证据边界", "",
        "当前可以描述这一次 Amazon.sg / SGD 搜索结果的展示价格、评分、评价量和卡片顺序，"
        "以及各价格档的样本聚合；这只是本次页面快照。",
        "review_count ≠ sales；search_position ≠ Amazon 官方 Search Rank；"
        "单次 snapshot 不能证明趋势；当前 Amazon.sg / SGD 结果不能直接代表 Amazon.com。"
        "所有 SQL 结果只基于现有真实 SQLite 商品行，没有伪造快照。",
        "今后若同一 keyword、marketplace、asin 有多个可比采集时点，变化查询可描述"
        "展示价格、卡片位置和评价量的观测差值；这仍不能单独证明销量或变化原因。", "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    result = run_queries()
    write_report(result)
    print(f"database={result['database']}")
    print(f"collection_runs={result['run_count']} snapshots={result['snapshot_count']} products={result['product_rows']}")
    for row in result["overview"]:
        print("overview=" + str(dict(row)))
    print("price_bands=" + str([dict(row) for row in result["bands"]]))
    print(f"multi_snapshot_change_rows={len(result['changes'])}")
    if not result["changes"]:
        print("当前数据不足以进行真实趋势分析")
    print(f"database_sha256={result['database_sha256']} report={REPORT_PATH}")


if __name__ == "__main__":
    main()
