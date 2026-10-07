"""离线保存并审计单次 Playwright CLI 的捕获结果；本模块不发网络请求。"""
import argparse
import base64
import hashlib
import json
import logging
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from src.realtime.config import RAW_DIR, RESULT_DIR, DATABASE_FILE, LOG_FILE, FIELDS
from src.realtime.parser import detect_page, parse_candidates
from src.realtime.storage import store_run
from src.realtime.playwright_report import write_report


def preserve(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f'Refusing to overwrite differing evidence: {path}')
    else:
        with path.open('xb') as stream:
            stream.write(data)


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, indent=2).encode('utf-8')


def save_capture(capture):
    stamp = datetime.fromisoformat(capture['crawl_time'].replace('Z', '+00:00')).strftime('%Y%m%dT%H%M%S%fZ')
    stem = f"garden_hose_playwright_{stamp}"
    metadata = {key: value for key, value in capture.items()
                if key not in ('html', 'initial_html_base64', 'screenshot_base64')}
    artifacts = {'raw_file': ('.html', capture['html'].encode('utf-8'))}
    for key, suffix, source in [('initial_html_file', '.initial.html', 'initial_html_base64'),
                                ('screenshot_file', '.png', 'screenshot_base64')]:
        if capture.get(source):
            artifacts[key] = (suffix, base64.b64decode(capture[source], validate=True))
    metadata['artifact_hashes'] = {}
    for key, (suffix, data) in artifacts.items():
        path = RAW_DIR / (stem + suffix)
        preserve(path, data)
        metadata[key] = str(path)
        metadata['artifact_hashes'][key] = hashlib.sha256(data).hexdigest()
    metadata['html_bytes'] = len(artifacts['raw_file'][1])
    metadata['initial_html_bytes'] = len(artifacts.get('initial_html_file', ('', b''))[1]) if 'initial_html_file' in artifacts else None
    metadata['metadata_file'] = str(RAW_DIR / (stem + '.navigation.json'))
    preserve(Path(metadata['metadata_file']), json_bytes(metadata))
    return stem, metadata


def verify_storage(result, rows):
    with sqlite3.connect(DATABASE_FILE) as connection:
        connection.row_factory = sqlite3.Row
        stored = [dict(row) for row in connection.execute(
            f'SELECT {",".join(FIELDS)} FROM search_snapshots WHERE crawl_time=? AND keyword=? ORDER BY search_position',
            (result['crawl_time'], result['keyword']))]
        run = dict(connection.execute('SELECT * FROM collection_runs WHERE crawl_time=? AND keyword=?',
                                     (result['crawl_time'], result['keyword'])).fetchone())
        duplicates = connection.execute('''SELECT COUNT(*) FROM (
            SELECT crawl_time,keyword,asin FROM search_snapshots GROUP BY crawl_time,keyword,asin HAVING COUNT(*)>1)''').fetchone()[0]
        checks = {'integrity_check': connection.execute('PRAGMA integrity_check').fetchone()[0],
                  'foreign_key_errors': [tuple(row) for row in connection.execute('PRAGMA foreign_key_check')],
                  'collection_runs': [dict(row) for row in connection.execute('SELECT crawl_time,keyword,collection_method,status_code,outcome,marketplace,currency,inserted_rows FROM collection_runs')],
                  'snapshot_count_total': connection.execute('SELECT COUNT(*) FROM search_snapshots').fetchone()[0],
                  'snapshot_count_this_run': len(stored), 'duplicate_snapshot_keys': duplicates,
                  'stored_rows_equal_parsed': stored == rows,
                  'schema': {table: [dict(row) for row in connection.execute(f'PRAGMA table_info({table})')]
                             for table in ('collection_runs', 'search_snapshots')},
                  'value_types': {field: [row[0] for row in connection.execute(
                      f'SELECT DISTINCT typeof({field}) FROM search_snapshots WHERE crawl_time=? AND keyword=?',
                      (result['crawl_time'], result['keyword']))] for field in FIELDS},
                  'select_first_five': stored[:5]}
    assert checks['integrity_check'] == 'ok'
    assert not checks['foreign_key_errors'] and not duplicates and stored == rows
    assert run['collection_method'] == 'playwright' and run['inserted_rows'] == len(rows)
    for key, digest in result['artifact_hashes'].items():
        assert hashlib.sha256(Path(result[key]).read_bytes()).hexdigest() == digest
    return checks


def run(capture):
    stem, metadata = save_capture(capture)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=LOG_FILE, level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    logging.info('Playwright probe start_time=%s keyword=%s method=GET navigation_attempts=1', metadata['crawl_time'], metadata['keyword'])
    _, cards, page = detect_page(capture['html'], metadata['status_code'], metadata['final_url'])
    marketplace = urlparse(metadata['final_url']).hostname
    currency = {'www.amazon.com': 'USD', 'www.amazon.sg': 'SGD'}.get(marketplace)
    errors = list(page['page_errors'])
    if metadata['navigation_error']:
        errors.append(metadata['navigation_error'])
    if currency is None:
        errors.append('unsupported_marketplace')
    rows, quality = parse_candidates([] if errors else cards, metadata['crawl_time'],
                                     metadata['keyword'], metadata['final_url'], currency)
    initial_rows, initial_quality, initial_count = [], None, None
    if capture.get('initial_html_base64'):
        initial = base64.b64decode(capture['initial_html_base64'])
        _, initial_cards, _ = detect_page(initial, metadata['status_code'], metadata['final_url'])
        initial_count = len(initial_cards)
        initial_rows, initial_quality = parse_candidates([] if errors else initial_cards,
            metadata['crawl_time'], metadata['keyword'], metadata['final_url'], currency)
    source = 'initial_html' if rows and initial_rows == rows else 'cannot_confirm'
    result = {**metadata, **page, **quality, 'errors': errors, 'marketplace': marketplace,
              'currency': currency, 'initial_candidate_count': initial_count,
              'initial_rows_equal_dom_rows': bool(rows) and initial_rows == rows,
              'initial_quality': initial_quality, 'product_data_source': source,
              'marketplace_matches_initial_url': marketplace == urlparse(metadata['initial_url']).hostname,
              'network_resource_counts': dict(Counter(n['resource_type'] for n in metadata['network'])),
              'network_status_counts': dict(Counter(str(n['status']) for n in metadata['network'])),
              'outcome': 'source_unavailable' if errors else ('success' if marketplace == 'www.amazon.com' else 'success_other_marketplace'),
              'rows': rows, 'exit_code': 3 if errors else 0}
    inserted, storage_status = store_run(result, rows)
    result['inserted_rows_this_execution'] = inserted
    result['storage_status'] = storage_status
    verification = verify_storage(result, rows)
    result['snapshot_rows_this_run'] = verification['snapshot_count_this_run']
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    result_path = RESULT_DIR / (stem + '.result.json')
    if result_path.exists():
        # 离线重放沿用首次采集审计，不覆盖首次新增行数。
        original_result = json.loads(result_path.read_text(encoding='utf-8'))
        if original_result['rows'] != rows:
            raise ValueError('Parser output changed; retain old snapshot and inspect before migration')
        result = original_result
    else:
        preserve(result_path, json_bytes(result))
    preserve(RESULT_DIR / (stem + '.verification.json'), json_bytes(verification))
    write_report(result, verification)
    logging.info('Playwright status=%s final_url=%s candidate_count=%s parsed_count=%s missing_statistics=%s SQLite_inserted_rows=%s errors=%s end_time=%s',
                 metadata['status_code'], metadata['final_url'], len(cards), len(rows),
                 quality['missing_statistics'], inserted, errors, metadata['end_time'])
    summary = {key: result[key] for key in ('status_code','final_url','page_title','html_bytes',
        'initial_html_bytes','candidate_count','parsed_count','marketplace','currency','product_data_source',
        'inserted_rows_this_execution','outcome','exit_code','metadata_file')}
    summary['inserted_rows_this_execution'] = inserted
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return result['exit_code']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture-json', type=Path, required=True, help='Playwright CLI --raw run-code 输出文件（离线，不导航）')
    arguments = parser.parse_args()
    raise SystemExit(run(json.loads(arguments.capture_json.read_text(encoding='utf-8'))))
