# Change: 营销经营 GraphRAG（图模型上的检索增强问答）

状态：`proposed`。本体依据 [../marketing-data-processing/ontology.md](../marketing-data-processing/ontology.md)，场景依据 [../marketing-data-processing/scenarios.md](../marketing-data-processing/scenarios.md)，清洗产物 `datasets/processed/marketing_2026H1/`。

上游 change `marketing-data-processing` 只出干净表；本 change 把这些表与本体盖成**图**，并在图上做**轻量 GraphRAG**：自然语言问句 → 实体链接 → 子图检索 → 指标/明细拼装 → 带口径说明的答案。

## Why

纯 NL→SQL 方案在这批数据上会稳定踩坑（每条都在 [ontology.md §5](../marketing-data-processing/ontology.md) 有实采证据）：

| 坑 | 裸 SQL 的后果 | 图模型的防线 |
|---|---|---|
| 达成率漏「组织限定」 | 227% | 图上 `org_scope` 是节点/边属性，检索路径必带 |
| 漏「机型覆盖」 | 147% | `ProductType ⇢ measuredAgainst` 边只连预算覆盖的 6 类 |
| 漏「科室非空」 | 102.6% | 空键不建边（公理 A10），未归属行进 `unassigned` 桶 |
| 两张预算相加 | 预算翻倍 | `Plan ⊥ BusinessEvent`，两投影无连接边（B10） |
| 元 / 万元混除 | 差 10⁴ 倍 | 单位写在边的属性上，对照前强制换算 |
| 出货表 `fdept` 误当科室 | 只 60% 命中 | 该列不进图（ontology §5.6） |

图模型的价值不在"更聪明"，而在**把口径写进结构**：问句走哪条路径，就自动带上那条路径的过滤。

## What Changes

1. **图建模**：`datasets/build_marketing_graph.py` 由清洗产物盖图 → `datasets/json/marketing_cleaned_semantics.json`（Explorer 可加载）+ `datasets/json/marketing_ontology.ttl`。
2. **轻量 GraphRAG**：`datasets/marketing_graphrag.py`，纯 Python、无外部依赖（不接 LLM、不接图数据库）。
3. 检索四阶段：**实体链接 → 路径绑定 → 子图检索 → 指标拼装**。

### 图节点（[ontology.md §1.2](../marketing-data-processing/ontology.md) 判据筛选后）

| 节点类 | 规范键 | 实采基数 |
|---|---|---|
| `SalesPerson` | `sales_code` | 455 |
| `Dept` | `fdept` | 37 + 组织侧 40 |
| `Area` | `area` | 9~10 |
| `BusinessGroup` | `org_name` | 少量 |
| `Customer` | `cust_code` | ~4,245 |
| `Product`（机型） | `zprod_name` | 527 |
| `ProductType` | `zprod_type` | 22 |
| `Month` | `year,month` | 6 |
| `SignOrderLine` | `docno+docno_num` | 7,558 |
| `ShipOrderLine` | `docno+line_no` | 8,036 |
| `DeptBudgetMonth` | `fdept,year,month` | 234 |
| `ProductBudgetMonth` | `product_type,year,month` | 36 |

**不建节点**：主管（无工号键）、工厂 / `WERKS`、机型系列（词表不统一）、合同名、物料编码 `FmateNumber`（是 SKU 不是机型）。理由见 [ontology.md §1.2](../marketing-data-processing/ontology.md)。

### 图边

| 边 | 从 → 到 | 属性 |
|---|---|---|
| `belongsTo` | `SalesPerson → Dept` | — |
| `partOf` | `Dept → Area → BusinessGroup` | — |
| `categorizedAs` | `Product → ProductType` | 函数性（A6） |
| `locatedIn` | `Customer → 客户地区`（属性化，不建地区节点） | `cust_area` |
| `signedBy` | `SignOrderLine → SalesPerson` | — |
| `shippedBy` | `ShipOrderLine → SalesPerson` | — |
| `ofModel` | 事件 → `Product` | — |
| `contractParty` / `shipTo` | 事件 → `Customer` | 角色 |
| `inMonth` | 事件 → `Month` | — |
| `measuredAgainst` | `Dept ⇢ DeptBudgetMonth` / `ProductType ⇢ ProductBudgetMonth` | **查询时对照，物理不建边** |

## Non-goals

- 不接 LLM（本 change 是规则式图检索；LLM 接入口留后续 change）。
- 不接图数据库（Neo4j / FalkorDB 等），图以 JSON 落盘 + 内存检索。
- 不生成 RDF 三元组库 / SPARQL 端点（`.ttl` 只是本体声明，对照 `iot_ontology.ttl`）。
- 不重做清洗（输入必须是 `process_marketing_data.py` 的产物）。
- 不回答 [scenarios.md §9](../marketing-data-processing/scenarios.md)「不要问清单」里的问题 —— 应**显式拒绝并说明原因**。

## Impact

- 新增：`datasets/build_marketing_graph.py`、`datasets/marketing_graphrag.py`。
- 新增产物：`datasets/json/marketing_cleaned_semantics.json`、`datasets/json/marketing_ontology.ttl`。
- 读取：`datasets/processed/marketing_2026H1/*.parquet`。

## 退出条件

[tasks.md](./tasks.md) 全部勾选：图节点/边齐备 → 检索冒烟（CQ1–CQ6）→「不要问」问法被正确拒绝 → 达成率与 [metrics.md](../marketing-data-processing/metrics.md) H1 实算摘要一致。
