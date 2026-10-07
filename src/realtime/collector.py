"""单关键词、单页采集；可离线重放真实响应，遇到限制停止。"""
import argparse
import hashlib
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.realtime.config import KEYWORD, RAW_DIR, LOG_FILE, RESULT_DIR, FIELDS
from src.realtime.parser import detect_page, parse_candidates
from src.realtime.storage import store_run
from src.realtime.reporting import generate_reports


def save_without_overwriting(path,content):
    if path.exists():
        if path.read_bytes()!=content:
            raise RuntimeError(f'同一快照文件已存在且内容不同，禁止覆盖：{path}')
        return
    with path.open('xb') as file:
        file.write(content)


def preserve_response(meta,body):
    time=datetime.fromisoformat(meta['crawl_time']).astimezone(timezone.utc)
    slug=re.sub(r'[^a-z0-9]+','_',meta['keyword'].lower()).strip('_')
    key=f'{slug}_{time.strftime("%Y%m%dT%H%M%S%fZ")}'
    raw_path=RAW_DIR/f'{key}.html'
    meta={**meta,'raw_file':str(raw_path),'raw_sha256':hashlib.sha256(body).hexdigest()}
    save_without_overwriting(raw_path,body)
    metadata=RAW_DIR/f'{key}.response.json'
    save_without_overwriting(metadata,(json.dumps(meta,ensure_ascii=False,indent=2)+'\n').encode())
    return meta,key,metadata


def run(replay=None):
    RAW_DIR.mkdir(parents=True,exist_ok=True)
    RESULT_DIR.mkdir(parents=True,exist_ok=True)
    LOG_FILE.parent.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(filename=str(LOG_FILE),filemode='a',level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s',force=True)
    logger=logging.getLogger(__name__)
    processing_start=datetime.now(timezone.utc).isoformat()
    logger.info('start_time=%s keyword=%s mode=%s',processing_start,KEYWORD,'offline_replay' if replay else 'live_single_request')
    if replay:
        meta=json.loads(Path(replay).read_text())
        if meta['keyword']!=KEYWORD:
            raise ValueError('V1 仅允许 garden hose。')
        body=Path(meta['raw_file']).read_bytes()
        if meta.get('raw_sha256') and hashlib.sha256(body).hexdigest()!=meta['raw_sha256']:
            raise ValueError('真实响应校验值不一致。')
    else:
        # requests 的环境兼容警告保持可见，未设置 warnings 过滤器。
        from src.realtime.fetcher import fetch_once
        meta,body=fetch_once()
    meta,key,metadata=preserve_response(meta,body)
    logger.info('crawl_time=%s request_method=%s request_performed_this_execution=%s status_code=%s final_url=%s',
                meta['crawl_time'],meta['request_method'],not bool(replay),meta.get('status_code'),meta.get('final_url'))
    _,cards,page=detect_page(body,meta.get('status_code'),meta.get('final_url'))
    errors=list(meta.get('errors',[]))+page['page_errors']
    # 错误页、验证码、登录页不能作为商品搜索页继续解析。
    rows,quality=parse_candidates([] if errors else cards,meta['crawl_time'],KEYWORD,meta.get('final_url') or '')
    if not errors and not rows:
        errors.append('no_valid_products; successful product parsing not verified')
    result={**meta,**page,**quality,'errors':errors,'processing_start':processing_start,
            'mode':'offline_replay' if replay else 'live_single_request',
            'request_performed_this_execution':not bool(replay),
            'http_success':bool(meta.get('status_code') is not None and 200<=meta['status_code']<300),
            'response_received':meta.get('status_code') is not None,
            'outcome':'success' if not errors else 'source_unavailable',
            'response_metadata_file':str(metadata)}
    inserted,storage_status=store_run(result,rows)
    result.update(inserted_rows=inserted,storage_status=storage_status,
                  end_time=datetime.now(timezone.utc).isoformat(),exit_code=0 if not errors else 3)
    logger.info('candidate_count=%s selected_count=%s parsed_count=%s duplicate_asin_count=%s',
                result['candidate_count'],result['selected_candidate_count'],result['parsed_count'],result['duplicate_asin_count'])
    logger.info('missing_statistics=%s conversion_issues=%s',json.dumps(result['missing_statistics'],ensure_ascii=False),json.dumps(result['conversion_issues'],ensure_ascii=False))
    logger.info('SQLite_inserted_rows=%s storage_status=%s errors=%s raw_file=%s end_time=%s exit_code=%s',
                inserted,storage_status,json.dumps(errors,ensure_ascii=False),result['raw_file'],result['end_time'],result['exit_code'])
    (RESULT_DIR/f'{key}.result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    generate_reports(result,rows)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return result['exit_code']


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--replay',type=Path,help='离线处理已保存的真实响应元数据；不再发起网络请求')
    args=parser.parse_args()
    try:
        return run(args.replay)
    except Exception as error:
        logging.getLogger(__name__).exception('errors=%s end_time=%s exit_code=1',error,datetime.now(timezone.utc).isoformat())
        print(f'{type(error).__name__}: {error}',file=sys.stderr)
        return 1


if __name__=='__main__':
    sys.exit(main())
