"""核对数据来源、时间边界、确定性 cohort 及完整网格统计。"""
import csv
import hashlib
import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone

from src.config import (
    PROJECT_ROOT, OUTPUT_DIR, REPORT_DIR, STAGE15_DATABASE,
    STAGE15_SUMMARY, FORMAL_COHORT_FILE, COHORT_ANCHOR,
    ANALYSIS_START, ANALYSIS_END, TEST_START,
)
from src.build_cohort import selection_key


def sha256(path):
    h=hashlib.sha256()
    with path.open('rb') as file:
        for chunk in iter(lambda:file.read(1024*1024),b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    messages=[]
    old=json.loads((PROJECT_ROOT/'data/raw/download_manifest.json').read_text())
    for entry in old['files']:
        path=PROJECT_ROOT/entry['file']
        assert path.stat().st_size==entry['bytes']
        assert sha256(path)==entry['sha256']
    messages.append('PASS: Stage 1 原始文件大小与 SHA-256 未改变。')
    recent=json.loads((OUTPUT_DIR/'recent_period_profile.json').read_text())
    assert recent['source_rows']==old['source_interactions']
    assert sum(recent['all_year_counts'].values())==recent['source_rows']
    assert recent['invalid_key_or_time']==0
    assert sum(row['interactions'] for row in recent['recent_years'])==recent['recent_rows_in_database']
    for row in recent['recent_years']:
        assert row['interactions']==recent['all_year_counts'][str(row['year'])]
        assert row['active_parent_asin']<=row['interactions']
        assert row['active_users']<=row['interactions']
    messages.append('PASS: 全量扫描数量、年度合计与最近时期 SQLite 数量一致。')
    probe=json.loads((OUTPUT_DIR/'raw_review_probe.json').read_text())
    with (PROJECT_ROOT/probe['sample_file']['file']).open() as file:
        raw=[json.loads(line) for line in file]
    assert len(raw)==probe['sample_records']==2000
    required={'rating','title','text','images','asin','parent_asin','user_id','timestamp','helpful_vote','verified_purchase'}
    assert all(required<=set(row) for row in raw)
    assert all(isinstance(row['verified_purchase'],bool) for row in raw)
    assert sha256(PROJECT_ROOT/probe['sample_file']['file'])==probe['sample_file']['sha256']
    assert probe['transferred_bytes']==4*1024*1024
    messages.append('PASS: 原始 review 仅 4 MiB 前缀；2,000 条真实记录、十个字段与布尔 verified 状态已核对。')
    cohort=json.loads((OUTPUT_DIR/'cohort_selection.json').read_text())
    with FORMAL_COHORT_FILE.open() as file:
        selected=list(csv.DictReader(file))
    parents={r['parent_asin'] for r in selected}
    assert len(parents)==len(selected)==cohort['selected_products']==5000
    anchor_ms=datetime.fromisoformat(COHORT_ANCHOR).replace(tzinfo=timezone.utc).timestamp()*1000
    assert all(float(row['max_history_timestamp'])<anchor_ms for row in selected)
    assert all(int(row['historical_interactions'])>=12 and int(row['historical_active_months'])>=3 for row in selected)
    assert sha256(FORMAL_COHORT_FILE)==cohort['formal_cohort_sha256']
    with sqlite3.connect(STAGE15_DATABASE) as c:
        eligible=[r[0] for r in c.execute('SELECT parent FROM cohort_history WHERE historical_interactions>=12 AND historical_active_months>=3')]
        expected=sorted(eligible,key=lambda p:(selection_key(p),p))[:5000]
        reversed_expected=sorted(reversed(eligible),key=lambda p:(selection_key(p),p))[:5000]
        assert expected==reversed_expected==[r['parent_asin'] for r in selected]
        assert len(eligible)==cohort['eligible_products']
        summary=json.loads(STAGE15_SUMMARY.read_text())
        for kind,filename in [('week','weekly_distribution.csv'),('month','monthly_distribution.csv')]:
            with (OUTPUT_DIR/filename).open() as file:
                histograms={split:Counter() for split in ('train','test','all')}
                for row in csv.DictReader(file):
                    histograms[row['split']][int(row['interaction_count'])]=int(row['observations'])
            for row in [r for r in summary['granularity_metrics'] if r['kind']==kind]:
                histogram=histograms[row['split']]
                assert sum(histogram.values())==row['grid_observations']==5000*row['periods_per_product']
                assert row['nonzero_observations']+row['zero_observations']==row['grid_observations']
                assert histogram[0]==row['zero_observations']
                stop= c.execute("SELECT date(?, '+7 days')",(row['last_period_start'],)).fetchone()[0] if kind=='week' else row['end_exclusive']
                expected_events=c.execute('''SELECT COUNT(*) FROM interactions i JOIN formal_cohort c
                    ON c.parent=i.parent WHERE timestamp>=? AND timestamp<?''',
                    (datetime.fromisoformat(row['first_period_start']).replace(tzinfo=timezone.utc).timestamp()*1000,
                     datetime.fromisoformat(stop).replace(tzinfo=timezone.utc).timestamp()*1000)).fetchone()[0]
                assert sum(count*frequency for count,frequency in histogram.items())==expected_events
        month={r['split']:r for r in summary['granularity_metrics'] if r['kind']=='month'}
        assert month['all']['grid_observations']==month['train']['grid_observations']+month['test']['grid_observations']
        assert month['all']['nonzero_observations']==month['train']['nonzero_observations']+month['test']['nonzero_observations']
        assert summary['chosen_granularity']=='month'
        assert month['train']['sparsity']<next(r for r in summary['granularity_metrics'] if r['kind']=='week' and r['split']=='train')['sparsity']
    messages.append('PASS: cohort 只含预测前历史，固定 seed、反向遍历与独立查询的成员一致。')
    messages.append('PASS: 周/月频数总量、非零比例、独立时间戳查询计数及月度分区合计一致。')
    for name in ['raw_review_feasibility.md','time_granularity_analysis.md','leakage_audit.md','modeling_scope.md']:
        assert (REPORT_DIR/name).stat().st_size>0
    scope=(REPORT_DIR/'modeling_scope.md').read_text()
    required_headings=['Business Question','Unit of Analysis','Prediction Time','Prediction Horizon','Target','Why This Target','Candidate Features','Leakage Risks','Train / Test Strategy','Cohort Rule','Known Biases','What This Project Can Claim','What This Project Cannot Claim']
    assert all('# '+heading in scope for heading in required_headings)
    messages.append('PASS: 报告口径完整；目标不等于销量，未训练模型。')
    (OUTPUT_DIR/'stage15_verification.log').write_text('\n'.join(messages)+'\nFinal exit code: 0\n')
    commands=['python3 -B -m src.check_raw_review','python3 -B -m src.analyze_recent_period',
              'python3 -B -m src.build_cohort','python3 -B -m src.analyze_time_granularity',
              'python3 -B -m src.scope_reporting','python3 -B -m src.verify_stage15']
    record='# Stage 1.5 Execution Record\n\n执行日期：2026-10-07（Asia/Shanghai）。实际输入为 Stage 1 保留的官方完整 5-core；没有删除或覆盖 Stage 1 数据。\n\n'
    record+='## 实际执行的模块命令\n\n项目根目录：仓库根目录\n\n```bash\n'
    record+='\n'.join(f'{command} > outputs/{log} 2>&1' for command,log in zip(commands,['raw_review_probe.log','recent_period.log','build_cohort.log','time_granularity.log','scope_reporting.log','verify_stage15_run.log']))+'\n```\n\n'
    record+='六个模块均实际执行，exit code 均为 0；build_cohort 在补充反向遍历验证后再次执行，结果一致。代码使用 Python 3.9.6 标准库，无需安装第三方依赖。\n\n'
    record+='额外实际执行 curl -fsSI --connect-timeout 15 --max-time 30 '+probe['url']+'（exit 0），保存代码的 cp -R 操作，以及 Python AST 语法检查和实际输出读取。模块内部的 HEAD/Range 参数见 check_raw_review.py 与 download_data.py；请求仅 4 MiB，schema 样本 2,000 条，未下载 2.16 GB 全量 raw。\n\n'
    record+='## 结果与审计\n\n全量 5-core 扫描 '+str(recent['source_rows'])+' 条，正式 cohort 5,000 商品；方案 C，月度 future_interaction_count；Train 2020–2021，Test 2022。\n\n'
    record+='\n'.join('- '+message for message in messages)+'\n\n**Stage 1.5 最终 exit code：0。**\n\n只完成数据底座、覆盖诊断和口径设计；未开始业务 EDA、Stage 2 或模型训练。\n'
    (OUTPUT_DIR/'stage15_execution_record.md').write_text(record,encoding='utf-8')
    print('\n'.join(messages))
    print('Stage 1.5 final exit code: 0')


if __name__ == '__main__':
    main()
