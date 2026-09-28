# Spec: 营销/经营数据处理

状态：`proposed`（第一轮 B1–B5、D1–D6；第二轮 B6–B10、D7–D8 已按推荐默认执行）。见 [../../decisions.md](../../decisions.md)。列定义见 [../../schemas.md](../../schemas.md)。  
本体分析见 [../../ontology.md](../../ontology.md)（实采证伪过程），场景解读见 [../../scenarios.md](../../scenarios.md)。

## ADDED Requirements

### Requirement: 清洗输入集

系统 SHALL 以 `dataReport/dataset/` 的 10 张 CSV 为输入（SQL Server `csj_dw.dbo` 导出，口径 2026-01~06）。  
系统 SHALL NOT 连内网 `192.168.10.209:1433` 实时查库。  
系统 SHALL NOT 修改原始 CSV。

#### Scenario: 十张 CSV 全量读入

- **WHEN** `dataReport/dataset/` 存在 10 张 CSV
- **THEN** 每张按其对象规则清洗，写出对应产物

### Requirement: 混合粒度产物

系统 SHALL 输出（B2、D4）：

- `emp_dim`
- `dept_dim`
- `product_dim`
- `sign_order_line`
- `ship_order_line`
- `dept_budget_month`
- `product_budget_month`
- `dq_report.json`

路径：`datasets/processed/marketing_2026H1/`。表为 parquet（`dq_report` 为 JSON）。

#### Scenario: 事实与维度分离

- **WHEN** 签单/出货行与业务员/科室/产品分类各自成表
- **THEN** 事实表含身份键，维度表独立，无标签列

### Requirement: 金额单位统一

系统 SHALL 统一金额到万元（B3 `wan`）：宽表金额保留元列并派生 `/10000` 万元列；预算表单位为万元（含税）保持原值。  
系统 SHALL NOT 把宽表元与预算万元直接相除。

#### Scenario: 达成率单位一致

- **WHEN** 计算达成率
- **THEN** 分子为 `Σ宽表 *_hs / 10000`（万元），分母为预算 `*_hs`（万元）

### Requirement: 达成口径

系统 SHALL 达成类按 `Fdept` 全量、不过滤 `User_role`（B4）。  
系统 SHALL 连续不签单/未出机才 `User_role='业务'`，按 `SalesCode` 聚合、姓名取 `MAX`。

#### Scenario: 达成不过滤领导

- **WHEN** 统计某科室管理出机达成
- **THEN** 不因行 `User_role != '业务'` 而剔除

#### Scenario: 行为类过滤业务

- **WHEN** 统计连续不签单人数
- **THEN** 仅 `User_role='业务'`，按 `SalesCode` 聚合

### Requirement: 科室对齐键

系统 SHALL 以 `Fdept_add` 作为组织 → 预算对齐键（B5）。  
系统 SHALL 宽表 `Fdept` 回填自 `Fdept_add`；`Fdept` 与 `Fdept_add` 值域冲突 SHALL 记入 `dq_report`，SHALL NOT 静默二选一。

#### Scenario: 组织视图只有 Fdept_add

- **WHEN** `v_sales_emp_info` 仅含 `Fdept_add`
- **THEN** 对齐键取 `Fdept_add`，不回填 `Fdept`

### Requirement: 占位行与去重

系统 SHALL 底层发货表保留 `ftag='预算数据'` 行（含保底预算字段），出货视图剔除同 `ftag` 行（D1）。  
系统 SHALL 对完全重复行去重，其余按全列去重（D2）。

#### Scenario: 出货视图剔除占位

- **WHEN** `v_sale_ship_order_emp_product` 行 `ftag='预算数据'` 且金额为 0
- **THEN** 该行不进入 `ship_order_line`

#### Scenario: 发货表保留保底预算

- **WHEN** `dw_sale_order_saptest` 行 `ftag='预算数据'` 含 `fbudget_*` 字段
- **THEN** 该行保留

### Requirement: PII

系统 SHALL NOT 把 `idcardnum`、`mobilephone`、`birthday` 写入任何分析产物（D3）。  
`bi_vpsempinfo_month` SHALL 只作 EHR 血缘，SHALL NOT 单独建模。

#### Scenario: EHR 月表不进分析层

- **WHEN** 读入 `bi_vpsempinfo_month_2026H1`
- **THEN** 其 PII 列不进入任何 parquet

### Requirement: 日期与空值

系统 SHALL 将 `SalesDocnoDate/BusinessDate/entrydate/birthday/dimissiondate/Sales_Employment_Date` 标准化为 `YYYY-MM-DD`。  
系统 SHALL 将 `NULL`、字符串 `"NULL"`、空串统一为空。

### Requirement: 本步不造分析结论

系统 SHALL NOT 在本 change 生成达成率报告、连续不签单名单、机型达成分析（B1）。  
系统 SHALL NOT 输出 `label`/`y`/`split` 列。  
系统 SHALL 写出 `dataReport/dataset/_semantic/metric_catalog.json`（度量目录，见 [metrics.md](../../metrics.md)）。

### Requirement: 组织边界（B6）

系统 SHALL 在两张事实表上写出 `org_scope` 列，取值 `in_scope`（`Orgname` 属装备一）/ `out_of_scope` / `unknown`（`Orgname` 空）。  
系统 SHALL NOT 在达成类口径中计入 `out_of_scope` 行；非装备一的行 SHALL 保留在事实表中供其他场景使用。

#### Scenario: 预算只覆盖装备一

- **WHEN** 计算达成率
- **THEN** 分子仅取 `org_scope='in_scope'`；不限定则得 228.6%

### Requirement: 机型覆盖（B7）

系统 SHALL 在达成类口径中限定 `zprod_type ∈ fill_product_budget.ProductType`（实采 6 类）。  
未覆盖类型（如实采 12.1 亿元的 3C钻攻机）SHALL 排除在达成分子之外，SHALL 在结构份额场景中保留。

#### Scenario: 3C 不在产品预算内

- **WHEN** 按产品类型对照预算
- **THEN** 3C钻攻机的对照为 0，并说明其预算挂在 `SalesDept='3C销售部'`（`Fdept` 空）

### Requirement: 空键不对照（B8）

系统 SHALL NOT 使用空串作为任何对照键。  
未归属科室的行 SHALL 保留在事实表并计入 `dq_report.unassigned_rows`。

#### Scenario: 空串不互配

- **WHEN** 检查预算 `Fdept` 与事实 `fdept` 的覆盖率
- **THEN** 先剔除空键再比对；不得因「空 ∈ 空集合」报 100% 命中

### Requirement: 工号唯一化（B9）

系统 SHALL 将 `emp_dim` 以 `sales_code` 唯一化（458 → 455）。  
同一工号多行时 SHALL 优先取 `employment_status='在职'`；冲突 SHALL 计入 `dq_report.duplicate_sales_code`。

#### Scenario: 在职优先

- **WHEN** `fill_sales_dept` 中同一 `SalesCode` 同时存在在职与离职行
- **THEN** `emp_dim` 保留在职行，避免与事实表 join 时业绩翻倍

### Requirement: 预算两投影互斥（B10）

系统 SHALL NOT 在 `dept_budget_month` 与 `product_budget_month` 之间建立任何连接或相加。  
一次查询 SHALL 只走一条预算投影。

#### Scenario: 不交叉

- **WHEN** 需要「科室 × 产品类型」的预算
- **THEN** 系统拒绝并说明分配矩阵未导出

### Requirement: 负金额与组织边界标记

系统 SHALL 保留负金额行（退货/退补为有效发生体，D7）并在 `dq_report.negative_amount_rows` 计数。  
系统 SHALL 写出 `org_scope` 标记列（D8）。

### Requirement: 底层对象不单独建模

系统 SHALL NOT 将 6 个底层/中间对象（`dw_sgning_wide_table`、`dw_sale_order_saptest`、`bi_vpsempinfo_month`、`fill_sales_dept`、`v_sales_emp_info`、`ods_sap_cw_product`）单独建模成图节点（D6）。  
图节点 SHALL 由 4 个允许查询对象（两宽表 + 两预算表）+ 维度实体（业务员/科室/客户/产品类型/区域/机型/月）构成。
