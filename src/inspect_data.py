"""Stage 1 入口：真实数据摸底、质量检查与报告生成。"""
import json
import sqlite3
import sys
from datetime import datetime

from src.config import COHORT_FILE, META_FILE, MANIFEST_FILE, OUTPUT_DIR, REPORT_DIR
from src.profiling import profile_file, distribution
from src.reporting import write_reports


def inspect(connection):
    connection.executescript('''
        CREATE TABLE reviews(parent TEXT, asin TEXT, user TEXT, rating REAL,
                             timestamp REAL, verified INTEGER, helpful REAL);
        CREATE TABLE metadata(parent TEXT, price REAL, average_rating REAL,
                              rating_number REAL, store TEXT, brand TEXT);
    ''')
    review = profile_file(connection, COHORT_FILE, 'reviews')
    meta = profile_file(connection, META_FILE, 'metadata')
    connection.executescript('''
        CREATE INDEX review_parent ON reviews(parent);
        CREATE INDEX meta_parent ON metadata(parent);
    ''')
    def scalar(query):
        return connection.execute(query).fetchone()[0]
    result = {'reviews': review, 'metadata': meta}
    result['coverage'] = {
        'review_parent_ids': scalar("SELECT COUNT(DISTINCT parent) FROM reviews WHERE parent IS NOT NULL AND TRIM(parent) != ''"),
        'metadata_parent_ids': scalar("SELECT COUNT(DISTINCT parent) FROM metadata WHERE parent IS NOT NULL AND TRIM(parent) != ''"),
        'users': scalar("SELECT COUNT(DISTINCT user) FROM reviews WHERE user IS NOT NULL AND TRIM(user) != ''"),
        'asins': scalar("SELECT COUNT(DISTINCT asin) FROM reviews WHERE asin IS NOT NULL AND TRIM(asin) != ''") if 'asin' in review['fields'] else None,
        'asin_multiple_parents': scalar('SELECT COUNT(*) FROM (SELECT asin FROM reviews WHERE asin IS NOT NULL GROUP BY asin HAVING COUNT(DISTINCT parent)>1)') if 'asin' in review['fields'] else None,
        'parent_multiple_asins': scalar('SELECT COUNT(*) FROM (SELECT parent FROM reviews GROUP BY parent HAVING COUNT(DISTINCT asin)>1)') if 'asin' in review['fields'] else None,
        'metadata_duplicate_parent_rows': scalar("SELECT COUNT(parent)-COUNT(DISTINCT parent) FROM metadata WHERE TRIM(parent) != ''"),
        'matched_review_rows': scalar('SELECT COUNT(*) FROM reviews r WHERE EXISTS (SELECT 1 FROM metadata m WHERE m.parent=r.parent)'),
        'matched_review_parents': scalar('SELECT COUNT(DISTINCT r.parent) FROM reviews r WHERE EXISTS (SELECT 1 FROM metadata m WHERE m.parent=r.parent)'),
        'metadata_without_cohort_reviews': scalar('SELECT COUNT(*) FROM metadata m WHERE NOT EXISTS (SELECT 1 FROM reviews r WHERE r.parent=m.parent)'),
    }
    result['coverage']['review_row_match_rate'] = result['coverage']['matched_review_rows'] / review['rows'] if review['rows'] else None
    result['coverage']['review_parent_match_rate'] = result['coverage']['matched_review_parents'] / result['coverage']['review_parent_ids'] if result['coverage']['review_parent_ids'] else None
    result['distributions'] = {
        'interactions_per_parent': distribution(connection, "SELECT COUNT(*) AS value FROM reviews WHERE parent IS NOT NULL AND TRIM(parent) != '' GROUP BY parent"),
        'price': distribution(connection, 'SELECT price AS value FROM metadata WHERE price IS NOT NULL'),
        'helpful_vote': distribution(connection, 'SELECT helpful AS value FROM reviews WHERE helpful IS NOT NULL') if 'helpful_vote' in review['fields'] else None,
    }
    result['verified_purchase_ratio'] = scalar('SELECT AVG(verified) FROM reviews') if 'verified_purchase' in review['fields'] else None
    result['time_span_days'] = (datetime.fromisoformat(review['time_max']) - datetime.fromisoformat(review['time_min'])).total_seconds()/86400 if review['time_min'] else None
    return result


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    if not COHORT_FILE.exists() or not META_FILE.exists():
        write_reports(None, REPORT_DIR)
        print('真实输入文件缺失：请先运行 python3 -m src.download_data；未生成任何虚构统计。', file=sys.stderr)
        return 2
    # 内存缓存限制，较大数据的精确关系/重复检查使用磁盘。
    database = OUTPUT_DIR / 'inspection.sqlite'
    if database.exists():
        database.unlink()
    with sqlite3.connect(database) as connection:
        connection.execute('PRAGMA cache_size=-16384')
        connection.execute('PRAGMA temp_store=FILE')
        result = inspect(connection)
    if MANIFEST_FILE.exists():
        result['download_manifest'] = json.loads(MANIFEST_FILE.read_text())
    (OUTPUT_DIR / 'inspection_summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    write_reports(result, REPORT_DIR)
    for kind in ('reviews', 'metadata'):
        data = result[kind]
        print(f'{kind}: {data["rows"]:,} rows × {data["columns"]} columns; {data["bytes"]:,} bytes')
        print('字段及实际类型:', {key: value['types'] for key, value in data['fields'].items()})
        print('前 5 行:', json.dumps(data['first_five'], ensure_ascii=False))
    compact = {key: value for key, value in result.items() if key not in ('reviews', 'metadata', 'download_manifest')}
    print(json.dumps(compact, ensure_ascii=False, indent=2))
    print(f'报告已生成：{REPORT_DIR}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
