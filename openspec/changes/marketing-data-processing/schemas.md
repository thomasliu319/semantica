# 营销/经营数据拟议产物字段

对照 `dataReport/数据表与视图.md` 三视图 DDL、`csj_dw表关联ER.md` 与 `dataset/README.md` 清洗规则。  
实采 CSV 多出来的列标「实采」；文档写了但语义不能当 H1 事实的标「禁止误用」。

## 身份键（全文统一，禁止改名）

| 字段 | 含义 | 不是 |
|---|---|---|
| `SalesCode` | 业务员工号 | 姓名 |
| `Fdept` / `Fdept_add` | 科室（组织侧落 `Fdept_add`） | 区名 / 小区名 |
| `ZPROD_NAME` | 机型/物料类型（`= fmate_type`/`FmateType`） | 产品类型 |
| `ZPROD_TYPE` | 产品类型（预算对照键） | 机型名 |
| `KunnrCode` / `fcust_number` | 客户编码 | 客户名 |
| `Fyear`/`Fmonth` | 签单年月 | 出货 `fyear`/`fperiod` |
| `Docno` / `DocNo` | 单据号 | 合同名 |

主键默认：`SalesCode`（人员）、`Fdept`（科室）、`ZPROD_NAME`（产品）。科室对齐键锁定 `Fdept_add`（B5）。

## 状态词（禁止混用）

| 业务说法 | 实际 | 语义陷阱 |
|---|---|---|
| 管理出机 | 出货 `TotalMoneyFC_HS`（元） | 与考核出机同字段，只有预算列不同 |
| 考核出机 | 出货 `TotalMoneyFC_HS`（元） | 同上 |
| 管理签单 | 签单 `TotalMoneyFc_HS`（元） | 不是 `TotalMoneyFc`（不含税） |
| 达成率 | `实际(万元) / 预算(万元)` | 宽表必须先 /10000 |
| 连续不签单/未出机 | 仅 `User_role='业务'`，按 `SalesCode` 聚合 | 达成类不过滤 `User_role` |

金额单位：宽表**元**，预算**万元**（含税）。比较前 `SUM(宽表金额)/10000`。

## 表一览

| 表 | 粒度 | 主键 | 来源 | 角色 |
|---|---|---|---|---|
| `emp_dim` | 业务员 | `sales_code` | `fill_sales_dept` / `v_sales_emp_info` | 维度 |
| `dept_dim` | 科室 | `fdept` | `fill_dept_budget` / `fill_sales_dept` | 维度 |
| `product_dim` | 机型/产品类型 | `zprod_name` | `ods_sap_cw_product` | 维度 |
| `customer_dim` | 客户 | `cust_code` | `KunnrCode` ∪ `fcust_number` | 维度 |
| `month_dim` | 自然月 | `year, month` | `Fyear/Fmonth` ∪ `fyear/fperiod` | 维度 |
| `sign_order_line` | 签单行 | `docno` + `docno_num` | `dw_sgning_wide_table` / `v_sales_order_product` | 事实 |
| `ship_order_line` | 出货行 | `docno` + 行号 | `dw_sale_order_saptest` / `v_sale_ship_order_emp_product` | 事实 |
| `dept_budget_month` | 科室 × 月 | `fdept, fyear, fmonth` | `fill_dept_budget` | 预算（Plan） |
| `product_budget_month` | 产品类型 × 月 | `product_type, fyear, fmonth` | `fill_product_budget` | 预算（Plan） |
| `dq_report` | 规则 | `rule_id` | — | 丢弃审计 |

第二轮新增列（[decisions.md](./decisions.md) B6–B10、D7–D8）：

| 列 | 落表 | 取值 | 依据 |
|---|---|---|---|
| `org_scope` | 两张事实表 | `in_scope` / `out_of_scope` / `unknown` | B6 + D8 |
| `model_unregistered` | 两张事实表 | `0`/`1`（`fmate_type ∉ ZPROD_NAME`） | ontology §2.2 |
| `cust_code` / `cust_role` | 两张事实表 + `customer_dim` | 编码 / `contract_party`·`ship_to`·`both` | ontology §2.3 |
| `total_money_fc_hs_wan` | 两张事实表 | `*_hs / 10000` | B3 |
| `year` / `month` | 两张事实表 | 签单 `Fyear/Fmonth`；出货 `fyear/fperiod` | 公理 A8 |

---

## `emp_dim`（业务员）

源：`fill_sales_dept`（快照，全量）。同 `v_sales_emp_info` 行一一对应（458）。

| 清洗列 | 源字段 | 规则 |
|---|---|---|
| `sales_code` | SalesCode | 主键 |
| `sales_name` | SalesName | 同工号多名取 `MAX` 在聚合层，维度保留原文 |
| `forg_name` | ForgName | 组织 |
| `sales_dept` | SalesDept | 销售部 |
| `area` | Area | 大区 |
| `fdept_add` | Fdept_add | 科室对齐键（B5） |
| `fdept` | Fdept | 与 `fdept_add` 值域一致时保留作对照；冲突记 dq |
| `supervisor_name` | SupervisorName | 主管 |
| `province` | Province | 省 |
| `affiliation_city` | AffiliationCity | 归属城市 |
| `employment_status` | EmploymentStatus | 在职/离职/异动（实采 415/42/1） |
| `user_role` | User_role | 业务/管理领导（实采 447/11） |
| `sales_employment_date` | Sales_Employment_Date | 入职日期，`YYYY-MM-DD` |

不进本表：EHR 月表的 PII（`idcardnum`/`mobilephone`/`birthday`）。

**工号唯一化（B9 `prefer_active`）**：源 458 行 / 455 工号。`C13437`、`C13480`、`C15083` 各有 2 行（在职 + 离职各一，其余字段相同）。取「在职」行；全离职取首行；冲突进 `dq_report.duplicate_sales_code`。

## `customer_dim`（客户）

源：签单 `KunnrCode`（4,149）∪ 出货 `fcust_number`（3,896），交集 3,800。

| 清洗列 | 源字段 | 规则 |
|---|---|---|
| `cust_code` | `KunnrCode` / `fcust_number` | 主键（并集） |
| `cust_name` | `fcust_name` | 出货侧名称 |
| `cust_area` | `fcust_area` | 客户所在地（7 值），**不是**销售大区 |
| `cust_role` | 来源 | `contract_party` / `ship_to` / `both` |

## `month_dim`（自然月）

源：签单 `Fyear/Fmonth` ∪ 出货 `fyear/fperiod`，2026-01~06 共 6 个月。

| 清洗列 | 源字段 | 规则 |
|---|---|---|
| `year` / `month` | `Fyear`/`Fmonth`、`fyear`/`fperiod` | 主键；**禁止**由日期列反推（公理 A8） |
| `month_label` | 派生 | `2026-01` … `2026-06` |

## `dept_dim`（科室）

源：`fill_dept_budget` 去重后的 `OrgName/ProductDept/SalesDept/Area/Area_fq/Fdept` 组合 + `fill_sales_dept` 的组织层级。

| 清洗列 | 源字段 | 规则 |
|---|---|---|
| `fdept` | Fdept | 主键（对齐 `emp_dim.fdept_add`） |
| `org_name` | OrgName | 事业群 |
| `product_dept` | ProductDept | 产品部 |
| `sales_dept` | SalesDept | 销售部 |
| `area` / `area_fq` | Area / Area_fq | 大区 / 大区分区 |

## `product_dim`（机型/产品类型）

源：`ods_sap_cw_product`（527 行，`ZPROD_NAME → ZPROD_TYPE`）。

| 清洗列 | 源字段 | 规则 |
|---|---|---|
| `zprod_name` | ZPROD_NAME | 主键；`= fmate_type` / `FmateType` |
| `zprod_type` | ZPROD_TYPE | 产品类型；预算对照键 |

---

## `sign_order_line`（签单行）

源：`dw_sgning_wide_table`（去重后 7,558）为主；`v_sales_order_product`（7,563）为对照（FULL OUTER 后 GROUP BY，行数略多）。

| 清洗列 | 源字段 | 规则 |
|---|---|---|
| `docno` | Docno | 单据号（+ 行号为主键） |
| `docno_num` | DocnoNum | 单据编号 |
| `contract_name` | ContractName | 合同名 |
| `kunnr_code` | KunnrCode | 客户编码 |
| `sales_code` | SalesCode | 业务员工号（`COALESCE(emp, ord)`） |
| `sales_name` | SalesName | 业务员姓名 |
| `org_name` | Orgname | 组织 |
| `fdept` | Fdept（回填自 `fdept_add`） | 科室 |
| `fmate_number` | FmateNumber | 机型编号 |
| `fmate_seris` | FmateSeris | 机型系列 |
| `fmate_type` | FmateType | 机型类型（`= ZPROD_NAME`） |
| `zprod_name` / `zprod_type` | ZPROD_NAME / ZPROD_TYPE | 回填产品分类 |
| `fyear` / `fmonth` | Fyear / Fmonth | 年月（时间口径） |
| `sales_docno_date` | SalesDocnoDate | 单据日期，`YYYY-MM-DD` |
| `fqty` | Fqty | 数量 |
| `total_money_fc` | TotalMoneyFc | 不含税签单，元 |
| `total_money_fc_hs` | TotalMoneyFc_HS | **含税签单，元**（管理签单指标） |
| `total_money_fc_hs_wan` | `/10000` | 万元 |

## `ship_order_line`（出货行）

源：`dw_sale_order_saptest`（去重后 8,036）为主；`v_sale_ship_order_emp_product`（7,988）为对照。

| 清洗列 | 源字段 | 规则 |
|---|---|---|
| `docno` | DocNo | 出货单号（+ 行号为主键） |
| `ftag` | ftag | 占位标记；`预算数据` 行在底层保留 |
| `sales_code` | fsales_number | 业务员工号 |
| `sales_name` | fsales_name | 业务员姓名 |
| `fdept` | fdept / 回填 | 科室 |
| `org_name` | Orgname | 组织 |
| `fcust_number` / `fcust_name` | fcust_number / fcust_name | 客户 |
| `fmate_number` / `fmate_name` / `fmate_type` | fmate_* | 机型（`fmate_type = ZPROD_NAME`） |
| `zprod_name` / `zprod_type` | 回填 | 产品分类 |
| `fyear` / `fperiod` | fyear / fperiod | 期间（时间口径） |
| `business_date` | BusinessDate | 业务日期，`YYYY-MM-DD` |
| `fqty` | FQTY | 数量 |
| `total_money_fc` | TotalMoneyFC | 不含税出货，元 |
| `total_money_fc_hs` | TotalMoneyFC_HS | **含税出货，元**（管理/考核出机指标） |
| `total_money_fc_hs_wan` | `/10000` | 万元 |

---

## `dept_budget_month`（科室月度预算）

源：`fill_dept_budget_2026H1`（234 行）。单位**万元**（含税）。

| 清洗列 | 源字段 | 规则 |
|---|---|---|
| `fdept` | Fdept | 主键之一（对齐 `emp_dim.fdept_add`） |
| `fyear` / `fmonth` | Fyear / Fmonth | 主键之一 |
| `org_name` / `product_dept` / `sales_dept` | OrgName / ProductDept / SalesDept | 组织 |
| `area` / `area_fq` | Area / Area_fq | 区域 |
| `management_ship_budget_hs` | Management_Ship_Budget_Hs | 管理出机预算，万元含税 |
| `assessment_ship_budget_hs` | Assessment_Ship_Budget_Hs | 考核出机预算，万元含税 |
| `management_signed_contract_hs` | Management_SignedContract_Hs | 管理签单预算，万元含税 |

含 `Lj_*`/`GL_*` 累计列按原文保留，不参与本 change 达成口径。

## `product_budget_month`（产品类型月度预算）

源：`fill_product_budget_2026H1`（36 行）。单位**万元**（含税）。

| 清洗列 | 源字段 | 规则 |
|---|---|---|
| `product_type` | ProductType | 主键之一（对齐 `product_dim.zprod_type`） |
| `fyear` / `fmonth` | Fyear / Fmonth | 主键之一 |
| `org_name` / `product_name` | OrgName / ProductName | 组织 / 产品线 |
| `management_ship_budget_hs` | Management_Ship_Budget_Hs | 管理出机预算 |
| `assessment_ship_budget_hs` | Assessment_Ship_Budget_Hs | 考核出机预算 |
| `gl_management_signed_contract_hs` | GL_Management_SignedContract_Hs | 管理签单预算 |

---

## `dq_report`

每条规则：`rule_id, table, count, example_keys, note`。  
至少覆盖：单位不一致（元 vs 万元）、`Fdept` 与 `Fdept_add` 值域冲突、`ftag='预算数据'` 剔除行数、完全重复行去重数、PII 剔除、日期非标准格式、EHR 血缘表未建模。
