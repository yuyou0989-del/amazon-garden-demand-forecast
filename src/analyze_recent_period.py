"""扫描完整 5-core，统计最近时期与仅使用过去信息的 cohort 候选条件。"""
import csv
import gzip
import json
import sqlite3
from collections import Counter
from datetime import timedelta

from src.config import REVIEW_FILE, OUTPUT_DIR, STAGE15_DATABASE
from src.profiling import parse_time, number, distribution


def write_csv(path, rows):
    if not rows:
        raise ValueError(f'没有可写结果: {path}')
    with path.open('w', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def load_full_core(connection):
    connection.execute('DROP TABLE IF EXISTS interactions')
    connection.execute('''CREATE TABLE interactions(
        parent TEXT, user TEXT, timestamp REAL, rating REAL,
        year INTEGER, month TEXT, week TEXT)''')
    counts, batch, total = Counter(), [], 0
    first, last = None, None
    with gzip.open(REVIEW_FILE, 'rt') as file:
        reader = csv.DictReader(file)
        fields = reader.fieldnames
        for row in reader:
            total += 1
            time = parse_time(row.get('timestamp'))
            if time is None or not row.get('parent_asin') or not row.get('user_id'):
                counts['invalid_key_or_time'] += 1
                continue
            first = min(first, time) if first else time
            last = max(last, time) if last else time
            counts[f'year_{time.year}'] += 1
            if 2018 <= time.year <= 2023:
                week = (time - timedelta(days=time.weekday())).date().isoformat()
                batch.append((row['parent_asin'], row['user_id'], number(row['timestamp']),
                              number(row['rating']), time.year, time.strftime('%Y-%m-01'), week))
            if len(batch) >= 10000:
                connection.executemany('INSERT INTO interactions VALUES (?,?,?,?,?,?,?)', batch)
                connection.commit()
                batch.clear()
            if total % 500000 == 0:
                print(f'已扫描 {total:,} 条完整 5-core 交互', flush=True)
    connection.executemany('INSERT INTO interactions VALUES (?,?,?,?,?,?,?)', batch)
    connection.commit()
    print('建立时间和商品索引', flush=True)
    connection.executescript('''
        CREATE INDEX interaction_month ON interactions(month);
        CREATE INDEX interaction_parent_month ON interactions(parent,month);
    ''')
    return {'source_rows': total, 'source_fields': fields,
            'invalid_key_or_time': counts['invalid_key_or_time'],
            'full_time_min': first.isoformat(), 'full_time_max': last.isoformat(),
            'all_year_counts': {key[5:]: value for key,value in counts.items() if key.startswith('year_')},
            'recent_rows_in_database': connection.execute('SELECT COUNT(*) FROM interactions').fetchone()[0]}


def analyze_history(connection):
    connection.executescript('''
        DROP TABLE IF EXISTS cohort_history;
        CREATE TABLE cohort_history AS
        SELECT parent, COUNT(*) AS historical_interactions,
               COUNT(DISTINCT month) AS historical_active_months,
               MIN(month) AS first_history_month, MAX(month) AS last_history_month,
               MIN(timestamp) AS min_timestamp, MAX(timestamp) AS max_timestamp
        FROM interactions WHERE month>='2019-01-01' AND month<'2020-01-01'
        GROUP BY parent;
        CREATE UNIQUE INDEX history_parent ON cohort_history(parent);
    ''')
    candidates = []
    for minimum_count in (3, 6, 12, 24):
        for minimum_months in (1, 3, 6):
            count = connection.execute('''SELECT COUNT(*) FROM cohort_history
                WHERE historical_interactions>=? AND historical_active_months>=?''',
                (minimum_count, minimum_months)).fetchone()[0]
            candidates.append({'min_history_interactions': minimum_count,
                               'min_active_months': minimum_months, 'eligible_products': count})
    write_csv(OUTPUT_DIR/'cohort_rule_candidates.csv', candidates)
    return {'interactions_2019': distribution(connection, 'SELECT historical_interactions AS value FROM cohort_history'),
            'active_months_2019': distribution(connection, 'SELECT historical_active_months AS value FROM cohort_history'),
            'candidate_rules': candidates}


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)
    with sqlite3.connect(STAGE15_DATABASE) as connection:
        connection.execute('PRAGMA cache_size=-32768')
        connection.execute('PRAGMA temp_store=FILE')
        profile = load_full_core(connection)
        rows = []
        for year in range(2018, 2024):
            count, products, users = connection.execute('''SELECT COUNT(*), COUNT(DISTINCT parent),
                COUNT(DISTINCT user) FROM interactions WHERE year=?''', (year,)).fetchone()
            rows.append({'dataset': 'full_official_5core', 'year': year,
                         'interactions': count, 'active_parent_asin': products, 'active_users': users,
                         'coverage_note': 'partial_year' if year==2023 else 'calendar_year'})
        write_csv(OUTPUT_DIR/'recent_period_summary.csv', rows)
        profile['recent_years'] = rows
        profile['history_diagnostics'] = analyze_history(connection)
    (OUTPUT_DIR/'recent_period_profile.json').write_text(json.dumps(profile,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(profile,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
