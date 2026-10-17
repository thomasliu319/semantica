"""Marketing ``fix`` metric catalog aligned to 《装备一营销问数本体_v1.3.xml》.

This is the ``v=marketingfix`` metrics contract. It reuses the compute engine from
``marketing_metrics`` (cleaned parquet + caliber-aware achieve joins) but serves a
richer, ontology-aligned catalog:

- ``dimensions``    — the 8 dimension domains (D1..D8) and their 66 members.
- ``measures``      — the 37 base measures (M01..M37) with caliber/unit/SQL refs.
- ``derived``       — the 22 derived metrics (X01..X22) with formulas and units.
- ``time_semantics``— the v1.3 time-span accumulation semantics (累计/截止/同期/连续窗口)
                      with the confirming rulings (RULE-1..5) and constraints (CT11/13/14/17).

The compute surface (``grains`` / ``bases_by_source`` / ``presets``) is unchanged
so every existing query keeps working; the two extra presets here (单均签单金额,
人均订单数) correspond to X16 / X22 and are computable from the sign bases.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from . import marketing_metrics as _m1

# ---------------------------------------------------------------------------
# 维度域与维度成员（v1.3 §2，8 大维度域，66 个维度成员）
# ---------------------------------------------------------------------------
DIMENSIONS: list[dict[str, Any]] = [
    {
        "code": "D1",
        "label_zh": "时间维度",
        "cn_alias": "年月;期间;时间口径",
        "description": "回答“截止目前/某月/1-某月”的时间口径：当期单月、年初至某月累计、截止目前；同比基准固定为去年同期。",
        "members": [
            {"code": "VM_Year", "label_zh": "年份"},
            {"code": "VM_Month", "label_zh": "月份"},
            {"code": "VM_YearMonth", "label_zh": "年月（复合时间键）"},
            {"code": "VM_CurrentMonth", "label_zh": "当期某月"},
            {"code": "VM_Ytd", "label_zh": "年初至某月累计"},
            {"code": "VM_AsOfNow", "label_zh": "截止目前"},
            {"code": "VM_LastYearSamePeriod", "label_zh": "去年同期"},
            {"code": "VM_OrderDate", "label_zh": "订单日期"},
            {"code": "VM_PostingDate", "label_zh": "过账/出货日期"},
            {"code": "VM_ConsecutiveSpan", "label_zh": "连续月份跨度"},
        ],
    },
    {
        "code": "D2",
        "label_zh": "组织维度",
        "cn_alias": "组织;部门;机构",
        "description": "五级组织下钻：事业部 > 产品部 > 销售部 > 大区 > 分区 > 科室。",
        "members": [
            {"code": "VM_BusinessDivision", "label_zh": "事业部"},
            {"code": "VM_ProductDept", "label_zh": "产品部"},
            {"code": "VM_SalesDept", "label_zh": "销售部"},
            {"code": "VM_Region", "label_zh": "大区"},
            {"code": "VM_SubRegion", "label_zh": "分区"},
            {"code": "VM_Section", "label_zh": "科室"},
            {"code": "VM_SalesCompany", "label_zh": "销售公司"},
            {"code": "VM_OrgLevel", "label_zh": "组织层级"},
        ],
    },
    {
        "code": "D3",
        "label_zh": "人员维度",
        "cn_alias": "业务员;销售人员;人",
        "description": "业务员个体与人员口径：工号为主键，姓名仅作辅助校验；支撑人均类、连续未签单/未出机、入职满3个月口径。",
        "members": [
            {"code": "VM_SalesCode", "label_zh": "业务员工号"},
            {"code": "VM_SalesName", "label_zh": "业务员姓名"},
            {"code": "VM_Role", "label_zh": "销售or领导"},
            {"code": "VM_EmploymentStatus", "label_zh": "在职状态"},
            {"code": "VM_EntryDate", "label_zh": "入职日期"},
            {"code": "VM_Tenure", "label_zh": "在职月数"},
            {"code": "VM_ContinuousNoOrder", "label_zh": "连续未签单"},
            {"code": "VM_ContinuousNoShip", "label_zh": "连续未出机"},
            {"code": "VM_Supervisor", "label_zh": "直接上级"},
            {"code": "VM_Province", "label_zh": "省份"},
            {"code": "VM_AffiliationCity", "label_zh": "归属地城市"},
            {"code": "VM_EhrProfile", "label_zh": "人事属性"},
            {"code": "VM_Headcount", "label_zh": "业务员人数"},
        ],
    },
    {
        "code": "D4",
        "label_zh": "产品维度",
        "cn_alias": "产品;机型;物料",
        "description": "产品四级下钻：产品线 > 产品类型 > 机型 > 物料/产品名称；立加/钻攻机分组为基础口径。",
        "members": [
            {"code": "VM_ProductLine", "label_zh": "产品线"},
            {"code": "VM_ProductType", "label_zh": "产品类型"},
            {"code": "VM_MachineModel", "label_zh": "机型"},
            {"code": "VM_ProductName", "label_zh": "产品名称/描述"},
            {"code": "VM_MaterialCode", "label_zh": "物料编码"},
            {"code": "VM_ProductConfig", "label_zh": "产品配置"},
            {"code": "VM_MachineGroup", "label_zh": "机型分组"},
            {"code": "VM_TopNModel", "label_zh": "机型 TOP N"},
        ],
    },
    {
        "code": "D5",
        "label_zh": "客户维度",
        "cn_alias": "客户;终端",
        "description": "客户编码/名称/简称、新老客户、3C口径、客户累计立加出机台数分层。",
        "members": [
            {"code": "VM_CustomerCode", "label_zh": "客户编码"},
            {"code": "VM_CustomerName", "label_zh": "客户名称"},
            {"code": "VM_CustomerShortName", "label_zh": "客户简称"},
            {"code": "VM_CustomerType", "label_zh": "客户类型"},
            {"code": "VM_Industry3C", "label_zh": "行业口径 3C"},
            {"code": "VM_CustomerShipTier", "label_zh": "客户累计立加出机台数分层"},
        ],
    },
    {
        "code": "D6",
        "label_zh": "单据维度",
        "cn_alias": "单据;订单;发货",
        "description": "签单与发货两类业务单据：一笔签单可对应多次发货/退货（1:N），行级唯一键防重复计数。",
        "members": [
            {"code": "VM_OrderNo", "label_zh": "订单号"},
            {"code": "VM_OrderLine", "label_zh": "订单行号"},
            {"code": "VM_OrderType", "label_zh": "订单类型"},
            {"code": "VM_ContractNo", "label_zh": "纸质合同号"},
            {"code": "VM_ShipOrReturn", "label_zh": "销售发货/销售退货"},
            {"code": "VM_BudgetOrActual", "label_zh": "预算or实际出货"},
            {"code": "VM_GoodsStrategy", "label_zh": "成品or其他"},
            {"code": "VM_Factory", "label_zh": "工厂维度"},
        ],
    },
    {
        "code": "D7",
        "label_zh": "预算维度",
        "cn_alias": "目标;计划;Budget",
        "description": "目标值来源：部门预算（组织颗粒度）+ 产品预算（产品颗粒度），按月年存放，含管理/考核、出机/签单、含税/不含税、金额/台数。",
        "members": [
            {"code": "VM_DeptBudget", "label_zh": "部门预算"},
            {"code": "VM_ProductBudget", "label_zh": "产品预算"},
            {"code": "VM_BudgetPeriod", "label_zh": "预算期间"},
            {"code": "VM_BudgetOrgGrain", "label_zh": "预算组织颗粒度"},
            {"code": "VM_BudgetProductGrain", "label_zh": "预算产品颗粒度"},
        ],
    },
    {
        "code": "D8",
        "label_zh": "口径维度",
        "cn_alias": "统计口径;业务口径",
        "description": "穿越所有指标的开关型维度：业务/税务/行业/客户/数据/单据/物料/人员口径。问数时必须显式解析。",
        "members": [
            {"code": "VC_BusinessCaliber", "label_zh": "业务口径"},
            {"code": "VC_TaxCaliber", "label_zh": "税务口径"},
            {"code": "VC_IndustryCaliber", "label_zh": "行业口径"},
            {"code": "VC_CustomerCaliber", "label_zh": "客户口径"},
            {"code": "VC_DataCaliber", "label_zh": "数据口径"},
            {"code": "VC_DocCaliber", "label_zh": "单据口径"},
            {"code": "VC_GoodsCaliber", "label_zh": "物料口径"},
            {"code": "VC_PersonCaliber", "label_zh": "人员口径"},
        ],
    },
]

# ---------------------------------------------------------------------------
# 基础度量（v1.3 §8，37 个 M01..M37）
# `base_id` 指向本目录可计算的 bases_by_source 键；None 表示当前清洗数据未建模。
# ---------------------------------------------------------------------------
MEASURES: list[dict[str, Any]] = [
    {"code": "M01", "label_zh": "管理出机金额_不含税", "category": "出机金额", "caliber": "管理口径×销售发货×不含税", "unit": "元", "base_id": "ship_amount_fc"},
    {"code": "M02", "label_zh": "管理出机金额_含税", "category": "出机金额", "caliber": "管理口径×销售发货×含税", "unit": "元", "base_id": "ship_amount_fc_hs"},
    {"code": "M03", "label_zh": "考核出机金额_不含税", "category": "出机金额", "caliber": "考核口径×销售发货×不含税", "unit": "元", "base_id": "ship_amount_fc"},
    {"code": "M04", "label_zh": "考核出机金额_含税", "category": "出机金额", "caliber": "考核口径×销售发货×含税", "unit": "元", "base_id": "ship_amount_fc_hs"},
    {"code": "M05", "label_zh": "管理出机台数", "category": "出机台数", "caliber": "管理口径", "unit": "台", "base_id": "ship_qty"},
    {"code": "M06", "label_zh": "考核出机台数", "category": "出机台数", "caliber": "考核口径", "unit": "台", "base_id": "ship_qty"},
    {"code": "M07", "label_zh": "管理立加出机台数", "category": "立加出机", "caliber": "管理口径×机型∈立加", "unit": "台", "base_id": None},
    {"code": "M08", "label_zh": "考核立加出机台数", "category": "立加出机", "caliber": "考核口径×机型∈立加", "unit": "台", "base_id": None},
    {"code": "M09", "label_zh": "立加出机金额_不含税", "category": "立加出机", "caliber": "机型∈立加", "unit": "元", "base_id": None},
    {"code": "M10", "label_zh": "钻攻机出机台数", "category": "钻攻机出机", "caliber": "机型∈通用钻攻机", "unit": "台", "base_id": None},
    {"code": "M11", "label_zh": "钻攻机出机金额_不含税", "category": "钻攻机出机", "caliber": "机型∈通用钻攻机", "unit": "元", "base_id": None},
    {"code": "M12", "label_zh": "管理签单金额_不含税", "category": "签单金额", "caliber": "管理口径×不含税", "unit": "元", "base_id": "sign_amount_fc"},
    {"code": "M13", "label_zh": "管理签单金额_含税", "category": "签单金额", "caliber": "管理口径×含税", "unit": "元", "base_id": "sign_amount_fc_hs"},
    {"code": "M14", "label_zh": "管理签单台数", "category": "签单台数", "caliber": "管理口径", "unit": "台", "base_id": "sign_qty"},
    {"code": "M15", "label_zh": "管理立加签单台数", "category": "立加签单", "caliber": "管理口径×机型∈立加", "unit": "台", "base_id": None},
    {"code": "M16", "label_zh": "产品类型出机台数", "category": "产品结构", "caliber": "按产品类型分组", "unit": "台", "base_id": "ship_qty"},
    {"code": "M17", "label_zh": "产品类型出机金额", "category": "产品结构", "caliber": "按产品类型分组", "unit": "元", "base_id": "ship_amount_fc"},
    {"code": "M18", "label_zh": "机型签单台数", "category": "机型榜单", "caliber": "按机型分组", "unit": "台", "base_id": "sign_qty"},
    {"code": "M19", "label_zh": "机型签单金额", "category": "机型榜单", "caliber": "按机型分组", "unit": "元", "base_id": "sign_amount_fc"},
    {"code": "M20", "label_zh": "新客户签单金额", "category": "客户结构", "caliber": "新客户", "unit": "元", "base_id": None},
    {"code": "M21", "label_zh": "老客户签单金额", "category": "客户结构", "caliber": "老客户", "unit": "元", "base_id": None},
    {"code": "M22", "label_zh": "在职业务员人数", "category": "人数", "caliber": "期末在职（累计期取第N月末快照）", "unit": "人", "base_id": None},
    {"code": "M23", "label_zh": "目标_管理出机金额_不含税", "category": "目标", "caliber": "部门预算", "unit": "万元", "base_id": None},
    {"code": "M24", "label_zh": "目标_管理出机金额_含税", "category": "目标", "caliber": "部门预算", "unit": "万元", "base_id": "management_ship_budget_hs"},
    {"code": "M25", "label_zh": "目标_考核出机金额_不含税", "category": "目标", "caliber": "部门预算", "unit": "万元", "base_id": "assessment_ship_budget_hs"},
    {"code": "M26", "label_zh": "目标_管理签单金额_不含税", "category": "目标", "caliber": "部门预算", "unit": "万元", "base_id": "management_signed_contract_hs"},
    {"code": "M27", "label_zh": "目标_管理立加签单台数", "category": "目标", "caliber": "部门预算", "unit": "台", "base_id": None},
    {"code": "M28", "label_zh": "目标_考核立加出机台数", "category": "目标", "caliber": "部门预算", "unit": "台", "base_id": None},
    {"code": "M29", "label_zh": "目标_产品类型考核出机台数", "category": "目标", "caliber": "产品预算", "unit": "台", "base_id": None},
    {"code": "M30", "label_zh": "目标_产品类型管理签单台数", "category": "目标", "caliber": "产品预算", "unit": "台", "base_id": None},
    {"code": "M31", "label_zh": "出机成本", "category": "成本", "caliber": "出机口径×成本（PI-11待确认）", "unit": "元", "base_id": None},
    {"code": "M32", "label_zh": "退货金额_不含税", "category": "退货", "caliber": "单据口径=销售退货", "unit": "元", "base_id": None},
    {"code": "M33", "label_zh": "退货台数", "category": "退货", "caliber": "单据口径=销售退货", "unit": "台", "base_id": None},
    {"code": "M34", "label_zh": "签单订单数", "category": "订单量", "caliber": "按订单号去重", "unit": "单", "base_id": "sign_docs"},
    {"code": "M35", "label_zh": "出机订单数", "category": "订单量", "caliber": "按订单号去重", "unit": "单", "base_id": "ship_docs"},
    {"code": "M36", "label_zh": "签单客户数", "category": "客户数", "caliber": "按客户编码去重", "unit": "家", "base_id": None},
    {"code": "M37", "label_zh": "出机客户数", "category": "客户数", "caliber": "按客户编码去重", "unit": "家", "base_id": "ship_customers"},
]

# ---------------------------------------------------------------------------
# 派生指标（v1.3 §9，22 个 X01..X22）
# `preset_ids` 指向本目录 presets 中可计算的配方；`supported` 表示当前可计算。
# ---------------------------------------------------------------------------
DERIVED_METRICS: list[dict[str, Any]] = [
    {"code": "X01", "label_zh": "达成率", "cn_alias": "达成率", "formula": "达成 / 目标 × 100%", "unit": "%", "caliber": "目标值与达成值需先对齐同一时间口径与组织颗粒度", "supported": True, "preset_ids": ["assessment_ship_achieve_pct", "management_ship_achieve_pct", "management_sign_achieve_pct"]},
    {"code": "X02", "label_zh": "同比", "cn_alias": "同比;同比率", "formula": "(本期 - 去年同期) / 去年同期 × 100%", "unit": "%", "caliber": "去年同期按同月数或同累计月数对齐", "supported": False},
    {"code": "X03", "label_zh": "人均达成", "cn_alias": "人均金额;人均台数", "formula": "达成(:期间) / 第:N月末在职业务员数", "unit": "元/人", "caliber": "分母取期末在职（口径定案③）", "supported": True, "preset_ids": ["ship_per_emp", "sign_per_emp"]},
    {"code": "X04", "label_zh": "人均同比", "cn_alias": "人均同比率", "formula": "(本期人均 - 去年同期人均) / 去年同期人均", "unit": "%", "caliber": "分子按同累计月数对齐", "supported": False},
    {"code": "X05", "label_zh": "人数占比", "cn_alias": "占比", "formula": "满足条件人数 / 在职业务员总数", "unit": "%", "caliber": "", "supported": False},
    {"code": "X06", "label_zh": "达成率排名", "cn_alias": "排名", "formula": "在比较范围内按达成率降序", "unit": "名次", "caliber": "比较范围默认全部科室，可限定大区", "supported": False},
    {"code": "X07", "label_zh": "连续未签单月数", "cn_alias": "连续不签单", "formula": "按月判断签单为0的连续自然月数", "unit": "月", "caliber": "需连续无断点", "supported": False},
    {"code": "X08", "label_zh": "连续未出机月数", "cn_alias": "连续不出机", "formula": "按月判断出机为0的连续自然月数", "unit": "月", "caliber": "", "supported": False},
    {"code": "X09", "label_zh": "满3个月业务人均", "cn_alias": "3个月及以上人均", "formula": "达成(:期间) / 第:N月末在职且满3个月业务员数", "unit": "元/人", "caliber": "分母取第N月末在职且入职满3个月（口径定案③）", "supported": False},
    {"code": "X10", "label_zh": "剔除10台客户后出机台数", "cn_alias": "剔除口径", "formula": "剔除客户累计立加出机≥10台订单", "unit": "台", "caliber": "", "supported": False},
    {"code": "X11", "label_zh": "剔除20台客户后出机台数", "cn_alias": "剔除口径", "formula": "剔除客户累计立加出机≥20台订单", "unit": "台", "caliber": "", "supported": False},
    {"code": "X12", "label_zh": "客户累计立加出机台数", "cn_alias": "客户分层", "formula": "按客户汇总历史立加出机台数", "unit": "台", "caliber": "时间范围需覆盖全部历史", "supported": False},
    {"code": "X13", "label_zh": "毛利额", "cn_alias": "毛利", "formula": "出机金额 − 出机成本", "unit": "元", "caliber": "成本与金额必须同税口径（PI-11）", "supported": False},
    {"code": "X14", "label_zh": "毛利率", "cn_alias": "毛利率", "formula": "毛利额 / 出机金额", "unit": "%", "caliber": "", "supported": False},
    {"code": "X15", "label_zh": "退货率", "cn_alias": "退货率", "formula": "退货金额 / 发货金额", "unit": "%", "caliber": "退货冲减口径待确认（PI-12）", "supported": False},
    {"code": "X16", "label_zh": "单均签单金额", "cn_alias": "客单价", "formula": "签单金额 / 签单订单数", "unit": "元/单", "caliber": "订单数口径待确认（PI-13）", "supported": True, "preset_ids": ["avg_sign_order_amount"]},
    {"code": "X17", "label_zh": "新客户数", "cn_alias": "新增客户", "formula": "新客户去重计数", "unit": "家", "caliber": "新客户判定规则待确认（PI-06）", "supported": False},
    {"code": "X18", "label_zh": "预算偏差率", "cn_alias": "偏差率", "formula": "(实际 − 预算) / 预算 × 100%", "unit": "%", "caliber": "正值为超预算", "supported": False},
    {"code": "X19", "label_zh": "环比", "cn_alias": "环比率;MoM", "formula": "(本期 − 上期) / 上期 × 100%", "unit": "%", "caliber": "上期指相邻上一个自然月", "supported": True, "preset_ids": []},
    {"code": "X20", "label_zh": "时间进度", "cn_alias": "序时进度", "formula": "已过月数 / 12", "unit": "%", "caliber": "用于与累计达成率对比判断进度滞后", "supported": False},
    {"code": "X21", "label_zh": "客户集中度", "cn_alias": "CR10;集中度", "formula": "TOP N 客户金额 / 全部客户金额", "unit": "%", "caliber": "", "supported": False},
    {"code": "X22", "label_zh": "人均订单数", "cn_alias": "出单率", "formula": "签单订单数 / 在职人数", "unit": "单/人", "caliber": "", "supported": True, "preset_ids": ["orders_per_emp"]},
]

# 新增可计算配方（对应 X16 / X22），叠加在 v1 的 PRESETS 之上。
EXTRA_PRESETS: list[dict[str, Any]] = [
    {"id": "avg_sign_order_amount", "op": "div", "a": "sign_amount_fc_hs_wan", "b": "sign_docs", "name_zh": "单均签单金额", "domain": "sign"},
    {"id": "orders_per_emp", "op": "div", "a": "sign_docs", "b": "sign_emps", "name_zh": "人均订单数", "domain": "sign"},
]


# ---------------------------------------------------------------------------
# 时间跨度累加语义（v1.3 重点：biz:timeKind 五值 + 口径定案 RULE + 约束 CT）
# ---------------------------------------------------------------------------
# v1.3 的时间口径是「累计/截止/同期/连续窗口」的组合空间，核心规则见：
#   - D1 维度域（VM_Ytd / VM_CurrentMonth / VM_AsOfNow / VM_LastYearSamePeriod / VM_ConsecutiveSpan）
#   - 口径定案 RULE-1（区间 BETWEEN）／RULE-4（闭区间含当月）／RULE-3（人均分母期末在职）
#   - 约束 CT13（区间）/ CT17（「截止」消歧）/ CT11（补月）/ CT14（期末在职）
#   - 时间键逻辑关联 R11/R12/R21/R25/R26（预算 vs 实际，默认 LEFT JOIN）
TIME_KINDS: list[dict[str, str]] = [
    {"kind": "ytd", "label_zh": "1-N月累计", "sql": "fyear = :Y AND fperiod BETWEEN 1 AND :N",
     "rule": "闭区间 [1, N] 含当月（RULE-4）；:N 必须可传参，禁止写死截止月"},
    {"kind": "month", "label_zh": "当期某月", "sql": "fyear = :Y AND fperiod = :M",
     "rule": "仅当问句明确指向单一月份时才用 =，禁止把累计降级为单月"},
    {"kind": "asof", "label_zh": "截止目前", "sql": "fyearperiod = (SELECT MAX(fyearperiod) FROM :fact)",
     "rule": "仅当问句为「截止目前/最新」且未给月份时使用（取最新完整月）"},
    {"kind": "series", "label_zh": "逐月序列", "sql": "GROUP BY 年月，缺月补 0",
     "rule": "趋势类先构建月份骨架表 LEFT JOIN，无数据月份补 0（CT11）"},
    {"kind": "span", "label_zh": "连续回溯窗口", "sql": "fperiod BETWEEN :N - :K + 1 AND :N",
     "rule": "「连续 K 月」回溯窗口，上界为截止月（CT17③）"},
]

TIME_RULINGS: list[dict[str, str]] = [
    {"code": "RULE-1", "label_zh": "时间条件用区间（BETWEEN）",
     "text": "凡「1-N月」「截止N月」一律生成 fyear=:Y AND fperiod BETWEEN 1 AND :N，不得降级为单月切片；只有「当期某月」才用 =。"},
    {"code": "RULE-4", "label_zh": "「1-N月累计」含当月 N",
     "text": "区间为闭区间 [1, N]，N 计入：1-5 月累计即 1、2、3、4、5 月，共 5 个月。"},
    {"code": "RULE-3", "label_zh": "累计期人均分母取期末在职",
     "text": "人均类指标（X03/X04/X09）在累计口径下，分母取第 :N 月末 EHR 在职快照；不取期间月均、不取期内任职去重。"},
    {"code": "RULE-2", "label_zh": "预算表以 JOIN 参与取数",
     "text": "目标值来自预算表必须以 JOIN 接入，默认 LEFT JOIN 保证期间与组织不被交集裁剪（INNER JOIN 会「只剩 N 月」）。"},
]

TIME_CONSTRAINTS: list[dict[str, str]] = [
    {"code": "CT13", "label_zh": "时间条件必须用区间（BETWEEN）",
     "text": "累计口径下 :N 必须作为参数传入，不得写死月份；禁止降级为 fperiod=:N 单月切片。"},
    {"code": "CT17", "label_zh": "「截止」措辞消歧",
     "text": "①截止目前/最新→当期最新完整月；②截止M月/1-N月→BETWEEN 1 AND :N；③连续K月→回溯窗口 :N-:K+1 AND :N。"},
    {"code": "CT11", "label_zh": "时间序列补月",
     "text": "趋势类问题先构建月份骨架表并与事实表 LEFT JOIN，无数据月份补 0 而非丢弃，避免趋势断点被误读为归零。"},
    {"code": "CT14", "label_zh": "累计期人均分母取期末在职",
     "text": "第 :N 月末快照；同比场景分子按同累计月数对齐，分母各自取本期/去年同期的第 :N 月末。"},
]

TIME_KEY_JOINS: list[dict[str, str]] = [
    {"code": "R11", "label_zh": "部门预算年月 ↔ 签单宽表年月",
     "note": "Fyear+Fmonth 复合时间键，默认 LEFT JOIN（口径定案②）"},
    {"code": "R12", "label_zh": "部门预算年月 ↔ 发货宽表年月",
     "note": "Fyear+Fmonth ↔ fyear+fperiod 复合时间键，默认 LEFT JOIN"},
    {"code": "R21", "label_zh": "EHR 人员快照年月 ↔ 部门预算年月",
     "note": "y1+m1 ↔ Fyear+Fmonth（按当月在职快照）"},
    {"code": "R25", "label_zh": "产品预算年月 ↔ 签单宽表年月",
     "note": "Fyear+Fmonth 复合时间键，默认 LEFT JOIN"},
    {"code": "R26", "label_zh": "产品预算年月 ↔ 发货宽表年月",
     "note": "Fyear+Fmonth ↔ fyear+fperiod 复合时间键，默认 LEFT JOIN"},
]

TIME_SEMANTICS: dict[str, Any] = {
    "time_kinds": TIME_KINDS,
    "rulings": TIME_RULINGS,
    "constraints": TIME_CONSTRAINTS,
    "time_key_joins": TIME_KEY_JOINS,
}


def catalog() -> dict[str, Any]:
    """v1.3-aligned catalog: base compute surface + dimensions/measures/derived/time."""
    base = _m1.catalog()
    base["dimensions"] = DIMENSIONS
    base["measures"] = MEASURES
    base["derived"] = DERIVED_METRICS
    base["time_semantics"] = TIME_SEMANTICS
    # 叠加 X16/X22 两个可计算配方（去重保序）。
    seen = {p["id"] for p in base["presets"]}
    base["presets"] = list(base["presets"]) + [p for p in EXTRA_PRESETS if p["id"] not in seen]
    return base


def compose(
    *,
    grain: str,
    bases: Sequence[str] | None = None,
    derived: Sequence[Mapping[str, Any]] | None = None,
    apply_presets: bool = True,
    limit: int = 200,
    frames: dict | None = None,
) -> dict[str, Any]:
    """Compute exactly like the marketing v1 engine (same parquet + caliber rules)."""
    return _m1.compose(
        grain=grain,
        bases=bases,
        derived=derived,
        apply_presets=apply_presets,
        limit=limit,
        frames=frames,
    )


def stamp_metrics(bases: Mapping[str, Any], *, extra: Sequence[dict[str, Any]] | None = None) -> dict[str, Any]:
    return _m1.stamp_metrics(bases, extra=extra)
