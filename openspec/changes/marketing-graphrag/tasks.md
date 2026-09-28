# Tasks — 营销经营 GraphRAG

实现 [spec.md](./specs/marketing-graphrag/spec.md)，设计 [design.md](./design.md)，决策 [decisions.md](./decisions.md)。  
入口 `datasets/build_marketing_graph.py` → `datasets/marketing_graphrag.py`。

## 1. 建图：节点

- [x] 1.1 `SalesPerson` 455 / `Dept` 40 / `Area` / `BusinessGroup` / `Month` 6
- [x] 1.2 `Product` 527 / `ProductType` 22
- [x] 1.3 `Customer` 4,245（带 `cust_role`）
- [x] 1.4 `SignOrderLine` 7,558 / `ShipOrderLine` 8,036（G3 事件也建节点）
- [x] 1.5 不建：主管 / 工厂 / 系列 / 合同名 / 物料编码
- [x] 1.6 节点属性带 `org_scope`、`zprod_type`、`amount_wan`、`unit`

## 2. 建图：边

- [x] 2.1 `belongsTo`（SalesPerson → Dept）
- [x] 2.2 `partOf`（Dept → Area → BusinessGroup）
- [x] 2.3 `categorizedAs`（Product → ProductType）
- [x] 2.4 `signedBy` / `shippedBy`（事件 → SalesPerson）
- [x] 2.5 `ofModel`（事件 → Product）
- [x] 2.6 `contractParty` / `shipTo`（事件 → Customer）
- [x] 2.7 `inMonth`（事件 → Month）
- [x] 2.8 `ofDept` / `ofType`（**空键不建边**，A10）
- [x] 2.9 不建：两预算表之间的任何边（B10）

## 3. 产物

- [x] 3.1 `datasets/json/marketing_cleaned_semantics.json`（`graph_id`/`nodes`/`edges`/`links`）
- [x] 3.2 `datasets/json/marketing_ontology.ttl`（对照 `iot_ontology.ttl`）
- [x] 3.3 图元数据含节点/边计数与各类的基数

## 4. 检索：实体链接

- [x] 4.1 科室 / 大区 / 产品类型 / 机型 / 月份 值域词典精确 + 前缀匹配
- [x] 4.2 人名匹配 `emp_dim.sales_name`，重名列候选
- [x] 4.3 指标词 → 度量槽位（管理出机 / 考核出机 / 管理签单 / 连续不签单 / 未出机）

## 5. 检索：路径绑定与子图

- [x] 5.1 意图分类：`achieve_dept` / `achieve_product` / `behavior_emp` / `customer_model` / `structure_share`
- [x] 5.2 达成类强制三口径（组织 / 机型 / 科室非空）+ 万元
- [x] 5.3 分子 `Σ amount_wan`，分母取对应预算节点
- [x] 5.4 行为类：`user_role='业务'`，按月求补集，离职分层
- [x] 5.5 结构份额：分母 = 自身总额，不是预算

## 6. 检索：答案与拒绝

- [x] 6.1 答案含 `caliber` / `numerator_wan` / `denominator_wan` / `achieve_pct` / `evidence`
- [x] 6.2 `top_contributors` 列出构成前 N（明细可回溯）
- [x] 6.3 「不要问清单」7 类问法显式拒绝并给原因（G5）
- [x] 6.4 交叉预算问法拒绝（B10）

## 7. 验收

- [x] 7.1 CQ1–CQ6（[ontology.md §6](../../marketing-data-processing/ontology.md)）冒烟通过
- [x] 7.2 达成率与 [metrics.md](../../marketing-data-processing/metrics.md) H1 实算摘要一致（130.6% / 91.1% / 103.2%）
- [x] 7.3 「科室×产品预算」「主管业绩」「毛利率」被正确拒绝
- [x] 7.4 不连内网、不接 LLM、不接图数据库
