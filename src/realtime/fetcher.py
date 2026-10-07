"""单次普通请求，保留非 2xx 响应；不重试、不伪装、不使用代理池。"""
from datetime import datetime, timezone
import requests

from src.realtime.config import SEARCH_URL, KEYWORD, REQUEST_TIMEOUT, MAX_RESPONSE_BYTES


def fetch_once():
    meta={'crawl_time':datetime.now(timezone.utc).isoformat(),'keyword':KEYWORD,
          'request_method':'requests GET','requested_url':SEARCH_URL,
          'user_agent':requests.utils.default_user_agent(),'errors':[]}
    chunks=[]
    try:
        with requests.Session() as session:
            session.max_redirects=3
            with session.get(SEARCH_URL,timeout=REQUEST_TIMEOUT,stream=True) as response:
                meta.update(status_code=response.status_code,final_url=response.url,
                            redirects=[{'status':r.status_code,'url':r.url} for r in response.history],
                            content_type=response.headers.get('Content-Type'),encoding=response.encoding)
                size=0
                for chunk in response.iter_content(65536):
                    available=MAX_RESPONSE_BYTES-size
                    chunks.append(chunk[:available])
                    size+=len(chunk)
                    if size>MAX_RESPONSE_BYTES:
                        meta['errors'].append('response_exceeds_10_MiB; partial response not parsed')
                        meta['response_truncated']=True
                        break
    except requests.RequestException as error:
        meta['errors'].append(f'{type(error).__name__}: {error}')
    body=b''.join(chunks)
    meta.update(response_bytes=len(body),end_time=datetime.now(timezone.utc).isoformat())
    return meta,body
