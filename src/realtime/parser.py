"""保守提取候选商品，严格校验；未在真实成功搜索页验证的选择器不宣称稳定。"""
import re
from collections import Counter
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

from src.realtime.config import FIELDS, MAX_PRODUCTS

ASIN_PATTERN = re.compile(r'^[A-Z0-9]{10}$')


def detect_page(html, status, final_url):
    soup = BeautifulSoup(html, 'html.parser')
    title = soup.title.get_text(' ', strip=True) if soup.title else None
    text = soup.get_text(' ', strip=True).lower()
    captcha = bool(soup.select('form[action*="validateCaptcha"], input[name="amzn-captcha-token"]')) or 'enter the characters you see below' in text
    robot = 'robot check' in (title or '').lower() or 'sorry, we just need to make sure you' in text
    login = '/ap/signin' in (final_url or '') or bool(soup.select('input[type="password"]'))
    cards = soup.select('[data-component-type="s-search-result"]')
    errors = []
    if status is None:
        errors.append('transport_error')
    elif not 200 <= status < 300:
        errors.append(f'http_{status}')
    if captcha: errors.append('captcha')
    if robot: errors.append('robot_check')
    if login: errors.append('login_required')
    if not cards and not errors:
        errors.append('no_search_product_cards; cannot distinguish empty results from changed DOM')
    return soup, cards, {'page_title': title, 'captcha': captcha, 'robot_check': robot,
                        'login_required': login, 'forbidden_403': status == 403,
                        'candidate_count': len(cards), 'page_errors': errors,
                        'automated_access_notice': b'to discuss automated access' in html.lower() if isinstance(html,bytes) else 'to discuss automated access' in html.lower()}


def numeric(value, field, issues, currency="USD"):
    if value is None or not str(value).strip():
        return None
    text = str(value).strip()
    if field == 'price':
        # 币种必须与展示符号相符；不做汇率换算或把单价当报价。
        prefix = {'USD': '$', 'SGD': 'S$'}.get(currency)
        match = re.fullmatch(re.escape(prefix) + r'\s*(\d+(?:,\d{3})*(?:\.\d{1,2})?)', text) if prefix else None
        if match:
            result = float(match.group(1).replace(',', ''))
            if result > 0: return result
    elif field == 'rating':
        match = re.fullmatch(r'(\d(?:\.\d+)?) out of 5 stars', text)
        if match:
            result = float(match.group(1))
            if 1 <= result <= 5: return result
    elif field == 'review_count':
        # “1K+”或多个数字串不猜测成精确评价量。
        text = text[1:-1] if text.startswith('(') and text.endswith(')') else text
        if re.fullmatch(r'(?:\d+|\d{1,3}(?:,\d{3})+)', text):
            return int(text.replace(',', ''))
    elif field == 'search_position':
        if re.fullmatch(r'\d+', text) and int(text)>0:
            return int(text)
    issues.append({'field': field, 'raw_value': text, 'reason': 'unparseable_or_out_of_range'})
    return None


def standard_product_url(href, asin, base_url, issues):
    if not href:
        return None
    url = urljoin(base_url, href)
    parsed = urlparse(url)
    match = re.search(r'/(?:dp|gp/product)/([A-Z0-9]{10})(?:/|$)', parsed.path)
    host = urlparse(base_url).hostname
    if host in ('www.amazon.com', 'www.amazon.sg') and parsed.hostname == host and match and match.group(1)==asin:
        return f'https://{host}/dp/{asin}'
    issues.append({'field':'product_url','raw_value':href,'reason':'not_a_matching_direct_amazon_product_url'})
    return None


def review_count_text(card):
    link = card.select_one('a[href*="customerReviews"]')
    if link is None:
        return None
    # 无障碍标签有精确 ratings 数时优先取它，不从 K 缩写猜数。
    label = link.get('aria-label', '')
    exact = re.fullmatch(r'([\d,]+) ratings?', label)
    return exact.group(1) if exact else link.get_text(' ', strip=True)


def parse_candidates(cards, crawl_time, keyword, base_url, currency="USD"):
    rows, issues, rejected = [], [], []
    for position, card in enumerate(cards[:MAX_PRODUCTS], 1):
        asin = (card.get('data-asin') or '').strip().upper()
        row_issues = []
        if not ASIN_PATTERN.fullmatch(asin):
            rejected.append({'search_position':position,'asin':asin or None,'reason':'missing_or_invalid_asin'})
            continue
        title_node = card.select_one('h2')
        title = title_node.get_text(' ', strip=True) if title_node else None
        link = title_node.find_parent('a') if title_node else None
        if link is None: link = card.select_one('a[href*="/dp/"], a[href*="/gp/product/"]')
        price_node = card.select_one('.a-price:not(.a-text-price) .a-offscreen')
        rating_node = card.select_one('.a-icon-star-small .a-icon-alt, .a-icon-star .a-icon-alt, .a-icon-star-mini .a-icon-alt')
        row = {'crawl_time':crawl_time,'keyword':keyword,
               'search_position':numeric(str(position),'search_position',row_issues),
               'asin':asin,'title':title or None,
               'price':numeric(price_node.get_text(strip=True) if price_node else None,'price',row_issues,currency),
               'rating':numeric(rating_node.get_text(strip=True) if rating_node else None,'rating',row_issues),
               'review_count':numeric(review_count_text(card),'review_count',row_issues),
               'product_url':standard_product_url(link.get('href') if link else None,asin,base_url,row_issues)}
        rows.append(row)
        issues.extend({'search_position':position,**issue} for issue in row_issues)
    frequencies = Counter(row['asin'] for row in rows)
    duplicates = sum(count-1 for count in frequencies.values())
    # 同次结果同 ASIN 只保存首次出现的位置；原始页和重复数仍保留。
    unique = list({row['asin']:row for row in reversed(rows)}.values())
    unique.sort(key=lambda row:row['search_position'])
    missing = {field:{'missing_count':sum(row[field] is None for row in rows),
                      'denominator':len(rows),
                      'missing_rate':sum(row[field] is None for row in rows)/len(rows) if rows else None}
               for field in FIELDS}
    attempted = min(len(cards),MAX_PRODUCTS)
    candidate_asin_missing = sum(not (card.get('data-asin') or '').strip() for card in cards[:MAX_PRODUCTS])
    return unique, {'selected_candidate_count':attempted,'parsed_count':len(rows),
                    'unique_parsed_count':len(unique),'rejected_candidates':rejected,
                    'candidate_asin_missing_rate':candidate_asin_missing/attempted if attempted else None,
                    'invalid_asin_count':len(rejected),'duplicate_asin_count':duplicates,
                    'missing_statistics':missing,'conversion_issues':issues}
