"""只用锚点前的历史筛选商品，固定哈希排序抽样，与 metadata 顺序无关。"""
import csv
import hashlib
import json
import sqlite3
from datetime import datetime, timezone

from src.config import (
    STAGE15_DATABASE, OUTPUT_DIR, FORMAL_COHORT_FILE, META_FILE, RANDOM_SEED,
    HISTORY_START, COHORT_ANCHOR, MIN_HISTORY_INTERACTIONS,
    MIN_HISTORY_ACTIVE_MONTHS, MAX_COHORT_PRODUCTS,
)
from src.analyze_recent_period import write_csv


def selection_key(parent):
    return hashlib.sha256(f'{RANDOM_SEED}|{parent}'.encode()).hexdigest()


def select_cohort(connection):
    # 每次从原始时间表重新计算；绝不依赖含未来统计的 cohort_summary。
    history = connection.execute('''SELECT parent, COUNT(*),COUNT(DISTINCT month),
        MIN(month),MAX(month),MAX(timestamp) FROM interactions
        WHERE month>=? AND month<? GROUP BY parent
        HAVING COUNT(*)>=? AND COUNT(DISTINCT month)>=?''',
        (HISTORY_START, COHORT_ANCHOR, MIN_HISTORY_INTERACTIONS,
         MIN_HISTORY_ACTIVE_MONTHS)).fetchall()
    ranked = sorted(history, key=lambda row: (selection_key(row[0]), row[0]))
    assert ranked == sorted(reversed(history), key=lambda row: (selection_key(row[0]), row[0]))
    selected = ranked[:MAX_COHORT_PRODUCTS]
    if not selected:
        raise RuntimeError('历史筛选没有符合条件的商品。')
    anchor_ms = datetime.fromisoformat(COHORT_ANCHOR).replace(tzinfo=timezone.utc).timestamp()*1000
    assert all(row[5] < anchor_ms for row in selected)
    rows = [{'parent_asin': parent, 'historical_interactions': count,
             'historical_active_months': active_months, 'first_history_month': first,
             'last_history_month': last, 'max_history_timestamp': max_time,
             'selection_hash': selection_key(parent), 'cohort_anchor_utc': COHORT_ANCHOR}
            for parent, count, active_months, first, last, max_time in selected]
    connection.execute('DROP TABLE IF EXISTS formal_cohort')
    connection.execute('CREATE TABLE formal_cohort(parent TEXT PRIMARY KEY)')
    connection.executemany('INSERT INTO formal_cohort VALUES (?)', [(row['parent_asin'],) for row in rows])
    connection.commit()
    write_csv(FORMAL_COHORT_FILE, rows)
    # metadata 仅检查现有覆盖，不能反过来决定 cohort 成员。
    with META_FILE.open() as file:
        metadata_ids = {json.loads(line).get('parent_asin') for line in file}
    result = {'history_start': HISTORY_START, 'anchor': COHORT_ANCHOR,
              'min_history_interactions': MIN_HISTORY_INTERACTIONS,
              'min_history_active_months': MIN_HISTORY_ACTIVE_MONTHS,
              'eligible_products': len(history), 'selected_products': len(rows),
              'max_products': MAX_COHORT_PRODUCTS, 'seed': RANDOM_SEED,
              'sampling': 'ascending SHA256("42|parent_asin"), parent_asin tie-break',
              'max_selected_history_timestamp': max(row[5] for row in selected),
              'metadata_snapshot_matches': sum(row['parent_asin'] in metadata_ids for row in rows),
              'formal_cohort_sha256': hashlib.sha256(FORMAL_COHORT_FILE.read_bytes()).hexdigest()}
    return result


def main():
    with sqlite3.connect(STAGE15_DATABASE) as connection:
        result = select_cohort(connection)
        # 独立再计算一次核对结果；上方反向遍历检查排序稳定性。
        second = select_cohort(connection)
        assert result == second
    (OUTPUT_DIR/'cohort_selection.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
