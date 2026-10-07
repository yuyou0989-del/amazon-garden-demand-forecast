"""从已保存的成功搜索 HTML 离线复算 V1 快照；不会发网络请求。"""
import argparse
import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from urllib.parse import urlparse

from src.realtime.config import DATABASE_FILE, FIELDS, MAX_PRODUCTS, RAW_DIR
from src.realtime.parser import detect_page, parse_candidates
from src.realtime.storage import connect_database, store_run

CONTEXT = {'marketplace': 'amazon.sg', 'currency': 'SGD',
           'collection_method': 'playwright'}


def saved_source(html_path):
    html_path = html_path.resolve()
    if html_path.parent != RAW_DIR.resolve() or not html_path.name.endswith('.initial.html'):
        raise ValueError('请指定 data/realtime/raw 中已保存的 Playwright .initial.html')
    metadata_path = html_path.with_name(html_path.name.replace('.initial.html', '.navigation.json'))
    metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
    html_bytes = html_path.read_bytes()
    expected_hash = metadata.get('artifact_hashes', {}).get('initial_html_file')
    if expected_hash and hashlib.sha256(html_bytes).hexdigest() != expected_hash:
        raise ValueError('保存的 HTML 与导航元数据 SHA-256 不一致')
    if metadata['status_code'] != 200 or urlparse(metadata['final_url']).hostname != 'www.amazon.sg':
        raise ValueError('保存的证据不是 Amazon.sg 200 成功页')
    if metadata['collection_method'] != 'playwright':
        raise ValueError('保存的 collection_method 不是 playwright')
    return metadata, html_bytes


def parse_saved_page(metadata, html_bytes):
    _, candidates, page = detect_page(html_bytes, metadata['status_code'], metadata['final_url'])
    if page['page_errors'] or len(candidates) < MAX_PRODUCTS:
        raise ValueError(f'成功页候选不足或有阻塞：{page["page_errors"]}，候选 {len(candidates)}')
    rows, quality = parse_candidates(candidates, metadata['crawl_time'], metadata['keyword'],
                                     metadata['final_url'], CONTEXT['currency'])
    if len(rows) != MAX_PRODUCTS or quality['duplicate_asin_count']:
        raise ValueError('保存页面前 20 个商品没有通过 ASIN/重复校验')
    return candidates, rows, quality


def persist_exact_snapshot(metadata, candidates, rows, quality):
    key = (metadata['crawl_time'], metadata['keyword'])
    with closing(connect_database()) as connection:
        run = connection.execute('''SELECT status_code,final_url,collection_method,inserted_rows
                                    FROM collection_runs WHERE crawl_time=? AND keyword=?''', key).fetchone()
    if run is None:
        # 空库时也可从同一真实 HTML 重建，不需要重开浏览器。
        result = {**metadata, **CONTEXT, 'request_method': 'GET',
                  'raw_file': metadata.get('raw_file'), 'outcome': 'success_other_marketplace',
                  'candidate_count': len(candidates), 'parsed_count': len(rows),
                  'missing_statistics': quality['missing_statistics'], 'errors': []}
        store_run(result, rows)
    elif (run[0], run[1], run[2], run[3]) != (200, metadata['final_url'], 'playwright', len(rows)):
        raise ValueError('已有运行审计与保存页面不一致；拒绝覆盖')

    with closing(connect_database()) as connection, connection:
        stored = connection.execute(f'''SELECT {','.join(FIELDS)} FROM search_snapshots
                                        WHERE crawl_time=? AND keyword=? ORDER BY search_position''', key).fetchall()
        expected = [tuple(row[field] for field in FIELDS) for row in rows]
        if stored != expected:
            raise ValueError('SQLite 商品与保存 HTML 不一致；拒绝覆盖真实商品字段')
        connection.execute('''UPDATE collection_runs SET marketplace=?,currency=?,collection_method=?
                              WHERE crawl_time=? AND keyword=?''',
                           (*CONTEXT.values(), *key))
        connection.execute('''UPDATE search_snapshots SET marketplace=?,currency=?,collection_method=?
                              WHERE crawl_time=? AND keyword=?''',
                           (*CONTEXT.values(), *key))
        count = connection.execute('SELECT COUNT(*) FROM search_snapshots WHERE crawl_time=? AND keyword=?', key).fetchone()[0]
        duplicates = connection.execute('''SELECT COUNT(*) FROM (
            SELECT asin FROM search_snapshots WHERE crawl_time=? AND keyword=?
            GROUP BY asin HAVING COUNT(*)>1)''', key).fetchone()[0]
        contexts = connection.execute('''SELECT DISTINCT marketplace,currency,collection_method
                                         FROM search_snapshots WHERE crawl_time=? AND keyword=?''', key).fetchall()
        types = {field: [item[0] for item in connection.execute(
            f'SELECT DISTINCT typeof({field}) FROM search_snapshots WHERE crawl_time=? AND keyword=?',key)]
                 for field in ('price', 'rating', 'review_count')}
        missing = {field: connection.execute(
            f'SELECT COUNT(*) FROM search_snapshots WHERE crawl_time=? AND keyword=? AND {field} IS NULL', key).fetchone()[0]
                   for field in (*FIELDS, *CONTEXT)}
        integrity = connection.execute('PRAGMA integrity_check').fetchone()[0]
        foreign_key_errors = connection.execute('PRAGMA foreign_key_check').fetchall()
        if count != MAX_PRODUCTS or duplicates or contexts != [tuple(CONTEXT.values())]:
            raise ValueError('数据库行数、唯一键或站点/币种/方式校验失败')
        if any(missing.values()) or types != {'price': ['real'], 'rating': ['real'], 'review_count': ['integer']}:
            raise ValueError('数据库字段缺失或类型与当前真实页面不符')
        if integrity != 'ok' or foreign_key_errors:
            raise ValueError('SQLite 完整性/外键校验失败')
        samples = connection.execute('''SELECT asin,title,price,rating,review_count
                                        FROM search_snapshots WHERE crawl_time=? AND keyword=?
                                        ORDER BY search_position LIMIT 3''', key).fetchall()
        total = connection.execute('SELECT COUNT(*) FROM search_snapshots').fetchone()[0]
    return {'parsed': len(rows), 'sqlite_rows_this_run': count, 'sqlite_rows_total': total,
            'duplicate_asin': duplicates, 'marketplace': CONTEXT['marketplace'],
            'currency': CONTEXT['currency'], 'collection_method': CONTEXT['collection_method'],
            'types': types, 'missing_rates': {field: value/count for field, value in missing.items()},
            'samples': [dict(zip(('asin','title','price','rating','review_count'), item)) for item in samples],
            'integrity_check': integrity, 'exit_code': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--html', type=Path, required=True)
    args = parser.parse_args()
    metadata, html = saved_source(args.html)
    candidates, rows, quality = parse_saved_page(metadata, html)
    print(json.dumps(persist_exact_snapshot(metadata, candidates, rows, quality),
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
