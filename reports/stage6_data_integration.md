# Stage 6A：历史与实时商品级关联核查

## 现有数据与 ID 语义

- 历史链：`data/interim/formal_cohort.csv` 有 **5,000 行、5,000 个唯一 `parent_asin`**；与 `data/processed/product_month_features.csv` 的 5,000 个 `parent_asin` 集合完全一致。5-core interaction 以父商品 ID 为粒度，没有 child `asin` 字段；Stage 3 也是 `parent_asin × UTC month`。
- 实时链：只读查询 `data/realtime/amazon_garden_realtime.db` 的 `search_snapshots`，有 **20 行、20 个唯一 `asin`**，位置 1–20，均为 `garden hose`、`amazon.sg`、`SGD`、`playwright`。`asin` 来自当前搜索卡片的 `data-asin`；`title`、`price`、`rating`、`review_count` 均非空。
- `parent_asin` 标识历史数据的父商品；实时 `asin` 标识搜索结果卡片上的商品 ASIN，现有卡片和数据库没有其 `parent_asin`。商品变体可能形成 child/parent 层级，因此这两种字段不能未经验证直接视作同一层级。不能从标题相似或字符串格式推断父子关系。参见现有 `reports/data_dictionary.md`、`reports/modeling_scope.md`、`reports/realtime_data_dictionary.md`。

## 直接 overlap 与 JOIN 结论

仅作诊断的集合交集 `historical parent_asin ∩ realtime asin`：**0 个**；overlap IDs：**无（空集合）**。

**NOT SAFE TO JOIN。** 当前没有任何直接相同的 ID，也没有实时 `asin ↔ parent_asin` 的可靠映射。即使以后出现字符串相等，也需核对是否为同一商品层级、同一市场/页面实体，不能仅凭相等自动断定可用。此次不创建映射或合并表，不把 2026 实时字段回填至 2020–2022 历史特征。

## 当前业务层组合与真正融合的条件

- **Historical Demand Model：** Amazon Reviews 2023 官方 Garden 5-core → 固定 5,000 个 `parent_asin` → 月度历史特征 → RandomForest → 历史 interaction 热度代理信号；不是销量。
- **Realtime Competitor Monitor：** Amazon.sg `garden hose` 搜索 → 当前 20 个商品 `asin` → SQLite 中的展示价格、评分、评价量、搜索结果位置快照 → 当前竞品状态；单次快照不能说明变化趋势。

两模块共同服务 Garden 竞品监控，但**不能声称这 20 个实时商品已经进入历史模型，或已有商品级融合**。真正融合需从可信来源获得可核验的 `asin ↔ parent_asin` 映射，并确认市场及商品实体口径一致；之后再核对交集与时间可用性，避免历史预测使用未来快照。

本报告只离线读取已有 CSV、SQLite 和文档；没有网络请求、数据修改或虚假 JOIN。
