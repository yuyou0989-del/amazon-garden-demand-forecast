"""Stage 3：固定 2019 cohort，构造 UTC 商品×月历史特征；不训练模型。"""
import csv
import json
import sqlite3
from contextlib import closing

import pandas as pd

from src.config import (ANALYSIS_END, ANALYSIS_START, COHORT_ANCHOR,
                        FORMAL_COHORT_FILE, HISTORY_START, MAX_COHORT_PRODUCTS,
                        STAGE15_DATABASE, PROJECT_ROOT, REPORT_DIR, RANDOM_SEED)
from src.validate_product_month import validate_table

OUTPUT_FILE = PROJECT_ROOT / 'data' / 'processed' / 'product_month_features.csv'
FEATURES = [
    'lag_1', 'lag_2', 'lag_3', 'rolling_mean_3', 'rolling_mean_6',
    'rolling_std_3', 'historical_interaction_mean',
    'historical_interaction_max', 'active_months_history',
    'historical_rating_mean', 'historical_rating_count',
]
TARGET = 'future_interaction_count'


def read_fixed_cohort(connection):
    with FORMAL_COHORT_FILE.open(newline='', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        if not reader.fieldnames or 'parent_asin' not in reader.fieldnames:
            raise ValueError('Stage 1.5 正式 cohort 文件缺少 parent_asin')
        rows = list(reader)
    products = [row['parent_asin'] for row in rows]
    if len(products) != MAX_COHORT_PRODUCTS or len(set(products)) != len(products):
        raise ValueError('正式 cohort 数量/唯一性不符合 Stage 1.5 固定口径')
    if any(row['cohort_anchor_utc'] != COHORT_ANCHOR for row in rows):
        raise ValueError('cohort 锚点与配置不一致')
    anchor_ms = pd.Timestamp(COHORT_ANCHOR, tz='UTC').timestamp() * 1000
    if any(float(row['max_history_timestamp']) >= anchor_ms for row in rows):
        raise ValueError('cohort 文件包含锚点后筛选信息')
    db_products = {row[0] for row in connection.execute('SELECT parent FROM formal_cohort')}
    if set(products) != db_products:
        raise ValueError('cohort CSV 与 Stage 1.5 SQLite 成员不一致')
    return products


def monthly_source(connection):
    # 源表来自已完成的完整 5-core 扫描；不连接 2023 metadata。
    sql = '''SELECT i.parent AS parent_asin, i.month,
                    COUNT(*) AS interaction_count,
                    COUNT(i.rating) AS rating_count,
                    COALESCE(SUM(i.rating),0) AS rating_sum
             FROM interactions AS i JOIN formal_cohort AS c ON i.parent=c.parent
             WHERE i.month>=? AND i.month<?
             GROUP BY i.parent,i.month'''
    monthly = pd.read_sql_query(sql, connection, params=(HISTORY_START, ANALYSIS_END))
    if monthly.empty or monthly.duplicated(['parent_asin','month']).any():
        raise ValueError('5-core 月度聚合为空或主键重复')
    return monthly


def complete_grid(products, monthly):
    months = pd.date_range(HISTORY_START, '2022-12-01', freq='MS', tz='UTC').strftime('%Y-%m-%d')
    index = pd.MultiIndex.from_product([products, months], names=['parent_asin','month'])
    grid = pd.DataFrame(index=index).reset_index()
    grid = grid.merge(monthly, on=['parent_asin','month'], how='left', validate='one_to_one')
    # 无交互月为真实源文件中 0 条；与历史不足造成的特征 NaN 分开。
    for field in ('interaction_count','rating_count'):
        grid[field] = grid[field].fillna(0).astype('int64')
    grid['rating_sum'] = grid['rating_sum'].fillna(0.0).astype('float64')
    if grid['interaction_count'].sum() != monthly['interaction_count'].sum():
        raise AssertionError('完整网格与源数据的 interaction 总数不一致')
    return grid


def add_history_features(grid):
    grid = grid.sort_values(['parent_asin','month']).reset_index(drop=True)
    group = grid.groupby('parent_asin', sort=False)
    counts = group['interaction_count']
    previous = counts.shift(1)
    for n in (1,2,3):
        grid[f'lag_{n}'] = counts.shift(n)
    for n in (3,6):
        grid[f'rolling_mean_{n}'] = previous.groupby(grid['parent_asin']).transform(
            lambda history: history.rolling(n, min_periods=n).mean())
    grid['rolling_std_3'] = previous.groupby(grid['parent_asin']).transform(
        lambda history: history.rolling(3, min_periods=3).std(ddof=1))
    grid['historical_interaction_mean'] = previous.groupby(grid['parent_asin']).transform(
        lambda history: history.expanding(min_periods=1).mean())
    grid['historical_interaction_max'] = previous.groupby(grid['parent_asin']).cummax()
    grid['active_months_history'] = (grid['interaction_count'].gt(0).groupby(grid['parent_asin']).cumsum()
                                     - grid['interaction_count'].gt(0).astype('int64'))
    # T 前 rating 用逐月 sum/count 累计再 shift；目标月 rating 完全不参与。
    cumulative_rating_count = group['rating_count'].cumsum()
    cumulative_rating_sum = group['rating_sum'].cumsum()
    grid['historical_rating_count'] = cumulative_rating_count.groupby(grid['parent_asin']).shift(1)
    rating_sum_before = cumulative_rating_sum.groupby(grid['parent_asin']).shift(1)
    grid['historical_rating_mean'] = rating_sum_before / grid['historical_rating_count'].replace(0, float('nan'))
    return grid


def formal_table(grid):
    # 2019 只作预热；target 与本月真实源计数同一行，绝不 shift 标签。
    table = grid.loc[(grid['month'] >= ANALYSIS_START) & (grid['month'] < ANALYSIS_END)].copy()
    table[TARGET] = table['interaction_count']
    table['split'] = table['month'].lt('2022-01-01').map({True:'train', False:'test'})
    table = table[['parent_asin','month','interaction_count',*FEATURES,TARGET,'split']]
    if table['historical_rating_count'].notna().all():
        table['historical_rating_count'] = table['historical_rating_count'].astype('int64')
    return table.reset_index(drop=True)


def write_report(table, checks, source_rows):
    stats = table[TARGET].describe(percentiles=[.5,.9,.95])
    rates = table.isna().mean()
    samples = table.loc[table['parent_asin'] == table['parent_asin'].iloc[0],
                        ['month','interaction_count','lag_1','lag_2','lag_3',
                         'rolling_mean_3','historical_rating_mean',TARGET,'split']].head(6)
    lines = ['# Stage 3 Feature Table', '',
             '- 来源：官方 Patio_Lawn_and_Garden 完整 5-core 扫描所得 Stage 1.5 `interactions` 表；固定 2019 cohort CSV 及数据库成员相互核对。没有读取 metadata。',
             '- 粒度：parent_asin × UTC 自然月；2019-01 至 2019-12 只用于历史预热，完整零交互月保留。',
             f'- 正式行数：{len(table):,}；商品数：{table.parent_asin.nunique():,}；月份：{table.month.min()} 至 {table.month.max()}。',
             f"- Train：{(table.split=='train').sum():,} 行（2020-01～2021-12）；Test：{(table.split=='test').sum():,} 行（2022-01～2022-12）。",
             f'- 源区间 2019～2022 有 {source_rows:,} 条 cohort interaction；完整网格的无记录月记 interaction_count=0。',
             '- target：future_interaction_count = 当前行 month 内真实 interaction_count；在月初预测该月。`interaction_count` 是审计/标签来源列，**不得作为模型特征**。',
             '- 特征列：' + ', '.join(FEATURES) + '。lag/rolling/expanding/rating 均只用 T 前数据；rolling_std_3 使用样本标准差 ddof=1。',
             '- 缺失值：2019 完整预热使正式月份的历史特征缺失数为 0；未对任何历史特征做模型方便型填补。零交互月的 interaction_count=0 是源文件计数口径。',
             f"- target：均值 {stats['mean']:.4f}；中位数 {stats['50%']:.0f}；p90 {stats['90%']:.0f}；p95 {stats['95%']:.0f}；最大 {stats['max']:.0f}。",
             f"- zero-target rate：{(table[TARGET]==0).mean():.4%}；train {(table.loc[table.split=='train',TARGET]==0).mean():.4%}；test {(table.loc[table.split=='test',TARGET]==0).mean():.4%}。",
             '', '| 字段 | 缺失率 |', '| --- | ---: |']
    lines += [f'| {name} | {rate:.4%} |' for name,rate in rates.items()]
    lines += ['', f"- 泄漏验证：{checks['summary']}。固定 seed={RANDOM_SEED}，{checks['sample_count']} 条商品月由源事件/时间戳独立抽查；详见终端验证输出。",
              '- 边界：源数据已按全时期 5-core 资格筛选；事件 timestamp 近似预测时可见时间，未证明线上真实入库时点。零 interaction 不等于零销量、零需求或在售。',
              '', '## 连续六个月真实样例', '',
              f"parent_asin：`{table.parent_asin.iloc[0]}`；2019 历史已在上一月特征中。",
              '', '```text\n'+samples.to_string(index=False)+'\n```', '']
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR/'stage3_feature_table.md').write_text('\n'.join(lines), encoding='utf-8')


def main():
    with closing(sqlite3.connect(f'file:{STAGE15_DATABASE}?mode=ro', uri=True)) as connection:
        products = read_fixed_cohort(connection)
        monthly = monthly_source(connection)
        grid = add_history_features(complete_grid(products, monthly))
        table = formal_table(grid)
        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        temporary = OUTPUT_FILE.with_suffix('.csv.tmp')
        table.to_csv(temporary, index=False, float_format='%.12g')
        saved = pd.read_csv(temporary, dtype={'parent_asin':'string','month':'string','split':'string'})
        checks = validate_table(saved, products, connection, FEATURES)
        temporary.replace(OUTPUT_FILE)
        write_report(saved, checks, int(monthly['interaction_count'].sum()))
    print(json.dumps({'rows':len(saved),'products':saved.parent_asin.nunique(),
                      'months':[saved.month.min(), saved.month.max()],
                      'train_rows':int((saved.split=='train').sum()),
                      'test_rows':int((saved.split=='test').sum()),
                      'zero_target_rate':float((saved[TARGET]==0).mean()),
                      'feature_missing_rates':{name:float(saved[name].isna().mean()) for name in FEATURES},
                      'leakage_validation':checks,'output_file':str(OUTPUT_FILE)},
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
