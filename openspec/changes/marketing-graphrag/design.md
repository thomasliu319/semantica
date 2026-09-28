# Design — 营销经营 GraphRAG

入口 `datasets/build_marketing_graph.py`（建图）+ `datasets/marketing_graphrag.py`（检索）。  
输入 `datasets/processed/marketing_2026H1/*.parquet`（必须先跑 `process_marketing_data.py`）。  
输出 `datasets/json/marketing_cleaned_semantics.json`、`datasets/json/marketing_ontology.ttl`。

## 一、建图

```
parquet（清洗产物）
   │
   ├─ 维度 → 节点：SalesPerson / Dept / Area / BusinessGroup / Customer / Product / ProductType / Month
   ├─ 事实 → 节点：SignOrderLine / ShipOrderLine（G3）
   └─ 边：
        belongsTo   SalesPerson → Dept
        partOf      Dept → Area → BusinessGroup
        categorizedAs  Product → ProductType
        signedBy    SignOrderLine → SalesPerson
        shippedBy   ShipOrderLine → SalesPerson
        ofModel     事件 → Product
        contractParty / shipTo  事件 → Customer
        inMonth     事件 → Month
        ofDept      事件 → Dept（仅 fdept 非空，A10）
        ofType      事件 → ProductType（仅 zprod_type 非空）
        （measuredAgainst 不建物理边，查询时对照，B10）
```

节点属性带口径标记：`org_scope`、`zprod_type`、`month`、`amount_wan`、`unit`。

节点规模（实采）：业务员 455 + 科室 40 + 大区 ~10 + 客户 4,245 + 机型 527 + 类型 22 + 月 6 + 签单 7,558 + 出货 8,036 ≈ **2.09 万节点**；边约 **7 万**。

## 二、检索四阶段

```
① 实体链接  问句中的字面量 → 图节点
    ├─ 科室名/区名/产品类型/机型/月份：值域词典精确匹配 + 前缀匹配
    ├─ 人名：emp_dim.sales_name（重名时列候选）
    └─ 指标词：管理出机/考核出机/管理签单/连续不签单… → 度量槽位

② 路径绑定  问法类型 → 检索路径（decisions.md 表）
    └─ 同时绑定强制口径（org_scope / zprod_type 覆盖 / fdept 非空 / 万元）

③ 子图检索  沿路径取节点与边；事件节点按口径过滤后聚合
    ├─ 达成类：分子 = Σ amount_wan（过滤后）；分母 = 对应预算节点属性
    └─ 行为类：按月求补集

④ 答案拼装  数字 + 口径四要素 + 构成明细 + 「不要问」拦截说明
```

## 三、口径强制点

| 阶段 | 强制项 | 漏掉的后果 |
|---|---|---|
| ③ | `org_scope = 'in_scope'` | 228.6% |
| ③ | `zprod_type ∈ 预算覆盖 6 类` | 148.2% |
| ③ | `fdept` 非空（`ofDept` 边天然满足） | 103.3% |
| ③ | 分子用 `*_hs_wan`，分母用预算万元 | 差 10⁴ 倍 |
| ② | 一次查询只走一条预算投影 | 预算翻倍 |

## 四、答案格式（G6 探针）

```json
{
  "question": "...",
  "intent": "achieve_dept_month",
  "caliber": {"org_scope": "in_scope", "model_covered": true,
              "dept_notnull": true, "unit": "万元含税"},
  "numerator_wan": 251576.35,
  "denominator_wan": 192663.33,
  "achieve_pct": 130.6,
  "evidence": {"nodes": 37, "edges": 6207, "rows": 6207},
  "top_contributors": [...],
  "caveats": [...]
}
```

## 五、非目标

不接 LLM / 图数据库 / SPARQL 端点；不重做清洗；不产出达成率报告（B1）。
