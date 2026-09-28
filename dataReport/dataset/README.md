# dataset 数据说明

数据源：SQL Server `csj_dw.dbo`（`192.168.10.209:1433`），账号 `BI_AI`。
口径范围：**2026 年 1-6 月**。本目录覆盖 `csj_dw表关联ER.md` 中全部 10 个对象的清洗结果。

## 文件清单（共 10 张）

| 文件 | 对象 | 类型 | 中文 | 行数 | 时间口径 |
|------|------|------|------|------|----------|
| `fill_sales_dept.csv` | `fill_sales_dept` | 表 | 业务员部门架构 | 458 | 维度快照（无时间字段） |
| `bi_vpsempinfo_month_2026H1.csv` | `bi_vpsempinfo_month` | 表 | EHR 组织月表 | 72,755 | 2026-01~06（y1/m1） |
| `v_sales_emp_info.csv` | `v_sales_emp_info` | 视图 | 业务组织架构 | 458 | 当前月快照 |
| `dw_sgning_wide_table_2026H1.csv` | `dw_sgning_wide_table` | 表 | 销售签单明细 | 7,558 | 2026-01~06（Fyear/Fmonth） |
| `dw_sale_order_saptest_2026H1.csv` | `dw_sale_order_saptest` | 表 | 发货数据表 | 8,036 | 2026-01~06（fyear/fperiod） |
| `ods_sap_cw_product.csv` | `ods_sap_cw_product` | 表 | 机型所属分类 | 527 | 维度（无时间字段） |
| `v_sales_order_product_2026H1.csv` | `v_sales_order_product` | 视图 | 签单宽表 | 7,563 | 2026-01~06 |
| `v_sale_ship_order_emp_product_2026H1.csv` | `v_sale_ship_order_emp_product` | 视图 | 出货宽表 | 7,988 | 2026-01~06 |
| `fill_dept_budget_2026H1.csv` | `fill_dept_budget` | 表 | 科室月度预算 | 234 | 2026-01~06（Fyear/Fmonth） |
| `fill_product_budget_2026H1.csv` | `fill_product_budget` | 表 | 产品类型月度预算 | 36 | 2026-01~06（Fyear/Fmonth） |

金额单位：两张宽表与两张底层事实表金额为**元**；预算表为**万元**；比较前 `SUM(宽表金额) / 10000`。

## 关联血缘（底 → 顶）

```text
fill_sales_dept ──LEFT JOIN── bi_vpsempinfo_month（当年当月 y1/m1）
        │
        ▼
 v_sales_emp_info（组织视图）
        │
        ├── FULL OUTER JOIN dw_sgning_wide_table
        │         └── LEFT JOIN ods_sap_cw_product（FmateType = ZPROD_NAME）
        │                    ▼
        │              v_sales_order_product（签单宽表）
        │
        └── 被 LEFT JOIN ← dw_sale_order_saptest（驱动表）
                  └── LEFT JOIN ods_sap_cw_product（fmate_type = ZPROD_NAME）
                             ▼
                  v_sale_ship_order_emp_product（出货宽表）

fill_dept_budget      ── 业务对照 Fdept ── 两宽表（管理/考核出机、管理签单）
fill_product_budget   ── 业务对照 ProductType ≈ ZPROD_TYPE ── 两宽表
```

说明：
- 签单宽表：`v_sales_emp_info` FULL OUTER JOIN `dw_sgning_wide_table`，再 LEFT JOIN 产品分类，视图内已 `GROUP BY`。
- 出货宽表：以 `dw_sale_order_saptest` 为驱动 LEFT JOIN 组织视图与产品分类，视图**无** `GROUP BY`。
- `v_sales_emp_info` 与 `fill_sales_dept` 当前库内字段为 `Fdept_add`（文档中的 `Fdept` 对应此列）。

## 清洗规则

1. **时间过滤**：事实/预算类表仅保留 2026-01 至 06；维度表（`fill_sales_dept`、`ods_sap_cw_product`）与组织视图 `v_sales_emp_info` 为快照，全量导出。
2. **列名规范化**：签单宽表视图的 `Expr1~Expr4` 还原为 `empSalesCode/ordSalesCode/empSalesName/ordSalesName`。
3. **去重**：
   - `dw_sale_order_saptest` 去掉 45 行完全重复行（8,081 → 8,036）。
   - `v_sale_ship_order_emp_product` 去掉 51 行完全重复行 + 25 行 `ftag='预算数据'` 占位（8,064 → 7,988）。
   - 其余对象按全列去重（签单明细、组织表、维度表均无重复）。
4. **`预算数据` 行的处理**：
   - 底层 `dw_sale_order_saptest` **保留** `ftag='预算数据'` 行——其含 `fbudget_category/fbudget_qty/fbudget_amount` 等「保底」预算字段（`DataSources='填报'`）。
   - 出货视图 `v_sale_ship_order_emp_product` 不暴露上述预算列，其 `ftag='预算数据'` 行金额为 0、明细全空，故剔除。
5. **空值统一**：`NULL`、字符串 `"NULL"`、空串统一为空。
6. **日期标准化**：`BusinessDate/SalesDocnoDate/entrydate/d1/birthday/dimissiondate/Sales_Employment_Date` 统一为 `YYYY-MM-DD`。
7. **数值清洗**：金额列保留 2 位小数；数量列保留 3 位小数；负金额（退货/退补）为有效记录，保留。

## 常用指标口径

| 业务说法 | 实际字段 | 单位 |
|----------|----------|------|
| 管理出机 | 出货宽表 `TotalMoneyFC_HS` | 元 |
| 考核出机 | 出货宽表 `TotalMoneyFC_HS` | 元 |
| 管理签单 | 签单宽表 `TotalMoneyFc_HS` | 元 |

- 达成类：按 `Fdept` 全量、不过滤 `User_role`。
- 连续不签单/未出机：`User_role='业务'`，按 `SalesCode` 聚合，姓名取 `MAX`。

## 敏感信息提示

- `bi_vpsempinfo_month_2026H1.csv` 含个人敏感字段：`idcardnum`（身份证号）、`mobilephone`（手机号）、`birthday`（出生日期）等，请按内网权限管控，勿外发或提交公开仓库。

## 生成方式

由 Python（`pymssql` + `pandas`）连接数据库查询后按上述规则清洗，以 `utf-8-sig`（带 BOM）编码写出，Excel 直接打开中文不乱码。
