# Change: 营销/经营数据处理（清洗 + 建模）

状态：`proposed`（第一轮 B1–B5、D1–D6；第二轮 B6–B10、D7–D8 已按推荐默认执行并已实跑）。真源 [decisions.md](./decisions.md)，规格 [specs/marketing-data-processing/spec.md](./specs/marketing-data-processing/spec.md)，任务 [tasks.md](./tasks.md)。

**本体论语义分析**：[ontology.md](./ontology.md)（存在论盘点 → 语义消歧 → 关系识别 → 公理 → 实采证伪 → 能力问题验收）。  
**数据场景语义解读**：[scenarios.md](./scenarios.md)（8 个场景 + 不要问清单）。

对应设备数据同一步：**iot-data-processing**（理解数据 / 理解业务 / 清洗与预处理）。  
本 change 范围只覆盖「理解营销口径 / 清洗与单位统一 / 事实-维度建模」。不做达成率报告、不做模型。

## Why

设备数据已按「让数据纯 / 宁肯错杀」完成清洗与建模。营销/经营数据（`dataReport/dataset/`，SQL Server `csj_dw.dbo` 导出的 10 张 CSV，口径 2026 H1）存在同类问题，不能直接进分析：

- **金额单位混用**：宽表金额是**元**，两张预算表是**万元**，混算达成率必错。
- **身份键漂移**：组织视图只暴露 `Fdept_add`，预算表键是 `Fdept`，文档 DDL 却写 `dept.Fdept`。
- **占位行**：出货视图混入 `ftag='预算数据'` 占位行（金额 0、明细全空）；底层发货表却要保留（含保底预算字段）。
- **重复行**：发货表 45 行、出货视图 51 行完全重复。
- **PII**：EHR 月表含身份证号、手机号、出生日期。

## What Changes

字段级定义见 [schemas.md](./schemas.md)，对照 `dataReport/数据表与视图.md` 三视图 DDL 与 `csj_dw表关联ER.md`。  
身份键：`SalesCode`（业务员工号）、`Fdept`（科室，组织侧落 `Fdept_add`）、`ZPROD_NAME`/`ZPROD_TYPE`（机型/产品类型）、`Fyear/Fmonth`（年月）。  
金额键锁定：`TotalMoneyFc_HS`（签单含税）、`TotalMoneyFC_HS`（出货含税），均**元**；预算表 `*_Hs` 均**万元**。

| 表 | 粒度 | 主键 | 来源 CSV | 角色 |
|---|---|---|---|---|
| `emp_dim` | 业务员 | `sales_code` | `fill_sales_dept` / `v_sales_emp_info` | 维度 |
| `dept_dim` | 科室 | `fdept` | `fill_dept_budget` / `fill_sales_dept` | 维度 |
| `product_dim` | 机型/产品类型 | `zprod_name` | `ods_sap_cw_product` | 维度 |
| `sign_order_line` | 签单行 | `docno`（+行号） | `dw_sgning_wide_table` / `v_sales_order_product` | 事实 |
| `ship_order_line` | 出货行 | `docno`（+行号） | `dw_sale_order_saptest` / `v_sale_ship_order_emp_product` | 事实 |
| `dept_budget_month` | 科室 × 月 | `fdept, fyear, fmonth` | `fill_dept_budget` | 预算 |
| `product_budget_month` | 产品类型 × 月 | `product_type, fyear, fmonth` | `fill_product_budget` | 预算 |
| `dq_report` | 规则 | `rule_id` | — | 丢弃审计 |

处理原则：

1. **单位统一万元**（B3 `wan`）：明细列保留元 + 万元列；达成口径一律万元（`SUM(宽表金额)/10000`）。
2. **达成口径**（B4 `fdept_all`）：按 `Fdept` 全量、不过滤 `User_role`；连续不签单/未出机才 `User_role='业务'` 且按 `SalesCode` 聚合、姓名取 `MAX`。
3. **科室键**（B5 `fdept_add`）：组织侧以 `Fdept_add` 对齐，宽表 `Fdept` 回填自 `Fdept_add`，禁止两列混用。
4. **占位行**（D1）：发货表保留 `ftag='预算数据'`（保底预算字段）；出货视图剔除同 `ftag` 行（金额 0）。
5. **去重**（D2）：完全重复行去重；其余全列去重。
6. **PII**（D3）：`idcardnum`/`mobilephone`/`birthday` 不进分析产物。
7. **日期标准化**：`SalesDocnoDate/BusinessDate/entrydate/birthday/dimissiondate/Sales_Employment_Date` 统一 `YYYY-MM-DD`。
8. **空值统一**：`NULL`、字符串 `"NULL"`、空串统一为空。

## 已理解的数据（Grill 前冻结的事实）

来源：`dataReport/dataset/` 10 张 CSV，口径 2026-01~06。

| 对象 | 行数 | 角色 |
|---|---|---|
| `fill_sales_dept` | 458 | 业务员部门架构（快照，含 `Fdept_add`+`Fdept`） |
| `v_sales_emp_info` | 458 | 组织视图（只含 `Fdept_add`） |
| `bi_vpsempinfo_month` | 72,755 | EHR 月表（含 PII，只作血缘） |
| `dw_sgning_wide_table` | 7,558 | 签单明细（Fyear/Fmonth） |
| `dw_sale_order_saptest` | 8,036 | 发货数据（fyear/fperiod；去重前 8,081） |
| `ods_sap_cw_product` | 527 | 机型所属分类（ZPROD_NAME → ZPROD_TYPE） |
| `v_sales_order_product` | 7,563 | 签单宽表（元） |
| `v_sale_ship_order_emp_product` | 7,988 | 出货宽表（元；去重前 8,064） |
| `fill_dept_budget` | 234 | 科室月度预算（万元） |
| `fill_product_budget` | 36 | 产品类型月度预算（万元） |

指标映射（真源 `dataReport/数据表与视图.md` 第五节）：

| 业务说法 | 实际（宽表，元） | 预算（科室，万元，含税） |
|---|---|---|
| 管理出机 | 出货 `TotalMoneyFC_HS` | `Management_Ship_Budget_Hs` |
| 考核出机 | 出货 `TotalMoneyFC_HS` | `Assessment_Ship_Budget_Hs` |
| 管理签单 | 签单 `TotalMoneyFc_HS` | `Management_SignedContract_Hs` |

## Non-goals

- 不在本 change 生成达成率报告、连续不签单名单、机型达成分析（那是分析/报告层）。
- 不连内网 `192.168.10.209:1433` 实时查库（输入是已导出的 CSV）。
- 不修改 `dataReport/dataset/` 原始 CSV。
- 不把 6 个底层/中间对象单独建模成图节点（D6 `dims_only`）。
- 不在本 change 接 LLM / Dify / NL→SPARQL（后续 change）。

## 实采后追加的五个阻塞项（第二轮 Grill，见 [grill.md](./grill.md)）

文档与第一轮都没问到，但直接决定达成率差 2.5 倍。证据见 [ontology.md §5](./ontology.md)：

| 题 | 发现 | 若不管的后果 |
|---|---|---|
| B6 组织口径 | 预算 234/234 是装备一，宽表混 8 个组织 | 228.6% |
| B7 机型覆盖 | 预算只覆盖 6/22 个产品类型，漏掉 12.1 亿的 3C钻攻机 | 148.2% |
| B8 空键伪命中 | 出货 1163/8036 行无科室；朴素 isin 会报 100% 命中 | 103.3% |
| B9 工号不唯一 | 458 行 / 455 工号，3 个工号在职+离职各一行 | join 后业绩翻倍 |
| B10 预算同源 | 两张预算表三指标合计差 ≤1.26 万元 = 同一笔钱的两个投影 | 相加则预算翻倍 |

默认口径下 H1 实算：考核出机 **130.6%**、管理出机 **91.1%**、管理签单 **103.2%**（详见 [metrics.md](./metrics.md)）。

## Impact

- 新增：`openspec/changes/marketing-data-processing/` 规格 + `datasets/process_marketing_data.py`。
- 输出：`datasets/processed/marketing_2026H1/*.parquet` + `dq_report.json` + `model_star.json`。
- 读取：`dataReport/dataset/*.csv`。

## 退出条件

Grill-Me 闭环（[decisions.md](./decisions.md) 确认）且 [tasks.md](./tasks.md) 全部勾选后关闭本 change。  
图建模与 GraphRAG 为独立 change [marketing-graphrag](../marketing-graphrag/proposal.md)。
