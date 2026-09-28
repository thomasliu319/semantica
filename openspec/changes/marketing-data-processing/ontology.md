# 本体论语义分析：营销/经营数据（csj_dw · 2026 H1）

本文记录**从 10 张 CSV 到本体模型**的完整推理过程，可逐节复核。  
输入：`dataReport/dataset/` 10 张 CSV（SQL Server `csj_dw.dbo` 导出，口径 2026-01~06）。  
本文所有「实采」数字均由只读剖析脚本对 CSV 实算得出，不来自文档推断。

分析顺序：**① 存在论盘点（有什么存在）→ ② 语义消歧（说的是不是一回事）→ ③ 关系识别（怎么连）→ ④ 分层与公理（约束是什么）→ ⑤ 陷阱证伪 → ⑥ 能力问题验收 → ⑦ 冻结进建模**。

上游决策见 [decisions.md](./decisions.md)、[grill.md](./grill.md)；下游建模见 [design.md](./design.md)、[schemas.md](./schemas.md)；场景解读见 [scenarios.md](./scenarios.md)。

---

## 0. 先立判据：什么才算一个「实体」

不加判据就会把每张表都变成节点（10 个节点、一堆 JOIN 边），那是 ER 图不是本体。本节先冻结判据，后面逐个候选按同一把尺子量。

| 判据 | 含义 | 反例（不是实体） |
|---|---|---|
| **E1 可独立标识** | 有稳定的业务键，不依赖某张事实表才存在 | `Docno`（离开了订单行没有意义 → 是事件的标识，不是独立物） |
| **E2 有自己的属性** | 存在非外键、非度量的描述性属性 | `Fyear×Fmonth` 组合（只有标签，没有自身属性 → 是时间坐标不是物） |
| **E3 被多个事实引用** | 至少被两个不同事实共享，否则并入宿主 | `WERKS`/工厂（只被出货引用 → 降为出货行的属性） |
| **E4 跨时间存续** | 状态可在多个时点被重新描述 | 单笔金额（一次性的量 → 是属性不是物） |

同时冻结三条语义规则：

- **R1（键同一性）**：两个名字指向同一实体，当且仅当业务键的值域互相覆盖且业务上不可再分。
- **R2（同名必异义）**：同一字符串在不同表里出现，默认视为**不同**实体，除非 R1 成立。
- **R3（单位同一性）**：可比较的量纲必须同单位；不同单位的同名指标视为两个不同的属性。

---

## 1. 存在论盘点：从 10 张表到候选实体

### 1.1 先分类：这 10 张表在本体里是什么「东西」

ER 图（`csj_dw表关联ER.md`）把 10 张表画成同等地位的方框，这是第一个需要纠正的直觉。**表 ≠ 实体**：这 10 张表分属三个不同的存在论范畴。

| 范畴 | 定义 | 本数据集中的对象 | 本体后果 |
|---|---|---|---|
| **持续体（Continuant）** | 跨时间存续、可被反复描述 | `fill_sales_dept`、`v_sales_emp_info`、`bi_vpsempinfo_month`、`ods_sap_cw_product` | 上升为**类** |
| **发生体（Occurrent）** | 在某个时点发生、有起止与金额 | `dw_sgning_wide_table`、`dw_sale_order_saptest` | 上升为**事件类** |
| **投影（Projection）** | 由别的对象按规则算出，无独立存在 | `v_sales_order_product`、`v_sale_ship_order_emp_product`、`fill_dept_budget`、`fill_product_budget` | **不是新实体**，是视图/计划 |

> 关键结论 A：`fill_dept_budget` 与 `fill_product_budget` 虽然是业务上传的「表」，存在论上却是**计划（Plan）**而不是发生体 —— 它们描述「应该发生什么」，不是「发生了什么」。因此预算与实际的对照不是两个事实的连接，而是**实际 vs 计划**的对照关系。这决定了后面不能把预算当事实表 join 进去相加。

> 关键结论 B：两张宽表是**投影**，其行由底层事件 + 组织维度拼出。把它们当独立实体会导致同一笔签单在两个抽象层各出现一次（双计风险）。

### 1.2 候选实体逐个过判据

| 候选 | E1 可标识 | E2 有属性 | E3 多事实引用 | E4 跨时间 | 判定 |
|---|:--:|:--:|:--:|:--:| --- |
| 业务员 `SalesCode` | ✅ | ✅ 姓名/省/市/角色/在职 | ✅ 签单+出货+预算 | ✅ | **实体** |
| 科室 `Fdept_add` | ✅ | ✅ 大区/销售部/事业群 | ✅ 签单+出货+预算 | ✅ | **实体** |
| 客户 `KunnrCode`/`fcust_number` | ✅ | ✅ 名称/地区 | ✅ 签单+出货 | ✅ | **实体**（需消歧，见 §2.3） |
| 机型 `ZPROD_NAME` | ✅ | ✅ 系列/编号 | ✅ 签单+出货 | ✅ | **实体** |
| 产品类型 `ZPROD_TYPE` | ✅ | ⚠️ 仅名称 | ✅ 出货+签单+产品预算 | ✅ | **实体**（预算对照键） |
| 大区 `Area` | ✅ | ✅ | ✅ | ✅ | **实体**（组织层级节点） |
| 月 `Fyear×Fmonth` | ✅ | ❌ | ✅ | — | **时间坐标**，建模为节点但标注为 `TimeInstant` |
| 签单事件 `Docno+DocnoNum` | ✅ | ⚠️ | ❌ 仅签单 | ❌ | **事件**（非持续体） |
| 出货事件 `DocNo+行` | ✅ | ⚠️ | ❌ 仅出货 | ❌ | **事件**（非持续体） |
| 合同 `ContractName` | ✅ | ❌ | ❌ | ❌ | **属性**（挂在签单事件上） |
| 工厂 `WERKS`/`factory` | ✅ | ✅ | ❌ 仅出货 | ✅ | **属性**（降格，E3 不成立） |
| 事业部 `Orgname`/`ForgName` | ✅ | ✅ | ✅ | ✅ | **实体**（组织层级顶层，且是口径边界） |
| EHR 月表 `empcode` | ✅ | ✅ PII | ❌ 只喂组织视图 | ✅ | **同一个业务员实体的另一数据源**（非新实体） |
| 主管 `SupervisorName` | ❌ 只有姓名 | ❌ | — | — | **属性**（不是独立实体，无工号键） |

> 关键结论 C：`SupervisorName` 在本数据集中**不是**实体 —— 只有姓名字符串，无工号（`fill_sales_dept` 无 `SupervisorCode`）。若按 ER 直觉建 `主管` 节点并用姓名做键，遇到重名就会错误合并。**不建模为节点**，保留为业务员的属性。

---

## 2. 语义消歧：哪些名字说的是同一件事

这是本体分析的核心工作量。逐组列出候选同义，用实采值域判定 R1 是否成立。

### 2.1 `Fdept` vs `Fdept_add` —— 同一科室的两个粒度（**最危险**）

| 项 | `Fdept_add` | `Fdept` |
|---|---|---|
| 实采唯一值 | **40** | **50** |
| 458 行中两列相等 | — | 366 行（**92 行不等**） |
| 不等样例 | `华中大区销售二科` | `华中销售二科`（少了"大区"） |
| | `华北大区①销售一科` | `华北大区①销售一科四组`（多了组） |
| | `华南五区销售一科` | `华南五区`（退到区名） |

判定：**不是同义词，是同一维度上的两个粒度层级**。`Fdept` 混了三种东西 —— 标准科室（`…销售N科`）、细分小组（`…科N组`）、退化的区名（`华南五区`）。

再看预算侧谁对得上：

```
预算 fill_dept_budget.Fdept 非空 216 行 / 37 个值
  ├─ ⊆ fill_sales_dept.Fdept_add ?  是（216/216 全覆盖）
  └─ ⊆ fill_sales_dept.Fdept      ?  否（仅 180/216）
Fdept_add 中不在预算里的 4 个值：华东大区、华北大区①、华南3C、华南大区
```

判定：**预算的 `Fdept` 就是 `Fdept_add` 口径**，那 4 个落单值恰好是区名/小区名（不是科室）。这印证了 `关键文件与检查清单.md` 里那句「达成结果里可能出现区名/小区名，属全量口径」。

→ 冻结（与 B5 一致）：**科室实体的规范键 = `Fdept_add`**；`Fdept` 只是组织表内部的细粒度变体，**禁止作为对齐键**。

### 2.2 `ZPROD_NAME` / `FmateType` / `fmate_type` / `FmateNumber` —— 一个实体的三种叫法 + 一个邻居

| 名字 | 出现位置 | 实采基数 | 判定 |
|---|---|---|---|
| `ZPROD_NAME` | `ods_sap_cw_product`（主键） | 527 | **规范键**：机型 |
| `FmateType` | 签单明细 | 201 | = `ZPROD_NAME`（命中 7538/7558） |
| `fmate_type` | 发货表 | 197 | = `ZPROD_NAME`（命中 7998/8036） |
| `FmateNumber` / `fmate_number` | 两处 | 1906 / 1726 | **不是机型**：物料编码，是机型的下级 SKU |

命中率缺口（签单 20 行、出货 38 行）就是**未登记机型**，实采名字如 `B-850`、`DH-50S`、`L-35L`、`S-800U`、`INT-HBM-130`、以及字面量 **`其它机型`**。

→ 冻结：机型实体主键 `ZPROD_NAME`；未命中行**保留事实、机型置空并记 dq**（不能因为对不上分类就丢钱）。

> 陷阱：`FmateNumber`（1906 个）基数远大于机型（527）。若误用物料编码做机型键，机型节点会从 527 暴涨到 1906，所有「按机型汇总」的口径都碎掉。

### 2.3 `KunnrCode` vs `fcust_number` —— 同名异物还是异名同物？

```
签单 KunnrCode      唯一 4149
出货 fcust_number   唯一 3896
交集                3800
```

覆盖率：签单客户 7110/7558 行能在出货客户集合里找到。值域高度重叠（前缀同族 `C01…`/`C02…`）但**不完全相等**：349 个签单客户从未出货，96 个出货客户未出现在签单里。

按 R1 判定：**同一实体「客户」的两个数据源**。但注意它们在本体里扮演的角色不同 —— 签单侧是「**合同相对方**」，出货侧是「**收货方**」。在 SAP 里这两者可以不同（代发货、集团内调拨）。

→ 冻结：建模为**一个** `Customer` 实体（并集键），但在两条事实上分别标注角色 `contractParty` / `shipTo`。这与「不丢失行」冲突最小。

### 2.4 时间：签单与出货用了两套日历字段

| 事实 | 期间字段 | 日期字段 | 实采一致性 |
|---|---|---|---|
| 签单 | `Fyear`+`Fmonth` | `SalesDocnoDate` | **`Fmonth` 与单据日期月份 100% 一致** |
| 出货 | `fyear`+`fperiod` | `BusinessDate` | 一致率 99.63%（30 行 `BusinessDate` 空） |

那 30 行空 `BusinessDate` 正是 `ftag='预算数据'` 的填报行 —— 与 D1 一致。

→ 冻结：月坐标统一为 `(year, month)`；签单取 `Fyear/Fmonth`，出货取 `fyear/fperiod`，**禁止用 `BusinessDate` 反推期间**（会漏掉 30 行，且 0.37% 的行会错位）。

### 2.5 金额：四个 `TotalMoney*` 是一张 2×2 语义网格

| | 不含税 | 含税 |
|---|---|---|
| **签单** | `TotalMoneyFc` | `TotalMoneyFc_HS` |
| **出货** | `TotalMoneyFC` | `TotalMoneyFC_HS` |

注意签单是 `Fc`（小写 c）、出货是 `FC`（大写 C）—— 大小写差异**不携带语义**，纯属历史命名。真正的语义轴是 `_HS` 后缀（含税）。

实采量级（元）：

| 列 | 合计 | 负行 | 零行 |
|---|---|---|---|
| 签单 `TotalMoneyFc_HS` | 5,169,219,039.24 | 264 | 3 |
| 出货 `TotalMoneyFC_HS` | 4,404,648,457.78 | 299 | 30 |

→ 冻结（与 B3/D5 一致）三个指标实体：**管理签单 = 签单含税；管理出机 = 考核出机 = 出货含税**（同一字段，仅对照的预算列不同）。负金额是退货/退补，**是有效发生体，保留**。

### 2.6 系列字段：签单与出货的词表不一致

```
签单 FmateSeris  15 值：…精密数控纵切车床、铣床加工中心…
出货 fmate_series 17 值：…七轴五联动车铣复合加工中心、铣镗加工中心、其它系列…
```

两者是**同一个语义维度（机型系列）的两套词表**，互不包含。

→ 冻结：系列**不建模为独立实体**（词表不统一，强行合并会造出假的同义关系），降为各自事实的属性；跨事实的系列对比必须先经机型 `ZPROD_NAME` 归一。

### 2.7 区域：三个 `Area` 不是一回事

| 字段 | 表 | 实采基数 | 语义 |
|---|---|---|---|
| `Area` | 组织/宽表（来自组织视图） | 9（签单宽表）/ 8（出货宽表） | **销售大区**（组织归属） |
| `Area_fq` | 科室预算 | 9 | 大区下的**分区**（华南一区…华东三区） |
| `fcust_area` | 发货表 | 7 | **客户所在地**（华南地区/华东地区…） |

→ 冻结：三个字段属于**两个不同实体**的属性 —— `Area`/`Area_fq` 属于「组织区域」层级，`fcust_area` 属于「客户」。把 `fcust_area` 当销售大区做达成分析，会把「华东卖给了西北客户」的单据算错归属。

---

## 3. 关系识别：从 JOIN 到语义关系

ER 图给的是**物理连接**（LEFT JOIN / FULL OUTER JOIN / 业务对照），本体要的是**语义关系**。逐条翻译。

### 3.1 物理连接 → 语义关系映射表

| 物理连接（来自 DDL） | ON 条件 | 语义关系 | 逆关系 | 基数（实采） |
|---|---|---|---|---|
| `fill_sales_dept → v_sales_emp_info` | 驱动表 | `derivedFrom`（投影） | — | 1:1（458=458） |
| `bi_vpsempinfo_month → v_sales_emp_info` | `SalesCode=empcode` + 当年当月 | `hasEhrRecord`（同一实体的另一数据源） | — | 1:0..1（2231/2748 命中） |
| `v_sales_emp_info ↔ dw_sgning_wide_table` | FULL OUTER `SalesCode` | `signs`（业务员 签 签单事件） | `signedBy` | 0..1 ↔ 0..N |
| `dw_sale_order_saptest → v_sales_emp_info` | `fsales_number=SalesCode` | `ships`（业务员 出 出货事件） | `shippedBy` | 0..1 ← N |
| `dw_sgning_wide_table → ods_sap_cw_product` | `FmateType=ZPROD_NAME` | `ofModel`（事件 的机型） | — | 0..1 ← N（20 行落空） |
| `dw_sale_order_saptest → ods_sap_cw_product` | `fmate_type=ZPROD_NAME` | `ofModel` | — | 0..1 ← N（38 行落空） |
| `fill_dept_budget ⇢ 两宽表` | `Fdept` | **`budgetsFor`（计划 对照 组织）** | `measuredAgainst` | 1:N，但见 §5.3 |
| `fill_product_budget ⇢ 两宽表` | `ProductType ≈ ZPROD_TYPE` | **`budgetsFor`（计划 对照 产品类型）** | `measuredAgainst` | 1:N，但见 §5.3 |

### 3.2 三条 ER 图里**没有**、但本体必须有的关系

图上没有，是因为 DDL 里没有 JOIN；但业务语义确实存在，缺了它们图就答不了问题：

| 关系 | 从 → 到 | 语义 | 为什么必须补 |
|---|---|---|---|
| `belongsTo` | 业务员 → 科室 | 组织归属 | 有了它，「某科室有哪些人」不用绕事实表 |
| `partOf` | 科室 → 大区 → 事业部 | 组织层级 | 上卷（rollup）路径，否则大区/事业部口径要重扫事实 |
| `categorizedAs` | 机型 → 产品类型 | 分类 | 机型 527 → 类型 22 的唯一上卷路径，也是产品预算的对照桥 |
| `locatedIn` | 客户 → 客户地区 | 地理 | 与销售大区区分（§2.7） |
| `reportsTo` | 业务员 → 主管 | 汇报 | **降级为属性**（§1.2 关键结论 C：无工号键） |
| `inMonth` | 事件 → 月 | 时间坐标 | 所有时序切片的入口 |

### 3.3 关系的形式性质（决定是否可函数式使用）

| 关系 | 函数性 | 说明 |
|---|---|---|
| `belongsTo`（业务员→科室） | **非函数** | 同一工号在 H1 可能异动；且实采有 3 个工号对应 2 行（见 §5.1） |
| `categorizedAs`（机型→类型） | **函数** | `ods_sap_cw_product` 527 行唯一（`ZPROD_NAME` 527 唯一） |
| `partOf`（科室→大区） | **函数** | 由科室名前缀决定，实采无跨大区科室 |
| `budgetsFor`（预算→组织） | **非函数** | 18 行预算 `Fdept` 为空（见 §5.4） |
| `inMonth`（事件→月） | **函数** | 每行只有一个期间 |

---

## 4. 本体分层与形式化

### 4.1 上层（Top-level）对齐

沿用 iot-data-processing 的持续体/发生体二分，不引入更重的上层本体：

```
Continuant（持续体）           Occurrent（发生体）
├─ Agentive（能动者）          ├─ BusinessEvent（业务事件）
│   ├─ SalesPerson             │   ├─ SignOrderLine（签单行）
│   └─ OrgUnit                 │   └─ ShipOrderLine（出货行）
│       ├─ Dept                └─ Plan（计划 / 非发生体）
│       ├─ Area                    ├─ DeptBudgetMonth
│       └─ BusinessGroup          └─ ProductBudgetMonth
├─ NonAgentive（非能动者）
│   ├─ Customer
│   ├─ Product（机型）
│   └─ ProductType
└─ TimeInstant（月）
```

> 设计理由：把 `Plan` 从 `Occurrent` 里单拎出来，是为了在类型层面**禁止**「预算 + 实际」被当成两个同类事实相加。这是 §5.4 双计陷阱的结构性防线 —— 不是靠文档约定，而是靠类不相交（disjointness）。

### 4.2 域本体类定义（营销销售域）

| 类 | 规范键 | 关键属性 | 不相交于 |
|---|---|---|---|
| `SalesPerson` | `sales_code` | `sales_name`, `user_role`, `employment_status`, `province`, `affiliation_city`, `sales_employment_date` | `OrgUnit`, `Customer`, `Product` |
| `Dept` | `fdept`（= `Fdept_add`） | `org_name`, `sales_dept`, `area`, `area_fq` | `Area`, `BusinessGroup` |
| `Area` | `area` | — | `Dept` |
| `BusinessGroup` | `org_name` | — | `Dept`, `Area` |
| `Customer` | `cust_code` | `cust_name`, `cust_area` | `SalesPerson` |
| `Product` | `zprod_name` | `zprod_type`（外键）, `series` | `ProductType` |
| `ProductType` | `zprod_type` | — | `Product` |
| `Month` | `year`,`month` | — | 全部持续体 |
| `SignOrderLine` | `docno`+`docno_num` | `contract_name`, `kunnr_code`, `fqty`, `total_money_fc`, `total_money_fc_hs`, `total_money_fc_hs_wan`, `auart_name`, `sales_docno_date` | `ShipOrderLine` |
| `ShipOrderLine` | `docno`+行号 | `ftag`, `fcust_number`, `fqty`, `total_money_fc`, `total_money_fc_hs`, `total_money_fc_hs_wan`, `business_date` | `SignOrderLine` |
| `DeptBudgetMonth` | `fdept`,`year`,`month` | `management_ship_budget_hs`, `assessment_ship_budget_hs`, `management_signed_contract_hs` | 全部 `Occurrent` |
| `ProductBudgetMonth` | `product_type`,`year`,`month` | 同上三列 | 全部 `Occurrent` |

### 4.3 公理（可机检）

```
A1  单位公理：SignOrderLine.total_money_fc_hs : 元
              DeptBudgetMonth.management_ship_budget_hs : 万元
              ∎ 二者不可直接相除；必须先 /10000
A2  键公理：  SalesPerson.sales_code 在维度内唯一（实采 458 行 → 455 唯一，冲突 3，见 §5.1）
A3  键公理：  Product.zprod_name 唯一（527/527 ✅）
A4  键公理：  DeptBudgetMonth(fdept, year, month) 唯一（实采 234 = 39×6，其中 18 行 fdept 空）
A5  不相交：  Plan ⊥ BusinessEvent
A6  函数性：  Product.categorizedAs 恰好 1 个 ProductType
A7  非空：    ShipOrderLine 的 ftag ∈ {销售发货, 销售退货, 预算数据}
A8  时间公理：SignOrderLine.inMonth 由 Fyear/Fmonth 决定，不由 SalesDocnoDate 反推
              ShipOrderLine.inMonth 由 fyear/fperiod 决定，不由 BusinessDate 反推
A9  层级公理：SalesPerson.belongsTo Dept，Dept.partOf Area，Area.partOf BusinessGroup
A10 空键公理：任何以空串为键的对照关系不成立（空 ≠ 空），见 §5.3
```

---

## 5. 语义陷阱：假设 → 实采证伪

本体分析的价值在于**否定**。以下每条都是「文档/直觉这么说 → 实采证明不是」。

### 5.1 陷阱：工号不是主键

- **直觉**：`fill_sales_dept` 458 行 = 458 个业务员，`SalesCode` 主键。
- **实采**：`SalesCode` 唯一 **455**，3 个工号各占 2 行：

| SalesCode | 姓名 | 两行的 `EmploymentStatus` |
|---|---|---|
| `C13437` | 闫晨 | 离职 / 在职 |
| `C13480` | 陈珺珺 | 在职 / 离职 |
| `C15083` | 辛清卫 | 在职 / 离职 |

- **后果**：`emp_dim` 若直接以 `sales_code` 建主键会丢 3 行（或报错）；若不去重就 join 事实表，这 3 人的签单/出货会**翻倍**。
- **处置**：维度以 `sales_code` 唯一化（同一工号取一条规范行，冲突进 dq），并显式记录「H1 内存在在职/离职双态」。

### 5.2 陷阱：达成分子必须先限定组织，否则分子是「全集团」而分母是「装备一事业群」

- **直觉**：科室预算 = 装备一事业群，宽表也是装备一，直接比。
- **实采**：宽表 `Orgname` 远不止装备一：

| 签单宽表 Orgname | 行数 | 出货宽表 Orgname | 行数 |
|---|---|---|---|
| 装备一事业群 | 7234 | 装备一事业部 | 7545 |
| 装备三事业部 | 181 | 装备三事业部 | 329 |
| 世纪鑫昌 | 45 | 世纪鑫昌 | 41 |
| 装备二-本部 | 37 | 装备二-本部 | 33 |
| （空） | 29 | 集团 | 10 |
| 装备五事业部 | 26 | 广州霏鸿 | 10 |
| 赫勒产品线 | 6 | 赫勒产品线 | 6 |
| 广州霏鸿 | 5 | （空） | 14 |

预算侧 `OrgName` **100% 是「装备一事业群」**（234/234）。
- **后果**：直接用全表算出机 = 440,464.85 万元，而预算 = 192,663.33 万元 → 228.6% 达成，虚高。
- **处置**：达成口径的分子 SHALL 限定 `org_name` 属装备一（与 `数据表与视图.md` 第五节默认过滤一致）；非装备一的行**保留在事实表**（其他场景要用），只是在达成切片上被过滤。

### 5.3 陷阱：空键伪命中（空串 join 空串 = 100% 命中假象）

- **直觉**：预算 `Fdept` 与宽表 `Fdept` 覆盖良好。
- **实采**：

```
预算 Fdept 空行        18 / 234
签单宽表 Fdept 空行   800 / 7563
出货宽表 Fdept 空行  1131 / 7988
「预算 Fdept ⊆ 宽表 Fdept」看似 234/234 全命中 —— 其中 18 行是空串对空串
剔除空串后：非空预算 Fdept 216 个值，在非空宽表 Fdept 中命中 216/216 ✅
```

- **后果**：朴素 `isin` 检查会给出「覆盖率 100%」的错觉，掩盖出货无法归属科室的事实（宽表 14.2%；本 change 采用的底层事件表基座为 1163/8036 = 14.5%）。
- **处置**：任何键覆盖检查与 join **必须先剔除空键**；未归属行不是错误，记入 dq 并保留（`unassigned` 桶），达成率分母只覆盖有预算的科室。

### 5.4 陷阱：两张预算表是同一笔预算的两个投影，**不可相加**

- **直觉**：科室预算 + 产品预算 = 总预算（两张表都叫「预算」）。
- **实采**：

| 指标 | 科室维度合计（万元） | 产品维度合计（万元） | 差 |
|---|---|---|---|
| 考核出机 | 192,663.33 | 192,663.36 | −0.03 |
| 管理出机 | 276,254.96 | 276,254.00 | +0.96 |
| 管理签单 | 297,809.11 | 297,810.37 | −1.26 |

逐月比对同样贴合（如 1 月：23,469.91 vs 23,469.90）。
- **结论**：**同一笔预算在「科室」和「产品类型」两个维度上的分摊**，不是两份预算。
- **后果**：相加得到 2 倍预算，达成率腰斩。
- **处置**：`Plan` 类内两条投影路径互斥使用 —— 问「科室达成」走科室投影，问「产品达成」走产品投影，**同一问题内只取一条**（公理 A5 的类型隔离 + 该项的显式约束）。

### 5.5 陷阱：预算只覆盖 6/22 个产品类型，分子不限定就虚高

- **直觉**：出货全额 vs 预算。
- **实采**：`fill_product_budget.ProductType` 只有 6 个值（型材机、通用钻攻机、小五轴、龙门机、立加、卧加），而 `ZPROD_TYPE` 有 **22** 个值。未覆盖的大头是 **3C钻攻机**（装备一口径下出货 121,039.14 万元，占 29.8%）。

装备一事业群口径下的逐步收敛（事实基座 = 底层事件表，组织字段自 `v_sales_emp_info` 回填）：

| 分子口径 | 出货含税（万元） | 对考核出机预算 192,663.33 | 对管理出机预算 276,254.96 |
|---|---|---|---|
| 全表 | 440,464.85 | 228.6% | 159.4% |
| + 限定装备一 | 406,474.68 | 211.0% | 147.1% |
| + 限定预算覆盖机型 | 285,435.54 | 148.2% | 103.3% |
| + 限定 Fdept 非空 | **251,576.35** | **130.6%** | **91.1%** |

签单同理：516,921.90 → 472,497.74 → 333,321.08 → **307,200.20**（管理签单预算 297,809.11 → **103.2%**）。
- **后果**：不收敛口径，达成率从 91% 变成 229%，差 2.5 倍，任何结论都不可信。
- **处置**：达成率 SHALL 显式声明分子口径四要素（组织 / 机型覆盖 / 科室非空 / 单位），并在产物里带上口径标记列，不允许「一个达成率数字」裸奔。

### 5.6 陷阱：出货表自带的 `fdept` 不能用来对齐预算

- **直觉**：发货表有 `fdept`，直接用它对齐预算。
- **实采**：发货表 `fdept` 唯一 **74** 个值（含 `美洲区`、`欧洲区`、`华东项目销售科(包括新人组)` 等 SAP 原始组织），只有 **4,814/8,036** 命中 `Fdept_add`。
- **对比**：出货**宽表**的 `Fdept`（来自组织视图）唯一 37 个值，非空 6,857 行，**且其非空值集合与预算非空 `Fdept` 互为子集**。
- **结论**：`dw_sale_order_saptest.fdept` 是 **SAP 出货组织**，与预算的**销售科室**是两套编码体系，只在 60% 行上偶然重合。
- **处置**：对齐键一律走宽表 `Fdept`（= `Fdept_add` 口径）。D6 决策「底层对象不单独建模」在此得到第二条独立证据支撑。

### 5.7 陷阱：负金额不是脏数据

- **实采**：签单 264 行负金额、出货 299 行负金额；`AuartName` 中 `退补退货` 207、`标准退货` 41、`换机退货` 16；出货 `ftag='销售退货'` 67 行。
- **后果**：若按「让数据纯」的直觉过滤负金额，会系统性高估达成。
- **处置**：负金额保留，并在 `dq_report` 里单列 `negative_amount_rows` 计数（是审计项不是剔除项）。

### 5.8 陷阱：`ftag='预算数据'` 的两副面孔（复核 D1）

| 对象 | `ftag='预算数据'` 行数 | `DataSources` | 金额 | 处置 |
|---|---|---|---|---|
| `dw_sale_order_saptest` | 30 | `填报` | 0（30 行零金额），但 `fbudget_amount` 30/30 非空 | **保留**（保底预算字段） |
| `v_sale_ship_order_emp_product` | 0（已剔除） | — | — | 剔除（D1 已生效） |

实采佐证：`ftag × DataSources = {销售发货:SAP 7939, 销售退货:SAP 67, 预算数据:填报 30}`，`ftag × fbudget_category = {…, 预算数据:保底 30}`。D1 判定正确，本文复核通过。

---

## 6. 能力问题（Competency Questions）验收

本体能不能用，看它能否回答业务真实问法。逐条验证并标注答案所需的关系路径：

| # | 业务问法 | 所需路径 | 是否可答 |
|---|---|---|---|
| CQ1 | X 科室 6 月管理出机达成多少？ | `Dept ⇢ measuredAgainst DeptBudgetMonth`；`Dept ← belongsTo SalesPerson ← shippedBy ShipOrderLine.inMonth` | ✅（需 §5.5 口径） |
| CQ2 | 哪些业务员连续 3 个月没签单？ | `SalesPerson(user_role=业务) ← signedBy SignOrderLine.inMonth` 按月求补集 | ✅ |
| CQ3 | 立加这个产品类型今年出货多少？ | `ProductType ← categorizedAs Product ← ofModel ShipOrderLine` | ✅ |
| CQ4 | 华南大区 Q2 签单 vs 出货比？ | `Area ← partOf Dept ← …` 两条事实上卷 | ✅ |
| CQ5 | 某客户买了哪些机型？ | `Customer ← contractParty/shipTo 事件 .ofModel Product` | ✅（需标注角色） |
| CQ6 | 产品类型预算达成？ | `ProductType ⇢ measuredAgainst ProductBudgetMonth` | ✅（与 CQ1 **不可同时相加**，§5.4） |
| CQ7 | 某主管手下是谁？ | `SalesPerson.supervisor_name`（属性） | ⚠️ **只能按姓名反查**，重名歧义，不建模为关系 |
| CQ8 | 某机型毛利率？ | 需 `FinalCost`（发货表有） | ⚠️ 成本不在允许查询四对象内，本 change 不建模 |
| CQ9 | 海外区达成？ | 预算里有「其他部门代卖/海外销售部」18 行 `Fdept` 为空 | ⚠️ 只能按 `Area` 对，不能按 `Dept` 对（§5.3） |

CQ7/CQ8/CQ9 的「⚠️」是本体边界，写进 [scenarios.md](./scenarios.md) 的「不要问」清单，GraphRAG 遇到时应显式拒绝并说明原因。

---

## 7. 冻结结论 → 交给建模

| # | 结论 | 落到 |
|---|---|---|
| 1 | 实体集合：业务员 / 科室 / 大区 / 事业部 / 客户 / 机型 / 产品类型 / 月 + 两类事件 + 两类计划 | `design.md` 图节点清单 |
| 2 | 科室规范键 = `Fdept_add`；出货表 `fdept` 禁用 | `schemas.md` |
| 3 | 机型规范键 = `ZPROD_NAME`；物料编码 `Fmate*`Number 降为属性 | `schemas.md` |
| 4 | 客户合并为一个实体，保留 `contractParty`/`shipTo` 角色区分 | `schemas.md` |
| 5 | 期间取 `Fyear/Fmonth`（签单）、`fyear/fperiod`（出货）；禁用日期反推 | `schemas.md` |
| 6 | `Plan ⊥ BusinessEvent`；两条预算投影互斥，不可相加 | 公理 A5 + `design.md` |
| 7 | 达成率四要素：组织 / 机型覆盖 / 科室非空 / 万元单位 | `metrics.md` |
| 8 | 空键不参与对照；未归属行进 dq 保留 | `design.md` 清洗规则 |
| 9 | 负金额保留；`ftag='预算数据'` 底层留、视图剔 | 清洗规则 |
| 10 | 主管、工厂、系列、合同名均**不**建节点 | 图节点清单 |
| 11 | 新增 5 个阻塞决策 B6–B10（组织口径 / 机型覆盖 / 空键 / 工号去重 / 预算互斥） | [grill.md](./grill.md)、[decisions.md](./decisions.md) |

---

## 附：实采证据索引

| 结论 | 证据 | 数值 |
|---|---|---|
| 工号不唯一 | `fill_sales_dept` | 458 行 / 455 唯一，3 工号双行 |
| `Fdept_add` 是预算口径 | 预算 Fdept ⊆ Fdept_add | 216/216 |
| `Fdept` 更细 | 两列不等 | 92 行 |
| 预算双投影同源 | 三指标合计 | 差 ≤ 1.26 万元 |
| 预算覆盖 6/22 类型 | `fill_product_budget` vs `ods_sap_cw_product` | 6 vs 22 |
| 组织边界影响 | 装备一 vs 全表 | 406,474.68 vs 440,464.85 万元 |
| 机型覆盖影响 | 覆盖机型后 | 285,435.54 万元 |
| 科室非空影响 | `Fdept` 非空后 | 251,576.35 万元 |
| 空键伪命中 | 宽表 `Fdept` 空 1131/7988（14.2%）；底表基座未归属 1163/8036 | 见 §5.3 |
| 未登记机型 | `fmate_type` ∉ `ZPROD_NAME` | 签单 20 / 出货 38 |
| 时间口径 | `Fmonth` vs 单据日期 | 100% / 99.63% |
| 负金额 | 签单 / 出货 | 264 / 299 行 |
