"""根据 Stage 1.5 真实统计生成口径报告及更新 README。"""
import json
from pathlib import Path

from src.config import PROJECT_ROOT, OUTPUT_DIR, REPORT_DIR
from src.reporting import table

OFFICIAL = 'https://amazon-reviews-2023.github.io/main.html'
MIRROR = 'https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023/blob/main/raw/review_categories/Patio_Lawn_and_Garden.jsonl'


def raw_feasibility(probe):
    fields = [[field, ', '.join(types), probe['field_present_counts'][field]]
              for field,types in probe['field_types'].items()]
    years = [[row['year'],row['interactions'],row['active_parent_asin'],row['active_users']]
             for row in probe['recent_years_sample_only']]
    return f'''# Raw Review Feasibility

## 官方明确提供的信息

- 数据集：McAuley Lab Amazon Reviews 2023；类目 Patio_Lawn_and_Garden。
- 官方文件：`Patio_Lawn_and_Garden.jsonl.gz`；[下载地址]({probe['url']})。
- [官方类目表]({OFFICIAL})给出约 16.5M reviews，这是四舍五入数量；本地没有读取全量原始评论，不把它写成精确行数。
- [官方 Hugging Face 未压缩 JSONL 镜像]({MIRROR})显示约 7.75 GB。这是网页展示的舍入大小，不是本地完整解压验证的字节数；没有确认 gzip 解压结果与镜像逐字节一致。
- 官方字段表列出 rating、title、text、images、asin、parent_asin、user_id、timestamp、helpful_vote、verified_purchase。官网 Quick Start 个别示例使用 sort_timestamp/helpful_votes，与字段表不同，因此代码以下面的本地真实字段为准。

## 本地实际验证的信息

检查时间 UTC：{probe['checked_at_utc']}。

- HEAD：压缩文件 **{probe['source_bytes']:,} 字节**（约 {probe['source_bytes']/1e9:.3f} GB），ETag `{probe['etag']}`。
- 决策阈值：1,500,000,000 字节；实际文件也超过 1.5 GiB，未完整下载。
- 实际 Range 请求 bytes 0–{probe['transferred_bytes']-1}，服务器返回对应 Content-Range，仅传输 **{probe['transferred_bytes']:,} 字节**。
- gzip 前缀顺序读取并保存 **{probe['sample_records']:,} 条**真实评论；这是 schema 样本，不是完整 gzip、不包含完整商品历史。
- 样本文件：`{probe['sample_file']['file']}`，{probe['sample_file']['bytes']:,} 字节；SHA-256 `{probe['sample_file']['sha256']}`。
- 样本中 verified_purchase=True 有 {probe['verified_true_sample_records']} 条；只证明字段及布尔类型存在，不估计类目购买验证比例。

{table(fields,['真实字段','样本实际类型','字段出现记录数'])}

timestamp 是 Unix 毫秒，实际整数值可正常转换。响应头保存在 data/raw/raw_review_schema_range_headers.txt，机器可读证据保存在 outputs/raw_review_probe.json。

## 原始 review 最近时期统计的边界

以下数字仅来自上述前 {probe['sample_records']} 条 schema 样本，源顺序可能按用户排列，不代表类目年度数量，也不能与全量 5-core 总数直接比较。

{table(years,['年（UTC）','样本 interaction 数','样本活跃 parent_asin','样本活跃 user 数'])}

原始 review **全量**的年度 interaction、商品及用户精确数量：无法计算，未完整扫描。

## 推测及尚未验证的信息

完整 raw 数据可能能补充更丰富的 verified-review 目标，但当前样本不能证明同一商品的完整历史、采集覆盖或所有字段在全量文件中的稳定性。只有完整扫描才可得到某个随机商品范围的完整 raw 历史。gzip 不具备可直接按商品 ID 定位的通用索引，不能任意 Range 一个中间片段就称为完整商品样本。

没有推断源文件规模之外的下载时长，没有把 2023 年数量下降归因为真实市场需求或已证实的采集错误。

## 本次决策

字段补充有价值，但完整 raw 超出预算；只确认 schema，正式分析继续使用完整官方 5-core。候选升级目标优先为 `future_verified_interactions`，定义为未来窗口内 verified_purchase=True 的 raw 评论数；当前 **正式 target 是 future_interaction_count**，因为不能把局部 raw 样本的购买验证状态拼接为全量交互的状态。

原始 review 不包含真实销量。任何 verified review 计数依然是需求热度代理，而不是 sales、units_sold 或 revenue。
'''


def granularity_report(summary,recent,cohort):
    years = [[r['year'],r['interactions'],r['active_parent_asin'],r['active_users'],r['coverage_note']] for r in recent['recent_years']]
    months2023 = [[r['month'],r['interactions'],r['active_parent_asin'],r['active_users']] for r in summary['recent_monthly_coverage'] if r['month'].startswith('2023')]
    comparisons = [[r['option'],r['split'],r['dataset'],r['start'],r['end_exclusive'],r['interactions'],r['active_parent_asin'],r['active_users']] for r in summary['window_comparison']]
    metrics = [[r['kind'],r['split'],r['periods_per_product'],r['grid_observations'],r['nonzero_observations'],f'{r["sparsity"]:.4%}',r['interaction_count_distribution']['p50'],r['interaction_count_distribution']['p95'],r['nonzero_periods_per_product_distribution']['p50'],r['all_zero_products']] for r in summary['granularity_metrics']]
    histories = recent['history_diagnostics']
    train = {r['kind']:r for r in summary['granularity_metrics'] if r['split']=='train'}
    return f'''# Time Granularity Analysis

本报告仅做 Stage 1.5 覆盖与粒度诊断，不做竞品 EDA、趋势归因或模型训练。数字均来自完整 5-core 的实际扫描及固定 cohort。

## 最近时期：完整官方 5-core

全量扫描 {recent['source_rows']:,} 条。完整文件最早时间为 {recent['full_time_min']}，最晚为 {recent['full_time_max']}；Stage 1 的 2006 年最早时间仅属于旧 metadata 前缀商品范围，不是完整文件下界。

{table(years,['年（UTC）','interaction 数','活跃 parent_asin','活跃 user 数','覆盖说明'])}

活跃数指 해당窗口内至少发生一次 interaction；不等于在售商品或购买用户总数。

## 2023 年覆盖诊断

{table(months2023,['月','interaction 数','活跃 parent_asin','活跃 user 数'])}

2023 年从 3 月到 5 月、8 月出现数量突降。9 月截止至文件最大时间，明确不是完整月/年。较早月份虽是完整日历窗口，也不能据此证明采集完全；下降可能涉及采集/样本机制或真实行为变化，原因未验证。不能把这些零值或下降直接当作市场需求信号。

## 时间方案比较

A：2020–2022 Train、2023 Test；B：2021–2022 Train、2023 Test。比较中的 2023 Test 限定到 1–8 月，排除不完整 9 月，但仍受突降问题影响。

C：2020–2021 Train、2022 Test。选择 C，保留两个较近的训练年度和一个完整日历年度测试窗口，不混入原因未确认的 2023 年突降。2019 仅为历史预热和 cohort 筛选；2018 及更早只保留原始数据，不默认投入建模。2020 年可能存在疫情相关行为变化，此处不做归因，需要以后记录分布变化风险。

{table(comparisons,['方案','分区','范围','开始（含）','结束（不含）','interaction 数','活跃父商品','活跃用户'])}

## Cohort 条件依据

2019 年有历史交互的商品 {histories['interactions_2019']['count']:,} 个；历史交互中位数 {histories['interactions_2019']['p50']}、p75={histories['interactions_2019']['p75']}，活跃月份中位数 {histories['active_months_2019']['p50']}。大量商品不足以支持月度历史信息。

最低 12 条历史交互是年均约一条/月的信息要求，而不是每个月都必须有交互；至少 3 个活跃月份避免只靠单月集中活动入选，也尽量少排除季节性商品。规则只查 2019 年，不查后续表现。符合条件 {cohort['eligible_products']:,} 个，确定性哈希抽样 {cohort['selected_products']:,} 个，cap=5,000 是计算规模控制，并非根据模型效果确定。

## 完整周期网格

固定 5,000 商品范围、UTC；formal 2020-01-01 ≤ 时间 < 2023-01-01。月从每月 1 日开始；周从周一开始，仅计起止日期都落在对应区间内的完整周。

每个商品都有预先指定的完整日历周期，不按它的最后一次未来交互缩短网格。非零 observation 是 parent_asin × 周/月中至少一条交互。稀疏度 = 零 interaction 网格数 / 全部商品 × 完整周期网格数。零值只表示该官方 5-core 文件没有该周期交互，不证明零销售、零需求、商品仍在售或采集完整。

{table(metrics,['粒度','分区','每商品完整周期数','全部网格数','非零 observation 数','稀疏度','count p50','count p95','每商品非零周期 p50','全区间零交互商品数'])}

跨训练/测试边界的周不属于任一单独分区的完整周，但可能属于 all 区间，所以周分区不能直接相加；月对齐边界，可以相加。每商品“有效周期”需区分完整日历周期与非零周期，后者不能用于未来活动筛选。

频数分布含零值及精确分位数；原始频数 CSV 见 outputs/weekly_distribution.csv、monthly_distribution.csv；每商品非零周期数见 cohort_summary.csv。这些诊断输出含未来汇总，只用于报告，不可用于正式 cohort 或特征筛选。

## 最终选择：month

仅依据训练期：week 稀疏度 {train['week']['sparsity']:.2%}、count 中位数 {train['week']['interaction_count_distribution']['p50']}；month 稀疏度 {train['month']['sparsity']:.2%}、count 中位数 {train['month']['interaction_count_distribution']['p50']}。月粒度明显减少零值，保留季节性月份及月度运营节奏。训练期每商品月度非零周期中位数为 {train['month']['nonzero_periods_per_product_distribution']['p50']} / {train['month']['periods_per_product']}。

月度聚合会丢失周内波动和短促销信息，不能支撑周级补货判断；当前没有广告、促销和库存历史，项目业务问题也限定为月度评论热度。未根据测试集模型表现选择粒度。测试期覆盖数字仅作为已固定协议的诊断，不用于调参或删商品。
'''.replace('해당','该')


def leakage_report():
    rows = [
        ['historical interaction count','A','仅 timestamp < T 的过去窗口计数，禁止包含目标月。'],
        ['historical average rating','A','从 T 前评分重新计算；不是商品页面快照。无历史时保留缺失及历史条数。'],
        ['historical rating distribution','A','T 前各评分的计数/比例，分母也只能是 T 前交互。'],
        ['historical verified interaction count','B','需完整 raw 历史及 verified 状态历史语义；本次不可计算，禁止拼接样本推断。'],
        ['historical helpful votes','B','需要 T 时点票数快照；评论虽早于 T，采集时累计 helpful_vote 仍可能包含未来投票。'],
        ['metadata price','B','需要 T 时点真实价格历史；当前快照在本回测中按 C 禁用。'],
        ['metadata average_rating','C','采集时累计快照包含 T 之后评分；改用过去交互重算值，不假定两种评分口径相同。'],
        ['metadata rating_number','C','采集时累计评分数包含未来，不是未来窗口交互标签或历史销量。'],
        ['store / brand','B','需要有生效时间的历史版本；不能假定采集值一直不变；当前值按 C 禁用。'],
        ['categories','B','需要 T 前分类版本，文件类目仅限定数据来源；当前快照按 C 禁用。'],
        ['product title / description / features','B','需要 T 前页面版本；当前快照按 C 禁用。'],
        ['review title / text','D','仅已发布且在 T 前可见的评论文本才可能安全；5-core 无字段，本项目不用。'],
        ['current metadata snapshot','C','不能将采集快照整表合并为历史预测特征；仅用于采集时描述，非历史竞品状态。'],
        ['review timestamp 与真实可获得时点','D','只有事件时间，缺发布/入库延迟；A 类采用“事件时间近似可见时间”假设，不能声称生产可用性已验证。'],
        ['未来活跃期数、最后一次交互、全期计数','C','不可用于删商品、界定有效期、筛选热门商品或构造特征。'],
        ['官方全期 5-core 成员资格','D','数据源已按全期活动筛选，无法在本地撤销；本回测不是完全无未来选择偏差。'],
    ]
    return '''# Leakage Audit

站在预测时间 T：特征必须是 T 前真实可获得的信息。T 为 UTC 月初，历史过滤条件严格为 timestamp < T；目标窗口为 [T, 下一月初)。

- **A：预测时点安全**，限定于本报告的事件时间可见性假设。
- **B：需要历史化后才能使用**，本项目当前缺失历史版本时不可启用。
- **C：禁止作为历史预测特征**，本项目当前回测必须排除。
- **D：暂时不确定**，需要补充证据；未确认则不启用。

'''+table(rows,['字段/信息','类别','处理规则'])+'''

## 本次实际启用范围

仅设计候选过去交互计数、评分分布、历史匿名用户去重数和日历特征；尚未创建模型特征矩阵。ID 只作为关联和分组键，不把未来活跃统计加入特征。B/D 类字段当前不进入特征候选的可执行清单。

## 五项优先审计风险

1. cohort/history/rolling 窗口跨过 T，或者使用未来活跃状态与最后交互时间删掉零值商品。
2. 采集时 price、平均评分、累计评分及可变页面属性被当作历史信息。
3. 采集时 helpful_vote 以及未经确认时点的 verified 状态被回填至早期。
4. 全数据标准化、填补、文本词表、特征选择，以及查看 2022 测试效果后调整粒度/阈值。处理器只能在各训练折拟合。
5. 官方全期 5-core 筛选与缺少发布/入库时间：本地时间切分无法消除源选择偏差，也不能证明真实运营时点可见性。

## 时间切分执行原则

调参/选择模型只在训练区间内部滚动验证。所有用于训练的标签窗口结束时间必须 ≤ 折的训练截止时刻；如果未来 horizon 加长，须同步隔离跨边界标签。每个预测点可以滚动使用该时点之前已实现的交互更新历史特征，但不得提前看到后续月份。2022 测试目标不能训练参数；单月 horizon 使用不重叠日历窗口。不得按2023或2022的活动筛选 cohort。
'''


def modeling_report(summary,cohort):
    return f'''# Business Question

对于在 2019 年已经有足够评论活动的 Patio_Lawn_and_Garden 父商品，能否仅凭预测时点前的评论交互历史，预测下一自然月在官方 5-core 用户/商品筛选数据中的 interaction 数量？结果用于比较月度评论热度预测方法，不直接指导真实库存量或广告预算。

# Unit of Analysis

parent_asin × month。按 UTC 自然月，不按变体 asin 建模；5-core 没有 asin。正式固定 cohort 为 {cohort['selected_products']:,} 个父商品。选择依据见 time_granularity_analysis.md 的训练期稀疏度比较。

# Prediction Time

每月 1 日 00:00:00 UTC，即 T；第一次为 2020-01-01。仅 timestamp < T 的记录可用于历史特征。以评论事件时间近似可见时间是未验证的回测假设，不宣称真实生产可获得时点已得到证明。

# Prediction Horizon

下一整个自然月：[T, next_month(T))。同一 T 的输入不得包含目标月记录。预测 2022 年各月时可滚动读取此前已实现月份的历史，但模型参数仅在训练区间拟合。

# Target

正式名称：**future_interaction_count**。

定义：对 cohort 中父商品 p，在完整官方 5-core 文件中满足 parent_asin=p 且 T ≤ timestamp < next_month(T) 的交互记录数量。沿用官方去重后交互口径，不恢复被 5-core 排除的用户/商品。固定商品 × 月网格没有记录时记为“此数据源中的 0 条交互”；不解释为零真实需求或商品仍在售。

升级候选：**future_verified_interactions**，需要完整或可证明完整的原始商品评论历史，统计未来窗口中 verified_purchase=True 的记录。本次只验证 schema，不具备启用该目标的数据条件。

# Why This Target

评论只覆盖发表评论的用户，5-core 又筛选活跃用户/商品。verified review 同样不是全部订单。本项目不包含真实商品销量，因此 target 只能称 demand/popularity proxy。禁止以 sales、units_sold、revenue 命名。

# Candidate Features

当前仅设计以下在 T 前可计算的候选，不执行特征工程：

- 上 1、2、3、6、12 个自然月的 interaction count；过去 3/6/12 月总量、平均量及过去非零月数。
- T 前 3/6/12 月的评分平均值、各等级计数和比例；同时保留统计支持条数，零交互不强行填入伪造平均评分。
- T 前窗口的去重用户数、此前历史交互累计量（累计起点限定 2019-01-01），仅使用已经出现的用户。
- 同月上年交互量（lag 12）、基于纯历史的变化量；除数为零的比例需要明确规则，不能伪造增长率。
- 可提前知道的目标月份、季度、月份周期编码，以及从预定 cohort 锚点开始的月数。

当前不把原始 review 小样本或 metadata 快照拼接进历史特征。

# Leakage Risks

详细分类见 leakage_audit.md。关键风险：滚动/聚合包含目标月、未来活跃度筛选、metadata 采集快照、累计 helpful votes、全数据拟合预处理器及测试调参。官方全期 5-core 成员资格还有源级未来选择偏差，本项目只能做限定样本的回顾性评价。

# Train / Test Strategy

- 历史预热与 cohort 筛选：2019-01-01 ≤ 时间 < 2020-01-01。
- 正式分析/预测目标月份：2020-01 至 2022-12，共 36 个月。
- Train 目标窗口：2020-01-01 ≤ 时间 < 2022-01-01，共 24 个月。
- 训练内部验证：例如 2020 年训练、2021 年滚动验证；模型和处理规则确定后，使用完整 2020–2021 年重新拟合。不会在本阶段训练。
- Test 目标窗口：2022-01-01 ≤ 时间 < 2023-01-01，共 12 个月；各商品都保留，不按测试活跃度剔除。
- 不随机打散商品 × 时间行。不按测试效果改变 cohort、粒度或历史阈值。
- 2023 年仅保留覆盖诊断：文件截止到 9 月 9 日；5–8 月出现显著交互数量突降，原因未确认，因此方案 A/B 的 2023 年测试暂不采纳。

# Cohort Rule

1. 从**整个**官方 category 5-core 文件筛选，完全不以 metadata 前缀限定成员。
2. 仅在历史区间 [2019-01-01, 2020-01-01) 内统计：interaction ≥ {cohort['min_history_interactions']} 且至少 {cohort['min_history_active_months']} 个非零自然月。
3. 满足条件 {cohort['eligible_products']:,} 个商品；升序排序 SHA-256("42|parent_asin")，以 parent_asin 破同分，固定取前 {cohort['selected_products']:,} 个。seed=42，cap=5,000 用于控制计算量。
4. 排序不依赖源文件顺序；倒序输入验证得到相同成员。history 的最大时间戳严格小于 2020-01-01。
5. 不要求训练期或测试期仍然有交互，不使用未来评分、活动或预测结果。筛选后不因模型表现好坏换商品。

formal_cohort.csv 只保存 ID、锚点前历史审计信息及哈希。cohort_summary.csv 包含后期诊断信息，只用于覆盖报告，禁止作为筛选或特征输入。现有 metadata 只匹配 {cohort['metadata_snapshot_matches']} / {cohort['selected_products']} 个正式 cohort 商品；这是旧前缀样本覆盖限制，不据此删除商品或声称已具备全 cohort 的竞品页面数据。

# Known Biases

- **5-core bias**：活跃用户/商品被保留；全时期成员资格可能依赖未来行为，不能靠本地 cutoff 完全消除。
- **review bias**：评论不是订单，发表评论的用户不是全部购买用户。
- **survivorship / activity bias**：2019 历史门槛偏向较活跃商品，排除后期新品；没有再用未来存活情况筛选，仍不能推广到冷启动商品。
- **metadata snapshot bias**：采集时属性不是历史状态，当前不用作预测特征；旧 metadata 样本也有顺序偏差。
- **2023 incomplete-year issue**：9 月截止且较早月份数量突降，不能与完整年度直接比较或假装为完整年度测试。
- 2019 的固定 cohort 与 2022 商品群可能不同；没有库存/上下架信息，零评论不证明商品仍在售。
- 时间戳缺少真实发布/入库时点，历史可见性是事件时间假设；类目采集完备性未得到独立证明。

# What This Project Can Claim

能够复现官方 5-core 数据的固定历史商品范围，完成商品 × 月数据口径、质量和泄漏审计，并在后续阶段比较限定样本的未来月度 interaction proxy 预测方法。本阶段没有预测效果或业务成果可声称。

# What This Project Cannot Claim

不能声称“准确预测真实 Amazon 销量”、收入、全部订单、因果需求、真实购买概率或补货数量。不能声称 verified 目标已经可用、全类目随机代表性、全商品 metadata 覆盖或完全无源选择偏差。不能把回顾性结果直接当成线上经营收益或对所有 Amazon Garden 商品有效的结论。
'''


def update_readme(summary,cohort):
    path = PROJECT_ROOT/'README.md'
    backup = OUTPUT_DIR/'README_stage1.md'
    if not backup.exists():
        backup.write_text(path.read_text())
    text = backup.read_text()
    text = text.replace('本次只执行 **Stage 1：项目骨架、真实数据获取/读取、结构和质量摸底**。',
                        '已完成 Stage 1；当前完成 **Stage 1.5：数据底座修正与建模口径设计**。未开始 Stage 2。')
    text = text.replace('固定商品范围（不是根据分析结果筛选）：','Stage 1 试读商品范围（已保留，**不再作为正式 cohort**）：')
    text = text.replace('这个真实商品范围可用于流程搭建和范围内 interaction 趋势探索；正式预测和类目推广结论之前，必须在 Stage 2 审查样本代表性与目标口径。',
                        '该试读商品范围仅为 Stage 1 结构和质量摸底用途；Stage 1.5 正式 cohort 已改为完整 5-core 中按预测前历史筛选，不再受 metadata 前缀限制。')
    text = text.replace('│   └── reporting.py', '│   ├── reporting.py\n│   ├── check_raw_review.py\n│   ├── analyze_recent_period.py\n│   ├── build_cohort.py\n│   ├── analyze_time_granularity.py\n│   ├── scope_reporting.py\n│   └── verify_stage15.py')
    text = text.replace('│   └── data_quality_report.md', '│   ├── data_quality_report.md\n│   ├── raw_review_feasibility.md\n│   ├── time_granularity_analysis.md\n│   ├── leakage_audit.md\n│   └── modeling_scope.md')
    text = text.replace('- interim：固定商品范围的 CSV 交互，原始字段和原始值保留。', '- interim：旧 interactions_cohort.csv 保留 Stage 1 试读交互；formal_cohort.csv 记录 Stage 1.5 正式商品成员及预测前历史审计信息。')
    before,_,_ = text.partition('## 10. Next Stage')
    addition = f'''### Stage 1.5 实际结论

- 原始 review 大于 1.5 GB 上限；只获取 4 MiB gzip 前缀并验证 2,000 条真实记录，确认 verified_purchase、helpful_vote、title/text 等字段存在。小样本只用于 schema，正式输入继续使用完整 5-core。
- 正式 cohort：仅使用 2019 年的 ≥12 条 interaction 和 ≥3 个活跃月条件，{cohort['eligible_products']:,} 个符合；按 seed 42 的 SHA-256("42|parent_asin") 顺序固定取 {cohort['selected_products']:,} 个，不使用未来活动或 metadata 匹配条件。
- 不把旧范围的 2006 年起点误认为完整数据起点：完整 5-core 实际最早为 2000 年。早期数据保留，但正式口径只采用较近且能够形成完整年度对照的 2020–2022；2019 为历史预热。
- 最终粒度 parent_asin × month：训练期周网格零值 73.64%，月网格零值 41.52%，月度 count 中位数为 1。月粒度减少稀疏，保留月份季节信息，但不支持周内促销判断。
- 预测时点 T 为 UTC 月初，horizon 为 [T, 下一月初)。正式 target：**future_interaction_count**，仅统计官方 5-core 中的未来月交互。
- Train：2020–2021；Test：2022；训练内部使用时间滚动验证。2023 年 3 月 50,084 条、5 月 4,497 条、8 月 676 条，原因未确认，不直接认定为真实需求下降，暂不作为正式测试年份。
- verified 升级候选是 future_verified_interactions；缺完整 raw 商品历史，当前不能启用。只依赖 T 前交互、评分、用户聚合和日历特征；采集时 metadata 快照和 helpful_vote 不可回填为历史特征。
- 官方全期 5-core 活跃筛选可能依赖未来，事件时间也未证明等于真实可见时间；本项目限定为条件样本的回顾性 proxy 预测，不宣称严格生产无泄漏。
- 现有 metadata 覆盖正式 cohort {cohort['metadata_snapshot_matches']}/{cohort['selected_products']} 个；保留但不用它筛选商品或充当全 cohort 的历史竞品属性。

报告：

- [原始 review 可行性](reports/raw_review_feasibility.md)
- [时间粒度与近期覆盖](reports/time_granularity_analysis.md)
- [泄漏审计](reports/leakage_audit.md)
- [正式建模口径](reports/modeling_scope.md)

Stage 1.5 复现命令（Stage 1 的原始 5-core 文件保留）：

```bash
python3 -B -m src.check_raw_review
python3 -B -m src.analyze_recent_period
python3 -B -m src.build_cohort
python3 -B -m src.analyze_time_granularity
python3 -B -m src.scope_reporting
python3 -B -m src.verify_stage15
```

新增脚本分别负责 schema 验证、完整近期数据扫描、历史 cohort、粒度诊断、报告和结果审计。数据/路径/规则集中于 config.py；仍不需要第三方依赖。正式 cohort 保存于 data/interim/formal_cohort.csv，旧 interactions_cohort.csv 保留为 Stage 1 输入。下载原始字段样本不会替代旧文件。outputs/stage15_execution_record.md 保存实际执行命令及退出码。

## 10. Next Stage

Stage 2 已具备**限定 5-core interaction proxy** 的数据清洗和商品 × 月结构设计条件。首先实施明确的历史 cutoff、月度零值口径及 source bias 标记，训练内部处理缺失与异常；不得启用无历史版本的 metadata。完整 verified-review 目标和正式 cohort 竞品属性分析仍需额外数据，目前不具备。本次仅完成口径和诊断，未生成特征矩阵、未进行竞品 EDA、未训练模型、未开始 Stage 2。
'''
    path.write_text(before+addition,encoding='utf-8')


def main():
    probe=json.loads((OUTPUT_DIR/'raw_review_probe.json').read_text())
    recent=json.loads((OUTPUT_DIR/'recent_period_profile.json').read_text())
    cohort=json.loads((OUTPUT_DIR/'cohort_selection.json').read_text())
    summary=json.loads((OUTPUT_DIR/'stage15_summary.json').read_text())
    reports={'raw_review_feasibility.md':raw_feasibility(probe),
             'time_granularity_analysis.md':granularity_report(summary,recent,cohort),
             'leakage_audit.md':leakage_report(),
             'modeling_scope.md':modeling_report(summary,cohort)}
    for name,content in reports.items():
        (REPORT_DIR/name).write_text(content,encoding='utf-8')
        print(f'已生成 {name}')
    update_readme(summary,cohort)
    print('README 已更新；Stage 1 原 README 保留于 outputs/README_stage1.md。')


if __name__ == '__main__':
    main()
