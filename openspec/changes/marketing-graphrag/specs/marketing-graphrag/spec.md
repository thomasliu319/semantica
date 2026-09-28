# Spec: 营销经营 GraphRAG

状态：`proposed`。见 [decisions.md](../../decisions.md)、[design.md](../../design.md)。  
上游：`marketing-data-processing` 的清洗产物；本体 [ontology.md](../../marketing-data-processing/ontology.md)。

## ADDED Requirements

### Requirement: 图由清洗产物盖成

系统 SHALL 以 `datasets/processed/marketing_2026H1/*.parquet` 为唯一输入建图。  
系统 SHALL NOT 直接读 `dataReport/dataset/*.csv`。  
系统 SHALL 输出 `datasets/json/marketing_cleaned_semantics.json`（`graph_id`/`nodes`/`edges`）与 `datasets/json/marketing_ontology.ttl`。

#### Scenario: 节点类齐备

- **WHEN** 建图完成
- **THEN** 节点类含 `SalesPerson`/`Dept`/`Area`/`BusinessGroup`/`Customer`/`Product`/`ProductType`/`Month`/`SignOrderLine`/`ShipOrderLine`

#### Scenario: 不建的节点

- **WHEN** 遇到主管姓名、工厂 `WERKS`、机型系列、合同名、物料编码 `FmateNumber`
- **THEN** 不建节点，仅作为宿主节点的属性（判据 E3 不成立）

### Requirement: 空键不建边

系统 SHALL NOT 为 `fdept` 为空的事件行建 `ofDept` 边（A10）。  
系统 SHALL NOT 为 `zprod_type` 为空的事件行建 `ofType` 边。  
这些行 SHALL 保留为事件节点，并计入 `unassigned` 桶。

#### Scenario: 空键不入对照

- **WHEN** 事件行 `fdept` 为空
- **THEN** 该行不参与任何对照检索，但仍在明细列表里可见

### Requirement: 两张预算表不连通

系统 SHALL NOT 建 `dept_budget_month` 与 `product_budget_month` 之间的任何边（B10）。  
系统 SHALL 在一次查询中只取一条预算投影。

#### Scenario: 交叉问法被拒

- **WHEN** 问句同时要求科室维度与产品类型维度的预算
- **THEN** 系统拒绝并说明「预算分配矩阵未导出」

### Requirement: 单位

系统 SHALL 以万元含税作为达成对照的唯一单位；事件节点属性 SHALL 同时保留元与万元两列（B3）。

#### Scenario: 元与万元不混除

- **WHEN** 计算达成率
- **THEN** 分子取 `amount_wan`，分母取预算 `*_hs`（万元）

### Requirement: 口径强制

系统 SHALL 在达成类检索中强制 `org_scope='in_scope'`、`zprod_type ∈ 预算覆盖集合`、科室非空。  
系统 SHALL 在答案中回显这三项（G6）。

#### Scenario: 达成率带口径

- **WHEN** 返回达成率
- **THEN** 同时返回 `numerator_wan`、`denominator_wan`、`caliber` 三项

### Requirement: 显式拒绝

系统 SHALL 对 [scenarios.md §9](../../marketing-data-processing/scenarios.md) 的「不要问清单」问法返回拒绝并说明原因（G5）。  
系统 SHALL NOT 给出近似数值。

#### Scenario: 主管维度被拒

- **WHEN** 问「某主管的团队业绩」
- **THEN** 拒绝并说明「主管只有姓名无工号键，存在重名歧义」

### Requirement: 本步不造结论

系统 SHALL NOT 生成达成率报告或名单（B1）。  
返回的达成率 SHALL 标注为口径探针。
