"""只验证本次真实结果、原始响应与数据库；不插入虚构测试商品。"""
import hashlib
import json
import sqlite3
from pathlib import Path

from src.realtime.config import DATABASE_FILE, RESULT_DIR, FIELDS


def main():
    results=sorted(RESULT_DIR.glob('*.result.json'))
    if not results: raise RuntimeError('没有实际采集结果。')
    result=json.loads(results[-1].read_text())
    raw=Path(result['raw_file']).read_bytes()
    assert len(raw)==result['response_bytes']
    assert hashlib.sha256(raw).hexdigest()==result['raw_sha256']
    connection=sqlite3.connect(DATABASE_FILE)
    connection.row_factory=sqlite3.Row
    try:
        run=connection.execute('SELECT * FROM collection_runs WHERE crawl_time=? AND keyword=?',
                               (result['crawl_time'],result['keyword'])).fetchone()
        assert run is not None
        rows=[dict(row) for row in connection.execute('SELECT * FROM search_snapshots WHERE crawl_time=? AND keyword=? ORDER BY search_position',
                                                     (result['crawl_time'],result['keyword']))]
        duplicate=connection.execute('''SELECT COUNT(*) FROM (SELECT crawl_time,keyword,asin,COUNT(*) n
            FROM search_snapshots GROUP BY crawl_time,keyword,asin HAVING n>1)''').fetchone()[0]
        assert duplicate==0
        assert len(rows)==result['unique_parsed_count']
        assert run['inserted_rows']==len(rows)
        assert connection.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        schema=[dict(row) for row in connection.execute('PRAGMA table_info(search_snapshots)')]
        indexes=[dict(row) for row in connection.execute('PRAGMA index_list(search_snapshots)')]
        unique_columns=[]
        for index in indexes:
            if index['unique']:
                unique_columns.append([r['name'] for r in connection.execute(f'PRAGMA index_info("{index["name"]}")')])
        assert ['crawl_time','keyword','asin'] in unique_columns
        observed_types={field:[r[0] for r in connection.execute(f'SELECT DISTINCT typeof({field}) FROM search_snapshots WHERE crawl_time=? AND keyword=?',
                                                               (result['crawl_time'],result['keyword']))] for field in FIELDS}
        missing={field:sum(row[field] is None for row in rows) for field in FIELDS}
        if result['outcome']!='success':
            assert len(rows)==0
            assert all(x['missing_rate'] is None for x in result['missing_statistics'].values())
        verification={'verification':'PASS','actual_snapshot_rows':len(rows),
                      'actual_run_rows_for_this_crawl':1,'actual_run':dict(run),
                      'sample_select_results':rows[:5],'table_schema':schema,
                      'unique_key_columns':unique_columns,'duplicate_snapshot_keys':duplicate,
                      'observed_types':observed_types,'missing_counts':missing,
                      'missing_rates':{f:missing[f]/len(rows) if rows else None for f in FIELDS},
                      'raw_bytes':len(raw),'collector_exit_code':result['exit_code'],
                      'verification_exit_code':0}
        (RESULT_DIR/'verification.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(verification,ensure_ascii=False,indent=2))
    finally:
        connection.close()


if __name__=='__main__':
    main()
