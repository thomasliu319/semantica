# Decisions

状态：`proposed`（第一轮 B1–B5、D1–D6 推荐默认；第二轮 B6–B10、D7–D8 已按推荐默认**执行**，可改选后重跑）。  
来源：Grill-Me [grill.md](./grill.md) 推荐默认。第二轮触发于实采证伪，证据见 [ontology.md](./ontology.md) §5、场景解读见 [scenarios.md](./scenarios.md)。  
本文件是规格真源。改口必须先改这里，再改 spec / 脚本。

| 题 | 选项 | 冻结含义 |
|---|---|---|
| B1 | `clean_only` | 本 change 不定分析目标，不构造达成率/名单，只出干净事实表 + 维度表 |
| B2 | `hybrid` | `sign_order_line` / `ship_order_line` 事实 + `emp_dim` / `dept_dim` / `product_dim` + 两张预算月表 |
| B3 | `wan` | 金额统一万元：宽表 /10000，预算原样；明细列保留元 + 万元列 |
| B4 | `fdept_all` | 达成类按 `Fdept` 全量、不过滤 `User_role`；连续不签单/未出机才 `User_role='业务'` |
| B5 | `fdept_add` | 组织侧以 `Fdept_add` 对齐；宽表 `Fdept` 回填自 `Fdept_add`；禁止两列混用 |
| D1 | `keep_bottom_drop_view` | 发货表保留 `ftag='预算数据'`；出货视图剔除同 `ftag` 行 |
| D2 | `dedup_full_row` | 完全重复行去重；其余全列去重 |
| D3 | `drop_pii` | `idcardnum`/`mobilephone`/`birthday` 不进分析产物 |
| D4 | `parquet` | `datasets/processed/marketing_2026H1/*.parquet` + `dq_report.json` |
| D5 | `wan_only` | 预算表单位万元（含税）保持原值，不 ×10000 |
| D6 | `dims_only` | 6 个底层/中间对象只作血缘，不单独建模；图节点用 4 允许查询对象 + 维度实体 |

## 第二轮（实采后追加，已按推荐默认执行）

| 题 | 选项 | 冻结含义 | 证据 |
|---|---|---|---|
| B6 | `org_scope_filter` | 达成分子限定装备一；事实表同时落 `org_scope` 标记列（`in_scope`/`out_of_scope`/`unknown`） | 预算 OrgName 234/234 装备一；宽表混 8 个组织 → 不限定则 227% |
| B7 | `budget_covered_only` | 达成分子限定 `zprod_type ∈ 预算覆盖 6 类` | 预算覆盖 6/22 类型；3C钻攻机 12.1 亿未覆盖 → 不限定则 147% |
| B8 | `drop_from_achieve` | 空键不参与任何对照；未归属行进 `dq_report.unassigned_rows`，事实表保留 | 出货宽表 Fdept 空 1131/7988；空串伪命中 100% |
| B9 | `prefer_active` | 同一 `SalesCode` 取「在职」行；冲突进 dq | 458 行 / 455 工号；C13437/C13480/C15083 各 2 行 |
| B10 | `mutually_exclusive` | 两张预算表一次查询只走一条投影；「科室×产品」交叉问法显式拒绝 | 两表三指标合计差 ≤1.26 万元 = 同一笔预算的两个分摊 |
| D7 | `keep_and_count` | 负金额（退货/退补）保留，dq 单列计数 | 签单 264 行 / 出货 299 行负金额 |
| D8 | `org_scope_column` | 事实表新增 `org_scope` 列，`in_scope` = Orgname 属装备一 | 见 B6 |

补充约束：清洗窗口 2026-01~06（H1）。`bi_vpsempinfo_month` 只作 EHR 血缘，不进分析层。原始 CSV 只读。

## 派生口径（由上述决策合成）

**达成率默认口径**（写入 `metrics.md`）：

```
分子 = Σ ShipOrderLine.total_money_fc_hs_wan
       WHERE org_scope = 'in_scope'
         AND zprod_type ∈ 预算覆盖集合
         AND fdept 非空
分母 = Σ DeptBudgetMonth.<指标>_budget_hs     （万元，含税，原值）
达成率 = 分子 / 分母；分母为 0 → null
```

三个指标：管理出机（`management_ship_budget_hs`）、考核出机（`assessment_ship_budget_hs`）、管理签单（`management_signed_contract_hs`，分子走 `sign_order_line`）。

> 待确认：B1–B10 为阻塞题，请在 [grill.md](./grill.md) 上确认或改选；D1–D8 可按默认采纳。改选后重跑 `datasets/process_marketing_data.py`。
