# Tasks: 营销/经营数据处理（清洗 + 建模）

实现 [spec.md](./specs/marketing-data-processing/spec.md)，列对照 [schemas.md](./schemas.md)，度量对照 [metrics.md](./metrics.md)。  
本体分析见 [ontology.md](./ontology.md)，场景解读见 [scenarios.md](./scenarios.md)。  
设计见 [design.md](./design.md)。入口 `datasets/process_marketing_data.py`，输出 `datasets/processed/marketing_2026H1/`。  
图建模与 GraphRAG 见 [../marketing-graphrag/tasks.md](../marketing-graphrag/tasks.md)。

图例：`[ ]` 待办 · `[x]` 完成。勾选状态以实跑为准。

## 卡片 1｜输入与队列

- [x] 1.1 读入 `dataReport/dataset/` 10 张 CSV（`utf-8-sig` 去 BOM，全列按字符串读）
- [x] 1.2 建对象 → 产物映射（4 允许查询对象 + 6 底层/中间对象）
- [x] 1.3 `bi_vpsempinfo_month` 只作血缘，不进任何 parquet（D3）
- [x] 1.4 原始 CSV 只读；`_semantic/` 除外（D4）

## 卡片 2｜维度表

- [x] 2.1 `emp_dim.parquet`：`sales_code` 唯一化，458 → 455 行（B9 `prefer_active`）
- [x] 2.2 `emp_dim` 含 `user_role`、`employment_status`（场景 2 分层依赖）；不含 PII（D3）
- [x] 2.3 `emp_dim.fdept_add` 为科室对齐键（B5）；`fdept` 保留作对照，冲突计 dq
- [x] 2.4 `dept_dim.parquet`：`fdept` 主键；含 `org_name`/`sales_dept`/`area`/`area_fq`
- [x] 2.5 `product_dim.parquet`：`zprod_name → zprod_type`，527 行（公理 A6 函数性）
- [x] 2.6 `customer_dim.parquet`：签单 `KunnrCode` ∪ 出货 `fcust_number` 并集键
- [x] 2.7 `customer_dim` 标注角色来源（`contract_party` / `ship_to` / `both`）

## 卡片 3｜事实表

- [x] 3.1 `sign_order_line.parquet`（`dw_sgning_wide_table` 7,558 行；`docno`+`docno_num` 主键）
- [x] 3.2 `ship_order_line.parquet`（`dw_sale_order_saptest` 8,036 行；保留 `ftag='预算数据'` 30 行，D1）
- [x] 3.3 出货视图 `v_sale_ship_order_emp_product` 剔除 `ftag='预算数据'`（D1，实采已剔除）+ 完全重复行（D2）
- [x] 3.4 金额派生：`*_hs_wan = *_hs / 10000`（B3）；明细保留元列
- [x] 3.5 回填 `zprod_name`/`zprod_type`（`fmate_type = ZPROD_NAME`）；未命中置空并标记 `model_unregistered`
- [x] 3.6 回填 `fdept`（自 `fdept_add`）；空键不参与对照（B8）
- [x] 3.7 新增 `org_scope` 列（`in_scope`/`out_of_scope`/`unknown`，B6/D8）
- [x] 3.8 日期标准化 `YYYY-MM-DD`；空值统一（`NULL`/`"NULL"`/空串 → 空）
- [x] 3.9 负金额保留（D7），dq 单列计数
- [x] 3.10 期间取 `Fyear/Fmonth`（签单）与 `fyear/fperiod`（出货），禁用日期反推（公理 A8）

## 卡片 4｜预算表

- [x] 4.1 `dept_budget_month.parquet`（234 行 = 39 组 × 6 月；万元含税不 ×10000，D5）
- [x] 4.2 `product_budget_month.parquet`（36 行 = 6 类型 × 6 月）
- [x] 4.3 两张预算表之间**不建任何连接**（B10 `mutually_exclusive`）
- [x] 4.4 18 行 `Fdept` 为空的预算行进 `dq_report.budget_rows_without_dept`，不丢弃

## 卡片 5｜数据质量报告

- [x] 5.1 `dq_report.json`：单位不一致、`Fdept` vs `Fdept_add` 冲突（92 行）、占位行剔除数、重复去重数、PII 剔除、日期异常
- [x] 5.2 `dq_report.unassigned_rows`：出货 1131 / 签单 800 行无科室（B8）
- [x] 5.3 `dq_report.unregistered_model_rows`：签单 20 / 出货 38 行机型未登记
- [x] 5.4 `dq_report.duplicate_sales_code`：3 个工号双行（B9）
- [x] 5.5 `dq_report.negative_amount_rows`：签单 264 / 出货 299
- [x] 5.6 `dq_report.budget_rows_without_dept`：18 行
- [x] 5.7 parquet 无 `label`/`y`/`split` 列（B1）
- [x] 5.8 `--out` 默认为 `datasets/processed/marketing_2026H1/`
- [x] 5.9 写 `dataReport/dataset/_semantic/metric_catalog.json`

## 卡片 6｜星型建模（逻辑模型）

- [x] 6.1 事实-维度星型：`sign_order_line` / `ship_order_line` 为中心，`emp_dim`/`dept_dim`/`product_dim`/`customer_dim`/`month_dim` 为维
- [x] 6.2 预算为独立星（`Plan`），与事实星**不 join**，仅在查询层按 `(dept, month)` / `(product_type, month)` 对照（公理 A5）
- [x] 6.3 组织层级 `BusinessGroup ← Area ← Dept ← SalesPerson` 显式建模（支持上卷）
- [x] 6.4 输出 `datasets/processed/marketing_2026H1/model_star.json`（星型模型描述，供 GraphRAG 读取）

## 卡片 7｜图建模（物理图）

- [x] 7.1 由清洗产物盖戳图节点：业务员 / 科室 / 大区 / 事业部 / 客户 / 机型 / 产品类型 / 月
- [x] 7.2 边：`belongsTo`、`partOf`、`categorizedAs`、`locatedIn`、`signedBy`/`shippedBy`、`ofModel`、`contractParty`/`shipTo`、`inMonth`、`measuredAgainst`
- [x] 7.3 **不建**节点：主管、工厂、系列、合同名、物料编码（[ontology.md §1.2](./ontology.md)）
- [x] 7.4 产出 `datasets/json/marketing_cleaned_semantics.json`（Explorer 可加载）
- [x] 7.5 产出 `datasets/json/marketing_ontology.ttl`（对照 `iot_ontology.ttl` 写法）
- [x] 7.6 详细任务与验收见 [../marketing-graphrag/tasks.md](../marketing-graphrag/tasks.md)

## 卡片 8｜测试

- [x] 8.1 `tests/datasets/test_process_marketing_data.py`：单位统一、`fdept_add` 对齐、占位行剔除、PII 剔除、无标签列
- [x] 8.2 `org_scope` 三值完备；`in_scope` 金额与预期一致
- [x] 8.3 `emp_dim` 工号唯一（455）；`product_dim` 527 行
- [x] 8.4 用 1–2 张夹具 CSV，不连内网
