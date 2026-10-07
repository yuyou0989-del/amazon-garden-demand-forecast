"""逐行读取及字段统计；关系和去重统计交给磁盘 SQLite。"""
import csv
import json
import math
from collections import Counter
from datetime import datetime, timezone

from src.config import TIME_START, TIME_END


def is_missing(value):
    # 空容器代表没有有效内容；另行报告 null/空白/空容器的具体数量。
    return value is None or value == '' or value == [] or value == {} or (
        isinstance(value, str) and not value.strip())


def number(value):
    if is_missing(value) or isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def parse_time(value):
    numeric = number(value)
    if numeric is None:
        return None
    try:
        # 官方数据实际 Unix 毫秒；不自动猜测单位或纠正异常值。
        return datetime.fromtimestamp(numeric / 1000, timezone.utc)
    except (ValueError, OverflowError, OSError):
        return None


def read_records(path, kind):
    with path.open(encoding='utf-8', newline='') as file:
        if kind == 'reviews':
            for row in csv.DictReader(file):
                # CSV 没有原生 dtype；保留原始字符串，不凭内容强制转换。
                yield row
        else:
            for line_number, line in enumerate(file, 1):
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as error:
                    raise ValueError(f'{path}:{line_number}: {error}') from error
                if not isinstance(row, dict):
                    raise ValueError(f'{path}:{line_number}: 不是 JSON 对象')
                yield row


def profile_file(connection, path, kind):
    fields, first_five, count, duplicates = {}, [], 0, 0
    years, ratings, categories = Counter(), Counter(), Counter()
    main_categories = Counter()
    times, flags = [], Counter()
    low, high = datetime.fromisoformat(TIME_START), datetime.fromisoformat(TIME_END)
    connection.execute(f'CREATE TABLE {kind}_canonical (row TEXT PRIMARY KEY)')
    for row in read_records(path, kind):
        count += 1
        if count <= 5:
            first_five.append(row)
        for key, value in row.items():
            if key not in fields:
                fields[key] = {'present': 0, 'missing': 0, 'null': 0, 'empty': 0,
                               'types': Counter(), 'example': None}
            field = fields[key]
            field['present'] += 1
            field['types'][type(value).__name__] += 1
            field['missing'] += int(is_missing(value))
            field['null'] += int(value is None)
            field['empty'] += int(is_missing(value) and value is not None)
            if field['example'] is None and not is_missing(value):
                field['example'] = value
        canonical = json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
        cursor = connection.execute(f'INSERT OR IGNORE INTO {kind}_canonical VALUES (?)', (canonical,))
        duplicates += int(cursor.rowcount == 0)
        parent = row.get('parent_asin')
        if kind == 'reviews':
            rating = number(row.get('rating'))
            time = parse_time(row.get('timestamp'))
            raw_rating = row.get('rating')
            if not is_missing(raw_rating):
                ratings[str(raw_rating)] += 1
                flags['invalid_rating'] += int(rating is None or rating not in (1, 2, 3, 4, 5))
            if not is_missing(row.get('timestamp')):
                flags['unparseable_timestamp'] += int(time is None)
            if time:
                years[str(time.year)] += 1
                flags['outside_source_window'] += int(time < low or time >= high)
                iso_time = time.isoformat()
                if not times:
                    times = [iso_time, iso_time]
                times = [min(times[0], iso_time), max(times[1], iso_time)]
            verified = row.get('verified_purchase')
            verified_bool = verified if isinstance(verified, bool) else None
            connection.execute('INSERT INTO reviews VALUES (?,?,?,?,?,?,?)',
                               (parent, row.get('asin'), row.get('user_id'), rating,
                                number(row.get('timestamp')), verified_bool,
                                number(row.get('helpful_vote'))))
        else:
            main_categories[str(row.get('main_category'))] += 1
            price = number(row.get('price'))
            if not is_missing(row.get('price')):
                flags['invalid_price'] += int(price is None or price <= 0)
            details = row.get('details')
            brand = details.get('Brand') if isinstance(details, dict) else None
            flags['missing_details_brand'] += int(is_missing(brand))
            for label in row.get('categories') or []:
                categories[str(label)] += 1
            connection.execute('INSERT INTO metadata VALUES (?,?,?,?,?,?)',
                               (parent, price, number(row.get('average_rating')),
                                number(row.get('rating_number')), row.get('store'), brand))
        if count % 10000 == 0:
            connection.commit()
    connection.commit()
    for field in fields.values():
        field['absent'] = count - field['present']
        field['missing'] += field['absent']
        field['missing_rate'] = field['missing'] / count if count else None
        field['types'] = dict(field['types'])
    return {'file': str(path), 'bytes': path.stat().st_size, 'rows': count,
            'columns': len(fields), 'fields': fields, 'first_five': first_five,
            'duplicates': duplicates, 'time_min': times[0] if times else None,
            'time_max': times[1] if times else None, 'by_year': dict(sorted(years.items())),
            'rating_distribution': dict(sorted(ratings.items())), 'flags': dict(flags),
            'main_category_distribution': dict(main_categories),
            'category_labels': len(categories), 'category_top20': categories.most_common(20)}


def distribution(connection, query):
    """排序和精确分位数在磁盘中执行，不把完整数列载入内存。"""
    total, minimum, maximum, average = connection.execute(
        f'SELECT COUNT(*),MIN(value),MAX(value),AVG(value) FROM ({query})').fetchone()
    result = {'count': total, 'min': minimum, 'max': maximum, 'mean': average}
    for quantile in (0.25, 0.5, 0.75, 0.95, 0.99):
        value = None
        if total:
            position = (total - 1) * quantile
            lower, upper = math.floor(position), math.ceil(position)
            a = connection.execute(f'SELECT value FROM ({query}) ORDER BY value LIMIT 1 OFFSET ?', (lower,)).fetchone()[0]
            b = connection.execute(f'SELECT value FROM ({query}) ORDER BY value LIMIT 1 OFFSET ?', (upper,)).fetchone()[0]
            value = a + (b - a) * (position - lower)
        result[f'p{int(quantile * 100)}'] = value
    return result
