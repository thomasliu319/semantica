# Design: 营销/经营数据清洗与建模

入口 `datasets/process_marketing_data.py`。原始 CSV 只读（`dataReport/dataset/_semantic/` 除外）。产物 `datasets/processed/marketing_2026H1/`。  
本体依据 [ontology.md](./ontology.md)，场景依据 [scenarios.md](./scenarios.md)，决策 [decisions.md](./decisions.md)。

## 流水线

```
dataReport/dataset/ 10 张 CSV（只读）
        │
        ├─ fill_sales_dept ──(工号去重 B9)──→ emp_dim（fdept_add 对齐 B5）
        │        └─ v_sales_emp_info（458=458 对照）
        │        └─ bi_vpsempinfo_month（仅血缘，PII 不入产物 D3）
        │
        ├─ fill_dept_budget 去重组合 ──→ dept_dim（+ area/area_fq）
        ├─ ods_sap_cw_product（527）──→ product_dim
        ├─ KunnrCode ∪ fcust_number ──→ customer_dim（角色标注）
        │
        ├─ dw_sgning_wide_table ──→ sign_order_line
        │        （去重；元+万元；回填 zprod_type / fdept / org_scope）
        ├─ dw_sale_order_saptest ──→ ship_order_line
        │        （保留 ftag='预算数据' 30 行；同上回填）
        │
        ├─ fill_dept_budget ──→ dept_budget_month（万元，18 行空 Fdept 保留）
        └─ fill_product_budget ──→ product_budget_month（万元）
                        │
        ┌───────────────┴───────────────┐
        │  parquet + dq_report.json     │  model_star.json（星型描述）
        └───────────────┬───────────────┘
                        ▼
        build_marketing_graph.py → marketing_cleaned_semantics.json + marketing_ontology.ttl
```

## 两张预算表不通连（B10）

```
fill_dept_budget  ──┐
                    ├─ ✗ 无连接键 ✗ ──  同一笔预算的两个投影，合计差 ≤1.26 万元
fill_product_budget ┘
```

`dept_budget_month` 与 `product_budget_month` 在物理与逻辑上都不建边；一次查询只走一条投影。

## 粒度

| 表 | 何时丢行 | 何时留行 |
|---|---|---|
| `emp_dim` | PII 列；同一工号的重复行（取「在职」，B9） | 455 个工号全量 |
| `dept_dim` / `product_dim` / `customer_dim` | 全列去重 | 维度快照全量 |
| `sign_order_line` | 完全重复行 | 负金额（退货/退补）保留；未登记机型保留（机型置空） |
| `ship_order_line` | 完全重复行；出货视图 `ftag='预算数据'` | 底层发货表 `ftag='预算数据'` 保留（保底预算字段） |
| `dept_budget_month` | 全列去重 | 18 行 `Fdept` 空保留（其他部门代卖），进 dq |
| `product_budget_month` | 全列去重 | 万元原值，不 ×10000 |

## 单位

- 宽表：`*_hs` 含税、`*_fc` 不含税，单位**元**；另写 `*_hs_wan = *_hs / 10000`（万元）。
- 预算表：`*_hs` 单位**万元**（含税），保持原值。
- 达成率：`Σ宽表 *_hs_wan / Σ预算 *_hs`，且分子满足四要素（见下）。

## 达成率四要素（B6/B7/B8 + B3）

| # | 要素 | 过滤 | 漏掉的后果 |
|---|---|---|---|
| 1 | 组织 | `org_scope = 'in_scope'`（Orgname 属装备一） | 228.6% |
| 2 | 机型 | `zprod_type ∈ 预算覆盖 6 类` | 148.2% |
| 3 | 科室 | `fdept` 非空 | 103.3% |
| 4 | 单位 | 分子 `/10000` 后与万元预算相除 | 差 10⁴ 倍 |

四要素全满足 → 考核出机 **130.6%**、管理出机 **91.1%**、管理签单 **103.2%**（H1 实算）。

**事实基座**：`sign_order_line` / `ship_order_line` 以**底层事件表**（`dw_sgning_wide_table` 7,558 / `dw_sale_order_saptest` 8,036）为基座，组织字段自 `v_sales_emp_info` 按工号回填 —— 等价于宽表投影，但保留了 D1 要求留存的 `ftag='预算数据'` 保底预算行（30 行）。与宽表基座在默认口径下差异 <1%（详见 [metrics.md](./metrics.md) 基座差异注）。

## 清洗规则

1. 日期标准化 `YYYY-MM-DD`；空值统一（`NULL`/`"NULL"`/空串 → 空）。
2. 金额列保留 2 位小数；数量列保留 3 位小数。
3. 科室键：以 `fdept_add` 对齐；`fdept` 仅作对照，值域冲突（92 行）记 dq。
4. 同工号多名：维度取规范行（在职优先），聚合层 `GROUP BY SalesCode` + `MAX(姓名)`。
5. 期间：签单 `Fyear/Fmonth`、出货 `fyear/fperiod`；**禁止**用 `BusinessDate`/`SalesDocnoDate` 反推（会漏 30 行 / 错 0.37%）。
6. 机型：以 `ZPROD_NAME` 为准；`FmateNumber`（物料编码，1906 个）**不是**机型，降为属性。
7. 空键：任何以空串为键的对照不成立；未归属行进 dq 保留。
8. 负金额：保留（退货/退补），dq 计数而非剔除。

## 星型模型（逻辑层）

```
                    month_dim
                        │
   emp_dim ──┐          │        ┌── dept_dim ──→ area ──→ business_group
             │          │        │
             ▼          ▼        ▼
      ┌─────────────────────────────────┐
      │  sign_order_line / ship_order_line │
      └─────────────────────────────────┘
             ▲          ▲        ▲
             │          │        │
   customer_dim    product_dim ──→ product_type
                                      
   ── 预算星（独立，不 join）──
   dept_budget_month(dept, month)     product_budget_month(product_type, month)
```

`Plan ⊥ BusinessEvent`（公理 A5）：预算星与事实星只在**查询层**按 `(dept, month)` 或 `(product_type, month)` 对照，物理上不通连。

## 非目标

不生成达成率报告 / 名单 / 模型；不连内网查库；不把 EHR 月表单独建模；不产出 `label`/`y`/`split` 列；不把主管/工厂/系列建为节点。
