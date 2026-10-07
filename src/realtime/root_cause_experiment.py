"""四组一次性诊断；仅 --live 会发网络请求，--report-only 只读既有证据。"""
import argparse
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from src.realtime.config import REALTIME_DIR, REPORT_DIR
from src.realtime.parser import detect_page

DIAGNOSTICS = REALTIME_DIR / 'diagnostics'
URLS = {'com': 'https://www.amazon.com/s?k=garden+hose',
        'sg': 'https://www.amazon.sg/s?k=garden+hose'}
EXPERIMENTS = [('A', 'requests', 'com'), ('B', 'requests', 'sg'),
               ('C', 'playwright', 'com'), ('D', 'playwright', 'sg')]
CHROME = Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
MAX_BODY = 10 * 1024 * 1024
KEY_HEADERS = ('server', 'content-type', 'content-length', 'location', 'retry-after',
               'via', 'x-cache', 'set-cookie')


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def write_once(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(data)


def save_json(path, value):
    write_once(path, (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))


def market(url):
    host = urlparse(url or '').hostname
    if host in ('amazon.com', 'www.amazon.com'):
        return 'amazon.com'
    if host in ('amazon.sg', 'www.amazon.sg'):
        return 'amazon.sg'
    return host


def public_headers(headers):
    """报告只列非敏感诊断值；完整响应头留在本地 headers JSON。"""
    lower = {k.lower(): v for k, v in headers.items()}
    result = {k: lower.get(k) for k in KEY_HEADERS if k != 'set-cookie'}
    cookies = lower.get('set-cookie')
    result['set-cookie_present'] = cookies is not None
    result['set-cookie_names'] = re.findall(r'(?:^|,\s*)([^=;\s,]+)=', cookies or '')
    for k, v in lower.items():
        if any(part in k for part in ('cache','cdn','gateway','amz','x-serv','x-ec2')) and k not in result:
            result[k] = v
    return result


def page_observation(body, status, final_url):
    _, cards, page = detect_page(body, status, final_url)
    html = body.decode('utf-8', 'replace') if isinstance(body, bytes) else body
    soup = BeautifulSoup(html, 'html.parser')
    visible = soup.get_text(' ', strip=True)
    image_alt = ' | '.join(img.get('alt', '') for img in soup.select('img[alt]') if img.get('alt'))[:300]
    explicit_access = bool(re.search(r'access denied|automated access denied|unusual traffic|too many requests', visible, re.I))
    return {'title': page['page_title'], 'candidate_count': len(cards),
            'normal_products': status is not None and 200 <= status < 300 and len(cards) > 0,
            'captcha': page['captcha'], 'robot_check': page['robot_check'],
            'login_required': page['login_required'], 'explicit_access_limit': explicit_access,
            'automated_access_comment': page['automated_access_notice'],
            'visible_text_excerpt': visible[:400], 'image_alt_excerpt': image_alt,
            'page_errors': page['page_errors']}


def persist(experiment, body, headers, chain, screenshot=None, dom=None):
    stamp = experiment['timestamp'].replace('-', '').replace(':', '').replace('+00:00', 'Z').replace('.', '')
    stem = f"{experiment['experiment_id']}_{stamp}"
    directory = DIAGNOSTICS / stem
    directory.mkdir(parents=True, exist_ok=False)
    write_once(directory / 'response.body', body)
    save_json(directory / 'headers.json', headers)
    save_json(directory / 'redirect_chain.json', chain)
    if screenshot is not None:
        write_once(directory / 'screenshot.png', screenshot)
    if dom is not None:
        write_once(directory / 'dom.html', dom.encode('utf-8'))
    experiment['evidence_directory'] = str(directory)
    experiment['body_sha256'] = hashlib.sha256(body).hexdigest()
    experiment['body_bytes'] = len(body)
    experiment['observation'] = page_observation(dom or body, experiment['status'], experiment['final_url'])
    experiment['explicit_stop'] = (experiment['status'] == 403 or
                                   experiment['observation']['captcha'] or
                                   experiment['observation']['robot_check'] or
                                   experiment['observation']['login_required'] or
                                   experiment['observation']['explicit_access_limit'])
    save_json(directory / 'response_metadata.json', experiment)
    return experiment


def request_once(experiment_id, market_code):
    import requests
    url = URLS[market_code]
    meta = {'experiment_id': experiment_id, 'timestamp': utc_now(), 'client': 'requests',
            'requested_url': url, 'requested_marketplace': market(url),
            'method': 'GET', 'client_version': requests.__version__,
            'user_agent': requests.utils.default_user_agent(),
            'final_url': None, 'final_marketplace': None, 'status': None, 'error': None,
            'end_time': None, 'redirect_chain': []}
    body, header_record, chain = b'', [], []
    try:
        with requests.Session() as session:
            session.max_redirects = 3
            with session.get(url, stream=True, timeout=(15, 35)) as response:
                responses = [*response.history, response]
                for item in responses:
                    h = dict(item.headers)
                    chain.append({'url': item.url, 'status': item.status_code,
                                  'location': h.get('Location'), 'content_type': h.get('Content-Type')})
                    header_record.append({'url': item.url, 'status': item.status_code,
                                          'response_headers': h,
                                          'diagnostic_headers': public_headers(h)})
                meta.update(status=response.status_code, final_url=response.url,
                            final_marketplace=market(response.url))
                chunks, size = [], 0
                for chunk in response.iter_content(65536):
                    size += len(chunk)
                    if size > MAX_BODY:
                        meta['error'] = 'body_exceeded_10_MiB; saved first 10 MiB only'
                        chunks.append(chunk[:MAX_BODY-(size-len(chunk))])
                        break
                    chunks.append(chunk)
                body = b''.join(chunks)
    except requests.RequestException as exc:
        meta['error'] = f'{type(exc).__name__}: {exc}'
    meta['end_time'] = utc_now()
    meta['redirect_chain'] = chain
    return persist(meta, body, header_record, chain)


def browser_once(browser, experiment_id, market_code):
    url = URLS[market_code]
    meta = {'experiment_id': experiment_id, 'timestamp': utc_now(), 'client': 'playwright',
            'requested_url': url, 'requested_marketplace': market(url), 'method': 'GET',
            'browser': 'existing system Google Chrome, headed, fresh default context',
            'final_url': None, 'final_marketplace': None, 'status': None, 'error': None,
            'end_time': None, 'redirect_chain': []}
    context = browser.new_context()
    page = context.new_page()
    seen = []
    def on_response(response):
        try:
            request = response.request
            if request.resource_type == 'document' and request.is_navigation_request():
                h = response.all_headers()
                seen.append({'url': response.url, 'status': response.status,
                             'location': h.get('location'), 'content_type': h.get('content-type'),
                             'response_headers': h, 'diagnostic_headers': public_headers(h),
                             'request_cookie_present': bool(request.all_headers().get('cookie'))})
        except Exception as exc:
            meta.setdefault('event_errors', []).append(str(exc))
    page.on('response', on_response)
    response = None
    try:
        # 唯一的顶层导航；没有重试、刷新或会话恢复。
        response = page.goto(url, wait_until='domcontentloaded', timeout=45000)
    except Exception as exc:
        meta['error'] = f'{type(exc).__name__}: {exc}'
    if response is not None:
        meta['status'] = response.status
    meta['final_url'] = page.url
    meta['final_marketplace'] = market(page.url)
    body = b''
    if response is not None:
        try:
            body = response.body()
        except Exception as exc:
            meta['body_error'] = str(exc)
    try:
        dom = page.content()
    except Exception as exc:
        meta['dom_error'] = str(exc)
        dom = ''
    try:
        screenshot = page.screenshot(timeout=10000)
    except Exception as exc:
        meta['screenshot_error'] = str(exc)
        screenshot = None
    meta['final_url'] = page.url
    meta['final_marketplace'] = market(page.url)
    meta['end_time'] = utc_now()
    # 只保留本次顶层导航的 document 响应，不把页面图片/XHR 当实验组。
    chain = [{'url': item['url'], 'status': item['status'],
              'location': item['location'], 'content_type': item['content_type']}
             for item in seen]
    if not chain and response is not None:
        h = response.all_headers()
        seen.append({'url': response.url, 'status': response.status,
                     'location': h.get('location'), 'content_type': h.get('content-type'),
                     'response_headers': h, 'diagnostic_headers': public_headers(h),
                     'request_cookie_present': bool(response.request.all_headers().get('cookie'))})
        chain = [{'url': response.url, 'status': response.status,
                  'location': h.get('location'), 'content_type': h.get('content-type')}]
    meta['redirect_chain'] = chain
    result = persist(meta, body, seen, chain, screenshot=screenshot, dom=dom)
    context.close()
    return result


def run_live():
    DIAGNOSTICS.mkdir(parents=True, exist_ok=True)
    if any(DIAGNOSTICS.glob('*/response_metadata.json')):
        raise RuntimeError('已有实验结果；禁止再次运行 --live。使用 --report-only 离线修复。')
    results = []
    blocked_markets = set()
    for eid, client, code in EXPERIMENTS[:2]:
        result = request_once(eid, code)
        results.append(result)
        print(f"{eid}: requests {result['requested_marketplace']} -> {result['final_marketplace']} status={result['status']} saved={result['evidence_directory']}", flush=True)
        if result['explicit_stop']:
            blocked_markets.add(code)
        time.sleep(3)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=str(CHROME), headless=False)
        try:
            for eid, client, code in EXPERIMENTS[2:]:
                if code in blocked_markets:
                    results.append({'experiment_id': eid, 'client': client,
                                    'requested_marketplace': market(URLS[code]),
                                    'status': None, 'not_run_reason': 'explicit_access_limit_on_same_marketplace'})
                    continue
                result = browser_once(browser, eid, code)
                results.append(result)
                print(f"{eid}: Playwright {result['requested_marketplace']} -> {result['final_marketplace']} status={result['status']} saved={result['evidence_directory']}", flush=True)
                if result['explicit_stop']:
                    blocked_markets.add(code)
                time.sleep(3)
        finally:
            browser.close()
    return results


def load_results():
    results = []
    for eid, _, _ in EXPERIMENTS:
        found = list(DIAGNOSTICS.glob(f'{eid}_*/response_metadata.json'))
        if len(found) > 1:
            raise ValueError(f'Multiple observations for {eid}; no cherry-picking allowed')
        if found:
            results.append(json.loads(found[0].read_text(encoding='utf-8')))
        else:
            results.append({'experiment_id': eid, 'not_run_reason': 'no_saved_evidence'})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--live', action='store_true')
    modes.add_argument('--report-only', action='store_true')
    args = parser.parse_args()
    if args.live:
        run_live()
    else:
        print(json.dumps(load_results(), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
