"""Stage 3 最小泄漏审计：网格全量检查 + 原始事件按 T 前重算抽查。"""
import math
import random
from datetime import timezone

import pandas as pd

from src.config import ANALYSIS_END, ANALYSIS_START, HISTORY_START, MAX_COHORT_PRODUCTS, RANDOM_SEED, TEST_START


def equal_number(actual, expected):
    if pd.isna(actual) and pd.isna(expected):
        return True
    return math.isclose(float(actual), float(expected), rel_tol=1e-9, abs_tol=1e-9)


def source_month_counts(connection, parent, cutoff):
    rows = connection.execute('''SELECT month,COUNT(*) FROM interactions
                                 WHERE parent=? AND month>=? AND month<? GROUP BY month''',
                              (parent,HISTORY_START,cutoff)).fetchall()
    return dict(rows)


def check_sample(row, connection):
    parent, cutoff = row['parent_asin'], row['month']
    months = pd.date_range(pd.Timestamp(HISTORY_START, tz='UTC'),
                           pd.Timestamp(cutoff, tz='UTC') - pd.DateOffset(months=1),
                           freq='MS',tz='UTC').strftime('%Y-%m-%d')
    monthly = source_month_counts(connection, parent, cutoff)
    history = [monthly.get(m,0) for m in months]
    assert len(history)>=12
    for lag in (1,2,3):
        assert equal_number(row[f'lag_{lag}'], history[-lag]), (parent,cutoff,lag)
    assert equal_number(row['rolling_mean_3'], sum(history[-3:])/3)
    assert equal_number(row['rolling_mean_6'], sum(history[-6:])/6)
    last3 = history[-3:]
    sample_std = (sum((x-sum(last3)/3)**2 for x in last3)/2)**.5
    assert equal_number(row['rolling_std_3'],sample_std)
    assert equal_number(row['historical_interaction_mean'],sum(history)/len(history))
    assert equal_number(row['historical_interaction_max'],max(history))
    assert row['active_months_history']==sum(value>0 for value in history)
    cutoff_ms = pd.Timestamp(cutoff, tz='UTC').timestamp()*1000
    start_ms = pd.Timestamp(HISTORY_START, tz='UTC').timestamp()*1000
    rating_count, rating_mean = connection.execute('''SELECT COUNT(rating),AVG(rating) FROM interactions
        WHERE parent=? AND timestamp>=? AND timestamp<?''',(parent,start_ms,cutoff_ms)).fetchone()
    assert row['historical_rating_count']==rating_count
    assert equal_number(row['historical_rating_mean'],rating_mean)
    target_count = connection.execute('''SELECT COUNT(*) FROM interactions
        WHERE parent=? AND month=?''',(parent,cutoff)).fetchone()[0]
    assert row['future_interaction_count']==target_count==row['interaction_count']


def validate_table(table, products, connection, features):
    expected_columns = ['parent_asin','month','interaction_count',*features,
                        'future_interaction_count','split']
    assert table.columns.tolist()==expected_columns
    assert len(products)==MAX_COHORT_PRODUCTS==5000 and len(table)==5000*36
    assert table.parent_asin.nunique()==5000 and set(table.parent_asin)==set(products)
    assert table.month.min()==ANALYSIS_START and table.month.max()=='2022-12-01'
    assert not table.duplicated(['parent_asin','month']).any()
    assert (table.groupby('parent_asin').month.nunique()==36).all()
    assert set(table.month)==set(pd.date_range(ANALYSIS_START,'2022-12-01',freq='MS',tz='UTC').strftime('%Y-%m-%d'))
    assert (table.loc[table.month<TEST_START,'split']=='train').all()
    assert (table.loc[table.month>=TEST_START,'split']=='test').all()
    assert (table.split=='train').sum()==120000 and (table.split=='test').sum()==60000
    assert (table.future_interaction_count==table.interaction_count).all()
    assert table.future_interaction_count.ge(0).all()
    assert 'interaction_count' not in features and 'future_interaction_count' not in features
    forbidden = {'price','store','brand','categories','features','description',
                 'average_rating','rating_number','helpful_vote','verified_purchase',
                 'cohort_summary','last_interaction','future_active_months'}
    assert not forbidden.intersection(features)
    assert all(name.startswith(('lag_','rolling_','historical_','active_months_')) for name in features)
    for split,start,end in [('train',ANALYSIS_START,TEST_START),('test',TEST_START,ANALYSIS_END)]:
        expected=connection.execute('''SELECT COUNT(*) FROM interactions i
            JOIN formal_cohort c ON i.parent=c.parent WHERE i.month>=? AND i.month<?''',(start,end)).fetchone()[0]
        assert int(table.loc[table.split==split,'future_interaction_count'].sum())==expected
    # 固定 seed，train/test 各 6 条；用源事件重新计算，而非复用构造特征的数组。
    rng=random.Random(RANDOM_SEED)
    positions=[]
    for split in ('train','test'):
        choices=table.index[table.split==split].tolist()
        positions.extend(rng.sample(choices,6))
    for position in positions:
        check_sample(table.iloc[position],connection)
    return {'sample_count':len(positions),
            'train_sample_count':6,'test_sample_count':6,
            'summary':'完整网格/分区/当前月 target/禁用 metadata 全量通过；12 条独立源事件重算 lag、rolling、expanding、rating timestamp<T、target 均通过；2022 样本未用同月 target 计算特征',
            'feature_missing_counts':{name:int(table[name].isna().sum()) for name in features}}
