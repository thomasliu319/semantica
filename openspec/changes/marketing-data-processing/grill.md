# Grill-Me：营销/经营数据处理需求拷问

OpenSpec 规则：B 组为阻塞题（理解业务，决定怎么杀），D 组可默认。每题只许选一个主选项；选「其他」必须补一句。  
本 change 与 [iot-data-processing](../iot-data-processing/) 同构：先理解数据与业务 → 再洗 → 再建模（事实表 + 维度表 + 预算对照），不跑分析。

导图锚点：业务场景（理解营销口径）→ 清洗预处理（让数据纯 / 单位统一 / 宁肯错杀）。

数据源事实（已冻结，见 [proposal.md](./proposal.md)）：`dataReport/dataset/` 10 张 CSV，来自 SQL Server `csj_dw.dbo`（`BI_AI@192.168.10.209:1433`），口径 2026-01~06。

---

## B. 阻塞题（理解业务，决定怎么杀）

### B1. 这一步之后，业务 Y 是什么？

营销数据已有明确业务问法（组织达成、连续不签单/未出机、机型出货），但清洗建模本身不定分析目标。

| 选项 | 含义 | 若选错 |
|---|---|---|
| `achieve_only` | 只支撑达成率（实际 vs 预算） | 连续不签单/未出机等行为问句会缺事实粒度 |
| `behavior_only` | 只支撑人员行为（连续不签单/未出机） | 预算对照表被丢弃，达成率算不了 |
| `full_bi` | 达成 + 行为 + 机型 + 客户 + 区域全维度 | 清洗门槛要靠业务，容易过度清洗 |
| `clean_only` | 本步不定 Y，只出干净事实表 + 维度表 | 只能用数据质量门槛，不能用「对分析有没有用」 |

推荐默认：`clean_only`（沿用设备数据：先让数据纯，特征/分析下一步）。

### B2. 分析原子粒度？

| 选项 | 对齐的接口 | 不适合 |
|---|---|---|
| `order_line` | 签单/出货行明细 | 达成率还要再聚合到科室 |
| `emp_month` | 业务员 × 月 | 预算在科室粒度，对不上 |
| `dept_month` | 科室 × 月（预算粒度） | 抹掉业务员个人行为 |
| `hybrid` | 事实行表 + 组织/预算维度 | 工作量最大，最不容易用错 |

推荐默认：`hybrid`（`sign_order_line` / `ship_order_line` 事实 + `emp_dim` / `dept_dim` / `product_dim` + `dept_budget_month` / `product_budget_month`）。

### B3. 金额单位统一到哪一层？

宽表金额是**元**，预算表是**万元**。混算必错。

| 选项 | 含义 | 若选错 |
|---|---|---|
| `wan` | 统一万元：宽表 /10000，预算原样 | 比较口径一致，明细保留元 |
| `yuan` | 统一元：预算 ×10000 | 浮点误差、数字变大易读错 |
| `both` | 元/万元双列都留 | 达成率取错列的风险 |

推荐默认：`wan`（明细列保留元 + 万元列；达成口径一律万元）。

### B4. 达成口径按 `User_role` 过滤吗？

| 选项 | 含义 |
|---|---|
| `fdept_all` | 达成类按 `Fdept` 全量、不过滤 `User_role`；连续不签单/未出机才 `User_role='业务'` |
| `business_only` | 所有场景仅 `User_role='业务'` |

推荐默认：`fdept_all`（领导/代卖科室的达成不能漏；行为类单列过滤）。

### B5. 科室对齐键用哪一列？

组织视图 `v_sales_emp_info` 只暴露 `Fdept_add`，预算表 `fill_dept_budget` 键是 `Fdept`，宽表里落的是 `Fdept`。文档 DDL 写 `dept.Fdept`，实际组织视图只有 `Fdept_add`。

| 选项 | 含义 |
|---|---|
| `fdept_add` | 以 `Fdept_add` 为组织 → 预算对齐键；宽表 `Fdept` 回填自 `Fdept_add` |
| `fdept` | 以 `Fdept` 为键；但组织视图没有该列，需先回填 |

推荐默认：`fdept_add`（值域一致的那列；写进 schemas 冻结，禁止两列混用）。

---

## D. 可默认题（防污染 / 交付）

### D1. `ftag='预算数据'` 行怎么处理？

推荐：`keep_bottom_drop_view`。底层 `dw_sale_order_saptest` 保留（含 `fbudget_category/fbudget_qty/fbudget_amount` 保底预算字段，`DataSources='填报'`）；出货视图 `v_sale_ship_order_emp_product` 不暴露这些列、其 `ftag='预算数据'` 行金额为 0 明细全空，故剔除。

### D2. 完全重复行？

推荐：`dedup_full_row`。`dw_sale_order_saptest` 去 45 行（8,081 → 8,036）；`v_sale_ship_order_emp_product` 去 51 行完全重复 + 25 行 `ftag='预算数据'`（8,064 → 7,988）；其余对象按全列去重（当前均无重复）。

### D3. PII 字段？

推荐：`drop_pii`。`bi_vpsempinfo_month` 的 `idcardnum`（身份证）、`mobilephone`（手机号）、`birthday`（出生日期）不进任何分析产物；该表只作 EHR 血缘，不单独建模。

### D4. 清洗产物？

推荐：`parquet` + `dq_report.json`，路径 `datasets/processed/marketing_2026H1/`。原始 CSV 只读，不改。

### D5. 预算单位？

推荐：`wan_only`。两张预算表单位万元（含税），保持原值，不 ×10000；达成率 = `SUM(宽表金额)/10000 / 预算`。

### D6. 6 个底层/中间对象是否建模成图节点？

推荐：`dims_only`。底层表/中间视图（`dw_sgning_wide_table`、`dw_sale_order_saptest`、`bi_vpsempinfo_month`、`fill_sales_dept`、`v_sales_emp_info`、`ods_sap_cw_product`）只作清洗血缘，不单独成节点；图节点用 4 个允许查询对象（两宽表 + 两预算表）+ 维度实体（业务员/科室/客户/产品类型/区域/机型/月）。

---

## 答完之后

1. 把选项写入本目录 [decisions.md](./decisions.md)（一题一行）。
2. 生成 `specs/marketing-data-processing/spec.md`（SHALL + Scenario）。
3. 再写 [tasks.md](./tasks.md) 和清洗脚本 `datasets/process_marketing_data.py`。

B1–B5、D1–D6 的推荐默认已按 [decisions.md](./decisions.md) 记录，待确认后冻结。

---

# 第二轮 Grill-Me（实采后追加）

第一轮在**读文档**阶段完成；本轮在**实采剖析**之后追加。  
触发原因：[ontology.md](./ontology.md) §5 的证伪结果 —— 有 5 个问题文档没写、第一轮也没问，但它们会直接决定达成率差 2.5 倍。

全部证据可复核（只读脚本对 `dataReport/dataset/` 实算，CSV 未改）。

## B6. 达成分子要不要限定组织？（决定 228.6% 还是 211.0%）

证据：`fill_dept_budget.OrgName` = 装备一事业群（234/234）；宽表 `Orgname` 混有装备三事业部 181/329 行、世纪鑫昌 45/41、装备二-本部 37/33、装备五 26、赫勒 6、广州霏鸿 5/10、集团 10。

| 选项 | 含义 | 若选错 |
|---|---|---|
| `org_scope_filter`（推荐） | 达成口径分子限定装备一；其他组织保留在事实表但打 `out_of_scope` 标 | 若业务其实要看全集团，需另建全集团预算 |
| `all_org` | 分子不分组织，全宽表直接比 | 228.6% 达成，把无预算的兄弟事业部算进分子 |
| `org_dim_column` | 分子不删行，靠 `org_scope` 列让下游选 | 下游忘记过滤就静默算错 |

推荐默认：`org_scope_filter` + 同时落 `org_scope` 标记列（两者叠加，既过滤又可审计）。

## B7. 达成分子要不要限定预算覆盖机型？（决定 148.2% 还是 130.6%）

证据：`fill_product_budget.ProductType` 仅 6 个值，`ods_sap_cw_product.ZPROD_TYPE` 有 22 个。未覆盖的大头是 **3C钻攻机**（装备一口径出货 121,038.96 万元，占 29.9%）。

| 选项 | 含义 | 若选错 |
|---|---|---|
| `budget_covered_only`（推荐） | 分子限定 `zprod_type ∈ 预算覆盖 6 类` | 3C 达成被系统性排除 |
| `all_model` | 分子取全机型 | 148.2%，分子含 12 亿无预算的 3C |
| `exclude_3c_only` | 只排除 3C | 其余 15 个未覆盖类型仍混在分子里 |

推荐默认：`budget_covered_only`。补充事实：3C 有预算，但挂在 `SalesDept='3C销售部'`（`Fdept` 空的 18 行之一），**不在产品类型维度**——想算 3C 达成要走部门路径。

## B8. 空键（Fdept 为空）怎么处理？（决定 103.3% 还是 130.6%）

证据：出货宽表 `Fdept` 空 1131/7988（14.2%）、签单宽表空 800/7563；预算 `Fdept` 空 18/234。朴素 `isin` 会因「空串 ∈ 空串集合」给出 100% 命中的假象。

| 选项 | 含义 |
|---|---|
| `drop_from_achieve`（推荐） | 空键不参与任何对照；未归属行进 `dq_report.unassigned_rows` 保留在事实表 |
| `treat_as_bucket` | 建一个「未分配」科室节点，与预算对照 | 
| `ignore_null` | 照常 join，接受空串互配 | 

推荐默认：`drop_from_achieve` + dq 计数。注意与 D1 的区别：这是**键缺失**，不是占位行。

## B9. `SalesCode` 不唯一（458 行 / 455 工号）怎么取规范行？

证据：`C13437` 闫晨、`C13480` 陈珺珺、`C15083` 辛清卫 各有 2 行，两行 `EmploymentStatus` 一个在职一个离职，其余字段完全相同。

| 选项 | 含义 | 若选错 |
|---|---|---|
| `prefer_active`（推荐） | 同一工号取 `在职` 行；全离职取第一行；冲突进 dq | 离职态被抹掉 |
| `keep_both` | 维度保留 458 行，用复合键 | 与事实表 join 会翻倍这 3 人的业绩 |
| `prefer_latest` | 按 `Sales_Employment_Date` 取最新 | 无稳定排序依据（44 行该列为空） |

推荐默认：`prefer_active`。

## B10. 两张预算表能不能交叉 / 相加？

证据：两表三个指标合计差 ≤ 1.26 万元（考核出机 192,663.33 vs 192,663.36；管理出机 276,254.96 vs 276,254.00；管理签单 297,809.11 vs 297,810.37），逐月同样贴合 —— **同一笔预算的两个维度分摊**。

| 选项 | 含义 |
|---|---|
| `mutually_exclusive`（推荐） | 一次查询只走一条投影；「科室×产品」交叉问法显式拒绝 |
| `joinable` | 建科室↔产品连接边 | 
| `additive` | 两表相加得总预算 | 

推荐默认：`mutually_exclusive`。理由：两表无连接键，交叉需要 39×6×6 的分配矩阵，本数据集未导出。

## D7. 负金额（退货 / 退补）？

推荐：`keep_and_count`。签单 264 行、出货 299 行负金额；`AuartName` 中退补退货 207、标准退货 41、换机退货 16；出货 `ftag='销售退货'` 67 行。保留并在 dq 计数。

## D8. 组织边界标记？

推荐：`org_scope_column`。事实表新增 `org_scope ∈ {in_scope, out_of_scope, unknown}`，`in_scope` = `Orgname` 属装备一；`unknown` = `Orgname` 空。默认达成口径取 `in_scope`。

## 答完之后

1. 把 B6–B10、D7–D8 写入 [decisions.md](./decisions.md)。
2. 更新 [schemas.md](./schemas.md)（新增列：`org_scope`、`cust_code`、`model_unregistered` 等）。
3. 更新 [tasks.md](./tasks.md) 与清洗脚本 `datasets/process_marketing_data.py`。
4. 图建模与 GraphRAG 走新 change [marketing-graphrag](../marketing-graphrag/proposal.md)。
