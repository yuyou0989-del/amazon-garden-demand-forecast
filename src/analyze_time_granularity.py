"""比较固定商品范围的周/月覆盖与稀疏度，不构造训练特征、不拟合模型。"""
import json
import math
import sqlite3
from collections import Counter
from datetime import date, timedelta

from src.config import (
    STAGE15_DATABASE, OUTPUT_DIR, STAGE15_SUMMARY, ANALYSIS_START,
    ANALYSIS_END, TEST_START,
)
from src.analyze_recent_period import write_csv


def next_month(value):
    return date(value.year+int(value.month==12), value.month%12+1, 1)


def full_periods(kind, start, end):
    if kind == 'month':
        current = start.replace(day=1)
        if current < start:
            current = next_month(current)
        advance = next_month
    else:
        current = start + timedelta(days=(-start.weekday())%7)
        advance = lambda value: value+timedelta(days=7)
    periods = []
    while advance(current) <= end:
        periods.append(current.isoformat())
        current = advance(current)
    return periods


def weighted_stats(histogram):
    """显式计入零值，用频数计算精确线性插值分位数。"""
    total = sum(histogram.values())
    if not total:
        raise ValueError('没有有效统计网格。')
    items = sorted(histogram.items())
    def at(position):
        seen = 0
        for value, frequency in items:
            seen += frequency
            if position < seen:
                return value
        raise AssertionError('分位数索引越界')
    result = {'count': total, 'min': items[0][0], 'max': items[-1][0],
              'mean': sum(v*f for v,f in items)/total}
    for q in (0.25,0.5,0.75,0.95,0.99):
        position = (total-1)*q
        lower, upper = math.floor(position), math.ceil(position)
        result[f'p{int(q*100)}'] = at(lower)+(at(upper)-at(lower))*(position-lower)
    return result


def period_metrics(connection, kind, start, end, product_count, label):
    periods = full_periods(kind, start, end)
    if not periods:
        raise ValueError('时间范围没有完整周期。')
    histogram, active = Counter(), Counter()
    # 月和周都是内部白名单字段，SQL 参数传入日期值。
    for parent, period, count in connection.execute(f'''SELECT i.parent,i.{kind},COUNT(*)
        FROM interactions i JOIN formal_cohort c ON c.parent=i.parent
        WHERE i.{kind}>=? AND i.{kind}<=? GROUP BY i.parent,i.{kind}''',
        (periods[0],periods[-1])):
        histogram[count] += 1
        active[parent] += 1
    grid = product_count*len(periods)
    nonzero = sum(histogram.values())
    histogram[0] = grid-nonzero
    assert histogram[0] >= 0
    active_distribution = Counter(active.values())
    active_distribution[0] += product_count-len(active)
    result = {'split': label, 'kind': kind, 'start': start.isoformat(),
              'end_exclusive': end.isoformat(), 'first_period_start': periods[0],
              'last_period_start': periods[-1], 'periods_per_product': len(periods),
              'products': product_count, 'grid_observations': grid,
              'nonzero_observations': nonzero, 'zero_observations': histogram[0],
              'sparsity': histogram[0]/grid, 'interaction_count_distribution': weighted_stats(histogram),
              'nonzero_count_distribution': weighted_stats(Counter({k:v for k,v in histogram.items() if k>0})),
              'nonzero_periods_per_product_distribution': weighted_stats(active_distribution),
              'all_zero_products': product_count-len(active)}
    return result, histogram, active


def compare_windows(connection):
    rows = []
    ranges = [
        ('A','train','2020-01-01','2023-01-01'),('A','test','2023-01-01','2023-09-01'),
        ('B','train','2021-01-01','2023-01-01'),('B','test','2023-01-01','2023-09-01'),
        ('C','train','2020-01-01','2022-01-01'),('C','test','2022-01-01','2023-01-01'),
    ]
    for option, split, start, end in ranges:
        for scope, join in [('full_5core',''),('formal_cohort','JOIN formal_cohort c ON c.parent=i.parent')]:
            count, products, users = connection.execute(f'''SELECT COUNT(*),COUNT(DISTINCT i.parent),
                COUNT(DISTINCT i.user) FROM interactions i {join} WHERE month>=? AND month<?''',
                (start,end)).fetchone()
            rows.append({'option':option,'split':split,'dataset':scope,'start':start,
                         'end_exclusive':end,'interactions':count,'active_parent_asin':products,'active_users':users})
    write_csv(OUTPUT_DIR/'time_window_comparison.csv',rows)
    return rows


def main():
    start,end,test = date.fromisoformat(ANALYSIS_START),date.fromisoformat(ANALYSIS_END),date.fromisoformat(TEST_START)
    with sqlite3.connect(STAGE15_DATABASE) as connection:
        product_count = connection.execute('SELECT COUNT(*) FROM formal_cohort').fetchone()[0]
        metrics, distributions, active_periods = [], {}, {}
        for kind in ('week','month'):
            output_rows = []
            for label,left,right in [('train',start,test),('test',test,end),('all',start,end)]:
                result,histogram,active = period_metrics(connection,kind,left,right,product_count,label)
                metrics.append(result)
                distributions[(kind,label)] = histogram
                active_periods[(kind,label)] = active
                output_rows.extend({'split':label,'interaction_count':count,'observations':frequency}
                                   for count,frequency in sorted(histogram.items()))
            write_csv(OUTPUT_DIR/f'{"weekly" if kind=="week" else "monthly"}_distribution.csv',output_rows)
        cohort_rows = []
        for parent, in connection.execute('SELECT parent FROM formal_cohort ORDER BY parent'):
            row = {'parent_asin':parent}
            for kind in ('week','month'):
                for label in ('train','test','all'):
                    row[f'{kind}_{label}_nonzero_periods'] = active_periods[(kind,label)][parent]
            cohort_rows.append(row)
        write_csv(OUTPUT_DIR/'cohort_summary.csv',cohort_rows)
        recent_months = [dict(zip(['month','interactions','active_parent_asin','active_users'],row)) for row in
            connection.execute('''SELECT month,COUNT(*),COUNT(DISTINCT parent),COUNT(DISTINCT user)
                FROM interactions WHERE month>='2020-01-01' GROUP BY month ORDER BY month''')]
        write_csv(OUTPUT_DIR/'recent_monthly_coverage.csv',recent_months)
        windows = compare_windows(connection)
    train = {row['kind']:row for row in metrics if row['split']=='train'}
    # 只用训练区间比较粒度，不按测试表现调参。
    if train['month']['sparsity'] >= train['week']['sparsity']:
        raise RuntimeError('月粒度未降低训练稀疏度，需重新审查口径。')
    result = {'chosen_granularity':'month','analysis_start':ANALYSIS_START,
              'analysis_end_exclusive':ANALYSIS_END,'test_start':TEST_START,
              'target':'future_interaction_count','selection_uses_test_outcomes':False,
              'granularity_metrics':metrics,'window_comparison':windows,
              'recent_monthly_coverage':recent_months}
    STAGE15_SUMMARY.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'chosen_granularity':result['chosen_granularity'],
                      'metrics':metrics},ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
