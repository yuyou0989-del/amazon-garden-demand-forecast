"""把统计结果写成数据字典和质量报告，不生成不存在的指标。"""
import json

MEANINGS = {
    'user_id': ('匿名用户标识', 'ID'),
    'asin': ('商品变体标识', 'ID'),
    'parent_asin': ('父商品标识；metadata 关联键', 'ID'),
    'timestamp': ('评论发生时间，Unix 毫秒；展示统一使用 UTC', '时间'),
    'rating': ('交互评分，合法整数等级 1–5', 'EDA'),
    'verified_purchase': ('平台标注是否验证购买', '潜在目标构造'),
    'helpful_vote': ('评论获得的有帮助票数', 'EDA'),
    'text': ('评论正文', '潜在特征'),
    'main_category': ('商品页面记录的主类目，可能不同于数据文件分类', 'EDA'),
    'price': ('采集时商品页面价格，美元；不是历史价格序列', '潜在特征'),
    'store': ('页面店铺名称；不直接等同品牌', 'EDA'),
    'categories': ('商品分类层级列表', 'EDA'),
    'features': ('商品卖点列表', '潜在特征'),
    'description': ('商品描述列表', '潜在特征'),
    'average_rating': ('采集时页面平均评分；有未来信息风险', 'EDA'),
    'rating_number': ('采集时页面累计评分数；有未来信息风险', 'EDA'),
    'details': ('商品详情字典；可能含 Brand，不新增原始 brand 字段', '潜在特征'),
    'images': ('商品或评论图片对象列表', '暂不使用'),
    'videos': ('视频对象列表', '暂不使用'),
    'bought_together': ('页面推荐搭配商品', '暂不使用'),
    'subtitle': ('可选字段；本子集中观测值均为 null，语义暂不确认', '暂不使用'),
    'author': ('可选字段；本子集中观测值均为 null，语义暂不确认', '暂不使用'),
}
HEADINGS = ['Dataset Overview', 'Time Coverage', 'Product Coverage',
            'Review / Interaction Quality', 'Metadata Quality', 'Missing Values',
            'Duplicate Check', 'Review-Metadata Matching', 'Potential Problems',
            'Stage 2 Recommendations']


def display(value):
    if value is None:
        return '不存在/无法计算'
    return json.dumps(value, ensure_ascii=False).replace('|', '\\|').replace('\n', ' ')


def percentage(value):
    return '不存在/无法计算' if value is None else f'{value:.4%}'


def table(rows, headers):
    result = ['| ' + ' | '.join(headers) + ' |', '| ' + ' | '.join(['---']*len(headers)) + ' |']
    for row in rows:
        result.append('| ' + ' | '.join(str(value).replace('\n', ' ') for value in row) + ' |')
    return '\n'.join(result)


def dictionary(result):
    output = ['# Data Dictionary', '',
              '只记录实际读取的字段。缺失 = 字段不存在、null、空白字符串、空列表或空字典。',
              'CSV 原始 dtype 为 str；数值统计单独解析为数字，不改写原始数据。示例截断至 160 字符，完整前 5 行见 outputs/inspection_summary.json。', '']
    for kind in ('reviews', 'metadata'):
        output += [f'## {kind}', '']
        rows = []
        for key, info in result[kind]['fields'].items():
            meaning, purpose = MEANINGS.get(key, ('含义尚待核实', '暂不使用'))
            if key == 'title':
                meaning, purpose = ('商品标题' if kind == 'metadata' else '评论标题'), '潜在特征'
            types = ', '.join(f'{name}: {count}' for name, count in info['types'].items())
            rows.append([key, types, meaning, display(info['example'])[:160],
                         percentage(info['missing_rate']), purpose])
        output += [table(rows, ['字段名', '数据类型（实际观测次数）', '含义', '示例', '缺失率', '后续用途']), '']
    output += ['## 不存在的重点字段', '',
               '5-core 交互文件中没有 asin、verified_purchase、helpful_vote、评论 title/text。',
               'metadata 没有顶层 brand；仅检查真实 details.Brand 的可用率，不把 store 假定为品牌。', '']
    return '\n'.join(output)


def quality(result):
    r, m = result['reviews'], result['metadata']
    c, d = result['coverage'], result['distributions']
    manifest = result.get('download_manifest', {})
    def missing(data, field):
        info = data['fields'].get(field)
        return percentage(info['missing_rate']) if info else '不存在/无法计算'
    sections = {}
    sections['Dataset Overview'] = table([
        ['交互分析输入（固定商品范围）', r['file'], r['rows'], r['columns'], r['bytes']],
        ['metadata 原始记录子集', m['file'], m['rows'], m['columns'], m['bytes']],
    ], ['数据', '文件', '行数', '列数', '字节数']) + '\n\n' + (
        f'完整官方 5-core 文件实际扫描 {manifest.get("source_interactions", "无法计算")} 行。'
        '\n\n分析范围为 metadata 原始顺序第 1–10,000 行对应父商品在整个 5-core 文件中的全部交互；'
        '保留这些商品在 5-core 用户子集中的历史，不代表原始评论全集。未删除异常或重复记录。')
    sections['Time Coverage'] = (
        f'最早：{display(r["time_min"])}；最晚：{display(r["time_max"])}（UTC）。'
        f'\n\n跨度：{display(result["time_span_days"])} 天。Unix 毫秒转换，不自动纠正单位。'
        '\n\n' + table(list(r['by_year'].items()), ['年（UTC）', 'interaction 数量']) +
        f'\n\n不可解析时间：{r["flags"].get("unparseable_timestamp", 0)}；'
        f'超出 [1996-01-01, 2023-10-01) 官方采集窗口：{r["flags"].get("outside_source_window", 0)}。')
    sections['Product Coverage'] = (
        f'交互唯一 parent_asin：{c["review_parent_ids"]}；metadata 唯一 parent_asin：{c["metadata_parent_ids"]}；'
        f'唯一 user_id：{c["users"]}。\n\nasin 数量：{display(c["asins"])}；'
        f'asin 与 parent_asin 关系：{display(c["asin_multiple_parents"])}。'
        '\n\n每个有效 parent_asin 的 interaction 数量分布：\n\n' +
        table(list(d['interactions_per_parent'].items()), ['统计量', '值']) +
        f'\n\nmetadata 中没有所选 5-core 交互的记录：{c["metadata_without_cohort_reviews"]}。'
        '这不等于零需求，可能只是被 5-core 用户/商品筛选排除。')
    sections['Review / Interaction Quality'] = (
        table(list(r['rating_distribution'].items()), ['原始 rating', '数量']) +
        f'\n\n非法非空 rating：{r["flags"].get("invalid_rating", 0)}；评分缺失率：{missing(r,"rating")}。'
        f'\n\nverified_purchase 比例：{percentage(result["verified_purchase_ratio"])}。'
        f'\n\nhelpful_vote 分布：{display(d["helpful_vote"])}。'
        '\n\n5-core 已由官方进行重复交互处理；本项目仍检查完全相同的行，不假定官方处理后必然无重复。')
    sections['Metadata Quality'] = (
        f'商品记录数：{m["rows"]}；price 缺失率：{missing(m,"price")}；'
        f'average_rating 缺失率：{missing(m,"average_rating")}；rating_number 缺失率：{missing(m,"rating_number")}。'
        f'\n\nstore 缺失率：{missing(m,"store")}；顶层 brand：不存在；'
        f'details.Brand 内容缺失率：{percentage(m["flags"].get("missing_details_brand",0)/m["rows"] if m["rows"] else None)}。'
        f'\n\n非法非空 price（无法转数值、非有限值或 ≤ 0）：{m["flags"].get("invalid_price",0)}。'
        '\n\nprice 分布（全部可解析有限值，异常未删除）：\n\n' +
        table(list(d['price'].items()), ['统计量', '值']) +
        f'\n\ncategories 内容缺失率：{missing(m,"categories")}；出现的层级标签数：{m["category_labels"]}。'
        '\n\n以下标签跨层级计数，单商品可计入多个标签：\n\n' +
        table(m['category_top20'], ['categories 标签（前 20）', '记录数']) +
        '\n\nmain_category 实际分布（不要用它代替源文件类目或 categories 层级）：\n\n' +
        table(list(m['main_category_distribution'].items()), ['main_category', '记录数']))
    missing_rows = []
    for kind in ('reviews', 'metadata'):
        for field, info in result[kind]['fields'].items():
            missing_rows.append([kind, field, info['absent'], info['null'], info['empty'], info['missing'], percentage(info['missing_rate'])])
    sections['Missing Values'] = table(missing_rows, ['数据', '字段', '字段不存在', 'null', '空白/空容器', '总缺失', '缺失率']) + (
        '\n\n关键字段检查：\n\n' + table([
            ['reviews', field, missing(r,field)] for field in ('parent_asin','asin','user_id','timestamp','rating')
        ] + [['metadata','parent_asin',missing(m,'parent_asin')]], ['数据', '关键字段', '缺失率']))
    sections['Duplicate Check'] = (
        f'完全重复行（首条之外的记录）：reviews {r["duplicates"]}；metadata {m["duplicates"]}。'
        '\n\n使用排序后的完整 JSON 表示比较，不仅依靠哈希；JSON 字段顺序不影响判定。'
        f'\n\nmetadata 重复 parent_asin 的额外记录数：{c["metadata_duplicate_parent_rows"]}。')
    sections['Review-Metadata Matching'] = (
        f'按 parent_asin 匹配；匹配 interaction 行：{c["matched_review_rows"]}/{r["rows"]}，'
        f'行匹配率：{percentage(c["review_row_match_rate"])}。'
        f'\n\n匹配唯一父商品：{c["matched_review_parents"]}/{c["review_parent_ids"]}，'
        f'父商品匹配率：{percentage(c["review_parent_match_rate"])}。'
        '\n\n该输入预先按 metadata 商品范围筛选，匹配率是流程完整性检查；不能据此宣称原始 Amazon 类目 metadata 全覆盖。')
    sections['Potential Problems'] = (
        '1. 5-core 仅保留活跃用户和商品，交互量与原始评论全集不同，存在选择偏差。\n'
        '2. 固定 metadata 前 10,000 条有源文件排列偏差，不是类目随机样本。\n'
        '3. asin、购买验证、helpful_vote 和评论文本缺失，无法分析变体或构造 verified review 目标。\n'
        f'4. price 缺失率为 {missing(m,"price")}；价格、average_rating、rating_number 是采集时快照，不能直接作为历史预测特征。\n'
        '5. 没有销售、库存、广告、上架/下架和价格历史；没有交互不能自动当成零需求。2023 年仅覆盖至数据采集截止时点，不能直接和完整年份比较。')
    sections['Stage 2 Recommendations'] = (
        '1. 先审查商品范围的代表性和历史覆盖；决定保留 5-core interaction proxy，还是扩充原始评论以获得 verified_purchase。\n'
        '2. 明确缺失值、异常值和 metadata 唯一键的处理规则，再进行清洗；当前不自动删除。\n'
        '3. 对商品 × 时间聚合，区分缺失观察和真实零值，检查月份覆盖及右截断。\n'
        '4. 明确特征可用时点，防止采集快照和未来累计评分引入时间泄漏；采用时间切分。\n'
        '5. 只有这些规则明确后才确定未来 interaction count 的代理目标；本阶段未训练模型。')
    return '\n\n'.join(f'# {heading}\n\n{sections[heading]}' for heading in HEADINGS) + '\n'


def write_reports(result, report_dir):
    if result is None:
        (report_dir/'data_dictionary.md').write_text('# Data Dictionary\n\n真实输入尚未读取；没有观测字段、示例或缺失率。\n')
        (report_dir/'data_quality_report.md').write_text('\n\n'.join(f'# {heading}\n\n真实输入缺失，无法计算；未使用模拟数据。' for heading in HEADINGS)+'\n')
        return
    (report_dir/'data_dictionary.md').write_text(dictionary(result), encoding='utf-8')
    (report_dir/'data_quality_report.md').write_text(quality(result), encoding='utf-8')
