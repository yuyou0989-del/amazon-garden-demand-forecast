"""商品快照与失败运行审计分表存储，不混入历史建模数据库。"""
import json
import sqlite3
from contextlib import closing
from src.realtime.config import DATABASE_FILE, FIELDS


def connect_database():
    DATABASE_FILE.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_FILE)
    connection.executescript('''
        CREATE TABLE IF NOT EXISTS collection_runs (
            crawl_time TEXT NOT NULL, keyword TEXT NOT NULL,
            request_method TEXT NOT NULL, status_code INTEGER, final_url TEXT,
            outcome TEXT NOT NULL, raw_file TEXT, candidate_count INTEGER NOT NULL,
            parsed_count INTEGER NOT NULL, inserted_rows INTEGER NOT NULL,
            missing_statistics TEXT NOT NULL, errors TEXT NOT NULL,
            PRIMARY KEY(crawl_time, keyword)
        );
        CREATE TABLE IF NOT EXISTS search_snapshots (
            id INTEGER PRIMARY KEY,
            crawl_time TEXT NOT NULL, keyword TEXT NOT NULL,
            search_position INTEGER NOT NULL CHECK(search_position>0),
            asin TEXT NOT NULL CHECK(length(asin)=10), title TEXT,
            price REAL CHECK(price IS NULL OR price>0),
            rating REAL CHECK(rating IS NULL OR (rating>=1 AND rating<=5)),
            review_count INTEGER CHECK(review_count IS NULL OR review_count>=0),
            product_url TEXT,
            marketplace TEXT, currency TEXT, collection_method TEXT,
            UNIQUE(crawl_time, keyword, asin),
            FOREIGN KEY(crawl_time, keyword) REFERENCES collection_runs(crawl_time, keyword)
        );
    ''')
    # 追加上下文列；旧审计只补 collection_method，原有字段不变。
    columns = {row[1] for row in connection.execute('PRAGMA table_info(collection_runs)')}
    for name, declaration in [('collection_method', "TEXT NOT NULL DEFAULT 'requests'"),
                              ('marketplace', 'TEXT'), ('currency', 'TEXT')]:
        if name not in columns:
            connection.execute(f'ALTER TABLE collection_runs ADD COLUMN {name} {declaration}')
    snapshot_columns = {row[1] for row in connection.execute('PRAGMA table_info(search_snapshots)')}
    for name in ('marketplace', 'currency', 'collection_method'):
        if name not in snapshot_columns:
            connection.execute(f'ALTER TABLE search_snapshots ADD COLUMN {name} TEXT')
    connection.execute('PRAGMA foreign_keys=ON')
    return connection


def store_run(result, rows):
    with closing(connect_database()) as connection, connection:
        existing = connection.execute('SELECT 1 FROM collection_runs WHERE crawl_time=? AND keyword=?',
                                      (result['crawl_time'],result['keyword'])).fetchone()
        if existing:
            return 0, 'already_recorded'
        connection.execute('''INSERT INTO collection_runs (
            crawl_time,keyword,request_method,status_code,final_url,outcome,raw_file,
            candidate_count,parsed_count,inserted_rows,missing_statistics,errors,
            collection_method,marketplace,currency) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                           (result['crawl_time'],result['keyword'],result['request_method'],
                            result.get('status_code'),result.get('final_url'),result['outcome'],
                            result.get('raw_file'),result['candidate_count'],result['parsed_count'],
                            0,json.dumps(result['missing_statistics']),json.dumps(result['errors']),
                            result.get('collection_method','requests'),
                            result.get('marketplace'),result.get('currency')))
        inserted = 0
        for row in rows:
            # 快照自身保存市场/币种/方法，避免脱离运行表后误把 SGD 当 USD。
            snapshot_fields = (*FIELDS, 'marketplace', 'currency', 'collection_method')
            values = [row[field] for field in FIELDS] + [result.get(field) for field in snapshot_fields[-3:]]
            cursor = connection.execute(
                f'INSERT INTO search_snapshots ({",".join(snapshot_fields)}) VALUES ({",".join(["?"]*len(snapshot_fields))})', values)
            inserted += cursor.rowcount
        connection.execute('UPDATE collection_runs SET inserted_rows=? WHERE crawl_time=? AND keyword=?',
                           (inserted,result['crawl_time'],result['keyword']))
    return inserted, 'recorded'
