# Decisions — 营销经营 GraphRAG

状态：`proposed`（推荐默认，本轮按默认执行）。本体真源 [../marketing-data-processing/ontology.md](../marketing-data-processing/ontology.md)。  
上游决策继承 `marketing-data-processing` 的 B1–B10 / D1–D8，本 change 不重开。

| 题 | 选项 | 冻结含义 |
|---|---|---|
| G1 | `rule_based` | 实体链接与路径绑定走规则（词典 + 值域匹配），不接 LLM |
| G2 | `json_inmemory` | 图以 JSON 落盘 + 内存检索，不接图数据库（Neo4j/FalkorDB） |
| G3 | `facts_as_nodes` | 事件行（签单/出货）也建节点，可通过边回溯明细；不是只存聚合 |
| G4 | `caliber_on_edge` | 口径（组织/机型/单位）写在边与节点属性上，检索路径强制携带 |
| G5 | `refuse_explicitly` | 「不要问清单」问法显式拒绝并给出原因，不做近似回答 |
| G6 | `probe_not_report` | 检索结果返回口径四要素与分子分母；达成率是**探针**不是报告（B1） |

## 为什么 G3 保留事件节点

15,594 行事件全部建节点会让图变大（约 2.6 万节点 / 10 万边），换来的是**明细可回溯**：问「某科室达成」时能顺边列出构成该数字的单据。若只存聚合，就无法回答「为什么是这个数」。取舍：JSON 约 20–40 MB，内存检索 <1 s，可接受。

## 为什么 G5 要显式拒绝

[scenarios.md §9](../marketing-data-processing/scenarios.md) 的 7 类问法在数据上**无解**（如科室×产品的预算分配矩阵未导出）。近似回答会产出看似合理的错数 —— 比拒绝更危险。

## 检索路径与口径绑定

| 问法类型 | 路径 | 强制口径 |
|---|---|---|
| 组织达成 | `Dept ⇢ DeptBudgetMonth`（查询时对照）+ `Dept ← SalesPerson ← 事件` | `org_scope=in_scope` ∧ `zprod_type ∈ 覆盖` ∧ `fdept≠''` ∧ 万元 |
| 产品达成 | `ProductType ⇢ ProductBudgetMonth` | 同上，**不与组织路径同时取**（B10） |
| 人员行为 | `SalesPerson ← 事件.inMonth` | `user_role='业务'`；离职分层 |
| 客户×机型 | `Customer ← 事件 → Product` | 角色标注 `contract_party`/`ship_to` |
| 结构份额 | `ProductType ← Product ← 事件` | 分母 = 自身总额（不是预算） |

## 不建的边（结构性防线）

| 不建 | 原因 |
|---|---|
| `DeptBudgetMonth — ProductBudgetMonth` | 同一笔预算的两个投影（B10），相加会翻倍 |
| 空键参与的对照边 | 空 ≠ 空（A10） |
| `ShipOrderLine.fdept_sap — Dept` | SAP 出货组织与预算科室两套编码，仅 60% 重合 |
| `SalesPerson — Supervisor` | 主管无工号键，重名歧义 |
| 系列 / 工厂 / 合同名节点 | 判据 E3 不成立（[ontology.md §1.2](../marketing-data-processing/ontology.md)） |
