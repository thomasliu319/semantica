"""Clean csj_dw marketing CSV (2026 H1) into parquet tables + dq report.

OpenSpec change: `marketing-data-processing`.
Decisions: B1 clean_only / B2 hybrid / B3 wan / B4 fdept_all / B5 fdept_add /
D1 keep_bottom_drop_view / D2 dedup_full_row / D3 drop_pii / D4 parquet /
D5 wan_only / D6 dims_only; round-2 B6 org_scope_filter / B7 budget_covered_only /
B8 drop_from_achieve / B9 prefer_active / B10 mutually_exclusive /
D7 keep_and_count / D8 org_scope_column.

Reads `dataReport/dataset/*.csv` read-only. Writes
`datasets/processed/marketing_2026H1/*.parquet` + `dq_report.json` +
`model_star.json`. Never writes back into `dataReport/dataset/` except
`_semantic/metric_catalog.json` (D4).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

_DS = Path(__file__).resolve().parent
_ROOT = _DS.parent
DEFAULT_SRC = _ROOT / "dataReport" / "dataset"
DEFAULT_OUT = _DS / "processed" / "marketing_2026H1"
SEMANTIC_CATALOG = DEFAULT_SRC / "_semantic" / "metric_catalog.json"

FORBIDDEN_COLS = {"label", "y", "split"}
NULL_TOKENS = {"", "NULL", "null", "Null", "nan", "NaN", "None", "NONE"}
IN_SCOPE_ORG_PREFIX = "装备一事业"
PII_COLS = {"idcardnum", "mobilephone", "birthday"}

# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, encoding="utf-8-sig", keep_default_na=False)


def norm_text(s: pd.Series) -> pd.Series:
    """统一空值：NULL / 空串 / 空白 -> ''。"""
    out = s.fillna("").astype(str).str.strip()
    return out.where(~out.isin(NULL_TOKENS), "")


def norm_date(s: pd.Series) -> pd.Series:
    """日期标准化 YYYY-MM-DD；无法解析则保留空。"""
    txt = norm_text(s)
    parsed = pd.to_datetime(txt, errors="coerce", format="%Y-%m-%d")
    fallback = pd.to_datetime(txt, errors="coerce")
    parsed = parsed.fillna(fallback)
    return parsed.dt.strftime("%Y-%m-%d").fillna("")


def to_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(norm_text(s).replace("", None), errors="coerce")


def round_num(s: pd.Series, nd: int) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").round(nd)


def wan(yuan: pd.Series) -> pd.Series:
    """元 -> 万元（B3）。"""
    return (pd.to_numeric(yuan, errors="coerce") / 10000).round(4)


def snake(name: str) -> str:
    out = []
    for i, ch in enumerate(name):
        if ch.isupper() and i > 0:
            prev = name[i - 1]
            nxt = name[i + 1] if i + 1 < len(name) else ""
            if not prev.isupper() or (nxt and nxt.islower()):
                out.append("_")
        out.append(ch.lower())
    return "".join(out)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_parquet(df: pd.DataFrame, path: Path) -> None:
    bad = FORBIDDEN_COLS.intersection(df.columns)
    if bad:
        raise ValueError(f"{path.name} 含禁列 {sorted(bad)}（B1 clean_only）")
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


# --------------------------------------------------------------------------- #
# load
# --------------------------------------------------------------------------- #


def load_sources(src: Path) -> dict[str, pd.DataFrame]:
    files = {
        "fill_sales_dept": "fill_sales_dept.csv",
        "v_sales_emp_info": "v_sales_emp_info.csv",
        "bi_vpsempinfo_month": "bi_vpsempinfo_month_2026H1.csv",
        "dw_sgning_wide_table": "dw_sgning_wide_table_2026H1.csv",
        "dw_sale_order_saptest": "dw_sale_order_saptest_2026H1.csv",
        "ods_sap_cw_product": "ods_sap_cw_product.csv",
        "v_sales_order_product": "v_sales_order_product_2026H1.csv",
        "v_sale_ship_order_emp_product": "v_sale_ship_order_emp_product_2026H1.csv",
        "fill_dept_budget": "fill_dept_budget_2026H1.csv",
        "fill_product_budget": "fill_product_budget_2026H1.csv",
    }
    return {k: read_csv(src / v) for k, v in files.items()}


# --------------------------------------------------------------------------- #
# dimensions
# --------------------------------------------------------------------------- #


def build_emp_dim(d: dict[str, pd.DataFrame], dq: list[dict]) -> pd.DataFrame:
    fsd = d["fill_sales_dept"].copy()
    vei = d["v_sales_emp_info"].copy()

    df = pd.DataFrame(
        {
            "sales_code": norm_text(fsd["SalesCode"]),
            "sales_name": norm_text(fsd["SalesName"]),
            "forg_name": norm_text(fsd["ForgName"]),
            "sales_dept": norm_text(fsd["SalesDept"]),
            "area": norm_text(fsd["Area"]),
            "fdept": norm_text(fsd["Fdept_add"]),  # B5：规范键 = Fdept_add
            "fdept_raw": norm_text(fsd["Fdept"]),  # 仅对照
            "supervisor_name": norm_text(fsd["SupervisorName"]),
            "province": norm_text(fsd["Province"]),
            "affiliation_city": norm_text(fsd["AffiliationCity"]),
            "employment_status": norm_text(fsd["EmploymentStatus"]),
            "user_role": norm_text(fsd["User_role"]),
            "sales_employment_date": norm_date(fsd["Sales_Employment_Date"]),
        }
    )

    # EHR 血缘：只取 entrydate / grade（非 PII）
    vei_key = pd.DataFrame(
        {
            "sales_code": norm_text(vei["SalesCode"]),
            "entrydate": norm_date(vei["entrydate"]),
            "grade": norm_text(vei["grade"]),
        }
    ).drop_duplicates("sales_code")
    df = df.merge(vei_key, on="sales_code", how="left")

    # B9 prefer_active：同工号取「在职」行
    n_before = len(df)
    dup_mask = df.duplicated("sales_code", keep=False)
    dup_codes = sorted(df.loc[dup_mask, "sales_code"].unique())
    if dup_codes:
        dq.append(
            {
                "rule_id": "duplicate_sales_code",
                "table": "emp_dim",
                "count": len(dup_codes),
                "example_keys": dup_codes[:10],
                "note": "同一工号多行的在职/离职双态；按 B9 prefer_active 取在职行",
            }
        )
    df["_rank"] = (df["employment_status"] != "在职").astype(int)
    df = df.sort_values(["sales_code", "_rank"]).drop_duplicates("sales_code", keep="first")
    df = df.drop(columns=["_rank"]).reset_index(drop=True)

    dq.append(
        {
            "rule_id": "emp_dim_row_reduction",
            "table": "emp_dim",
            "count": n_before - len(df),
            "example_keys": [],
            "note": f"fill_sales_dept {n_before} 行 -> {len(df)} 个工号",
        }
    )

    conflict = df[(df["fdept"] != "") & (df["fdept_raw"] != "") & (df["fdept"] != df["fdept_raw"])]
    dq.append(
        {
            "rule_id": "fdept_vs_fdept_add_conflict",
            "table": "emp_dim",
            "count": int(len(conflict)),
            "example_keys": conflict["sales_code"].head(5).tolist(),
            "note": "Fdept 与 Fdept_add 不等；对齐键锁定 Fdept_add（B5）",
        }
    )
    return df


def build_dept_dim(d: dict[str, pd.DataFrame], emp: pd.DataFrame, dq: list[dict]) -> pd.DataFrame:
    fdb = d["fill_dept_budget"].copy()
    bud = pd.DataFrame(
        {
            "fdept": norm_text(fdb["Fdept"]),
            "org_name": norm_text(fdb["OrgName"]),
            "product_dept": norm_text(fdb["ProductDept"]),
            "sales_dept": norm_text(fdb["SalesDept"]),
            "area": norm_text(fdb["Area"]),
            "area_fq": norm_text(fdb["Area_fq"]),
        }
    )
    empty_budget = int((bud["fdept"] == "").sum())
    bud = bud[bud["fdept"] != ""].drop_duplicates()

    from_emp = (
        emp[["fdept", "forg_name", "sales_dept", "area"]]
        .drop_duplicates("fdept")
        .rename(columns={"forg_name": "org_name"})
    )
    from_emp["product_dept"] = ""
    from_emp["area_fq"] = ""

    df = pd.concat([bud, from_emp], ignore_index=True)
    agg = {c: "first" for c in df.columns if c != "fdept"}
    df = df.groupby("fdept", as_index=False).agg(agg).reset_index(drop=True)

    dq.append(
        {
            "rule_id": "budget_rows_without_dept",
            "table": "dept_budget_month",
            "count": empty_budget,
            "example_keys": norm_text(fdb.loc[norm_text(fdb["Fdept"]) == "", "SalesDept"]).unique().tolist()[:5],
            "note": "其他部门代卖（项目/海外/3C销售部）预算无科室；保留不入 dept_dim（B8）",
        }
    )
    return df


def build_product_dim(d: dict[str, pd.DataFrame]) -> pd.DataFrame:
    p = d["ods_sap_cw_product"].copy()
    df = pd.DataFrame(
        {
            "zprod_name": norm_text(p["ZPROD_NAME"]),
            "zprod_type": norm_text(p["ZPROD_TYPE"]),
        }
    )
    return df.drop_duplicates("zprod_name").reset_index(drop=True)


def build_customer_dim(d: dict[str, pd.DataFrame], dq: list[dict]) -> pd.DataFrame:
    sg = d["dw_sgning_wide_table"]
    sh = d["dw_sale_order_saptest"]

    sign = pd.DataFrame({"cust_code": norm_text(sg["KunnrCode"])}).drop_duplicates()
    sign["cust_role"] = "contract_party"
    ship = pd.DataFrame(
        {
            "cust_code": norm_text(sh["fcust_number"]),
            "cust_name": norm_text(sh["fcust_name"]),
            "cust_area": norm_text(sh["fcust_area"]),
        }
    ).drop_duplicates("cust_code")
    ship["cust_role"] = "ship_to"

    df = sign.merge(ship, on="cust_code", how="outer", suffixes=("", "_s"))
    df["cust_name"] = df.get("cust_name", pd.Series("", index=df.index)).fillna("")
    df["cust_area"] = df.get("cust_area", pd.Series("", index=df.index)).fillna("")
    both = df["cust_role"].notna() & df["cust_role_s"].notna() if "cust_role_s" in df else None
    if both is not None:
        df.loc[both, "cust_role"] = "both"
    df["cust_role"] = df["cust_role"].fillna("ship_to")
    df = df[["cust_code", "cust_name", "cust_area", "cust_role"]].reset_index(drop=True)

    only_sign = int((df["cust_role"] == "contract_party").sum())
    only_ship = int((df["cust_role"] == "ship_to").sum())
    dq.append(
        {
            "rule_id": "customer_key_domain_gap",
            "table": "customer_dim",
            "count": only_sign + only_ship,
            "example_keys": [],
            "note": f"仅签单客户 {only_sign}（已签未出）；仅出货客户 {only_ship}（往期/直发）",
        }
    )
    return df


def build_month_dim(d: dict[str, pd.DataFrame]) -> pd.DataFrame:
    sg = d["dw_sgning_wide_table"]
    sh = d["dw_sale_order_saptest"]
    m = pd.concat(
        [
            pd.DataFrame({"year": norm_text(sg["Fyear"]), "month": norm_text(sg["Fmonth"])}),
            pd.DataFrame({"year": norm_text(sh["fyear"]), "month": norm_text(sh["fperiod"])}),
        ]
    )
    m = m[(m["year"] != "") & (m["month"] != "")].drop_duplicates()
    m["month"] = m["month"].astype(int)
    m = m.sort_values(["year", "month"]).reset_index(drop=True)
    m["month_label"] = m["year"] + "-" + m["month"].astype(str).str.zfill(2)
    return m[["year", "month", "month_label"]]


# --------------------------------------------------------------------------- #
# facts
# --------------------------------------------------------------------------- #


def _org_scope(orgname: pd.Series) -> pd.Series:
    o = norm_text(orgname)
    return pd.Series(
        [
            "in_scope" if v.startswith(IN_SCOPE_ORG_PREFIX) else ("unknown" if v == "" else "out_of_scope")
            for v in o
        ],
        index=o.index,
    )


def _attach_org(df: pd.DataFrame, emp: pd.DataFrame, code_col: str) -> pd.DataFrame:
    """按工号回填组织字段（等价于宽表投影，但保留底层行）。"""
    cols = ["sales_code", "sales_name", "forg_name", "sales_dept", "area", "fdept", "user_role", "employment_status"]
    org = emp[cols].rename(
        columns={
            "sales_code": "_key",
            "sales_name": "sales_name_org",
            "forg_name": "org_name",
        }
    )
    out = df.merge(org, left_on=code_col, right_on="_key", how="left").drop(columns=["_key"])
    for c in ["sales_name_org", "org_name", "sales_dept", "area", "fdept", "user_role", "employment_status"]:
        out[c] = out[c].fillna("")
    return out


def build_sign_order_line(d: dict[str, pd.DataFrame], emp: pd.DataFrame, prod: pd.DataFrame, dq: list[dict]) -> pd.DataFrame:
    sg = d["dw_sgning_wide_table"].copy()
    n0 = len(sg)
    sg = sg.drop_duplicates()  # D2

    df = pd.DataFrame(
        {
            "docno": norm_text(sg["Docno"]),
            "docno_num": norm_text(sg["DocnoNum"]),
            "contract_name": norm_text(sg["ContractName"]),
            "sales_docno_date": norm_date(sg["SalesDocnoDate"]),
            "year": norm_text(sg["Fyear"]),  # 公理 A8：期间取 Fyear/Fmonth
            "month": to_num(sg["Fmonth"]).astype("Int64"),
            "auart": norm_text(sg["Auart"]),
            "auart_name": norm_text(sg["AuartName"]),
            "werks": norm_text(sg["Werks"]),
            "sales_code": norm_text(sg["SalesCode"]),
            "sales_name": norm_text(sg["SalesName"]),
            "orgname_src": norm_text(sg["Orgname"]),
            "sales_org_name": norm_text(sg["SalesOrgName"]),
            "cust_code": norm_text(sg["KunnrCode"]),
            "fmate_number": norm_text(sg["FmateNumber"]),
            "fmate_seris": norm_text(sg["FmateSeris"]),
            "zprod_name": norm_text(sg["FmateType"]),
            "area_src": norm_text(sg["Area"]),
            "fqty": round_num(to_num(sg["Fqty"]), 3),
            "total_money_fc": round_num(to_num(sg["TotalMoneyFc"]), 2),
            "total_money_fc_hs": round_num(to_num(sg["TotalMoneyFc_HS"]), 2),
        }
    )
    df["total_money_fc_hs_wan"] = wan(df["total_money_fc_hs"])
    df = _attach_org(df, emp, "sales_code")

    # 机型分类回填（ZPROD_NAME -> ZPROD_TYPE）
    pmap = prod.set_index("zprod_name")["zprod_type"].to_dict()
    df["zprod_type"] = df["zprod_name"].map(pmap).fillna("")
    df["model_unregistered"] = ((df["zprod_name"] != "") & (df["zprod_type"] == "")).astype(int)

    df["org_scope"] = _org_scope(df["orgname_src"])
    df["cust_role"] = "contract_party"

    unassigned = int((df["fdept"] == "").sum())
    unreg = int(df["model_unregistered"].sum())
    neg = int((df["total_money_fc_hs"] < 0).sum())
    dq.append({"rule_id": "sign_dedup_full_row", "table": "sign_order_line", "count": n0 - len(sg),
               "example_keys": [], "note": "完全重复行去重（D2）"})
    dq.append({"rule_id": "sign_unassigned_dept_rows", "table": "sign_order_line", "count": unassigned,
               "example_keys": [], "note": "SalesCode 未匹配组织视图，fdept 为空；保留不入达成（B8）"})
    dq.append({"rule_id": "sign_unregistered_model_rows", "table": "sign_order_line", "count": unreg,
               "example_keys": df.loc[df["model_unregistered"] == 1, "zprod_name"].unique().tolist()[:8],
               "note": "fmate_type 不在 ods_sap_cw_product；保留事实、机型置空"})
    dq.append({"rule_id": "sign_negative_amount_rows", "table": "sign_order_line", "count": neg,
               "example_keys": [], "note": "退货/退补为有效发生体，保留（D7）"})
    return df


def build_ship_order_line(d: dict[str, pd.DataFrame], emp: pd.DataFrame, prod: pd.DataFrame, dq: list[dict]) -> pd.DataFrame:
    sh = d["dw_sale_order_saptest"].copy()
    n0 = len(sh)
    sh = sh.drop_duplicates()  # D2

    df = pd.DataFrame(
        {
            "ftag": norm_text(sh["ftag"]),
            "docno": norm_text(sh["DocNo"]),
            "forder_type": norm_text(sh["FORDER_TYPE"]),
            "business_date": norm_date(sh["BusinessDate"]),
            "year": norm_text(sh["fyear"]),  # 公理 A8：期间取 fyear/fperiod
            "month": to_num(sh["fperiod"]).astype("Int64"),
            "sales_code": norm_text(sh["fsales_number"]),
            "sales_name": norm_text(sh["fsales_name"]),
            "fdept_sap": norm_text(sh["fdept"]),  # 禁用：SAP 出货组织，非预算科室（ontology §5.6）
            "orgname_src": norm_text(sh["Orgname"]),
            "forg_name": norm_text(sh["forg_name"]),
            "cust_code": norm_text(sh["fcust_number"]),
            "cust_name": norm_text(sh["fcust_name"]),
            "cust_area": norm_text(sh["fcust_area"]),
            "fmate_number": norm_text(sh["fmate_number"]),
            "fmate_name": norm_text(sh["fmate_name"]),
            "fmate_series": norm_text(sh["fmate_series"]),
            "zprod_name": norm_text(sh["fmate_type"]),
            "area_src": norm_text(sh["Area"]),
            "factory": norm_text(sh["factory"]),
            "fqty": round_num(to_num(sh["FQTY"]), 3),
            "total_money_fc": round_num(to_num(sh["TotalMoneyFC"]), 2),
            "total_money_fc_hs": round_num(to_num(sh["TotalMoneyFC_HS"]), 2),
            "data_sources": norm_text(sh["DataSources"]),
            "fbudget_category": norm_text(sh["fbudget_category"]),
            "fbudget_qty": round_num(to_num(sh["fbudget_qty"]), 3),
            "fbudget_amount": round_num(to_num(sh["fbudget_amount"]), 2),
        }
    )
    df["total_money_fc_hs_wan"] = wan(df["total_money_fc_hs"])
    df = _attach_org(df, emp, "sales_code")
    df = df.sort_values(["docno", "ftag"]).reset_index(drop=True)
    df["line_no"] = df.groupby("docno").cumcount() + 1

    pmap = prod.set_index("zprod_name")["zprod_type"].to_dict()
    df["zprod_type"] = df["zprod_name"].map(pmap).fillna("")
    df["model_unregistered"] = ((df["zprod_name"] != "") & (df["zprod_type"] == "")).astype(int)

    df["org_scope"] = _org_scope(df["orgname_src"])
    df["cust_role"] = "ship_to"

    kept_budget = int((df["ftag"] == "预算数据").sum())
    unassigned = int((df["fdept"] == "").sum())
    unreg = int(df["model_unregistered"].sum())
    neg = int((df["total_money_fc_hs"] < 0).sum())
    dq.append({"rule_id": "ship_dedup_full_row", "table": "ship_order_line", "count": n0 - len(sh),
               "example_keys": [], "note": "完全重复行去重（D2）"})
    dq.append({"rule_id": "ship_keep_budget_placeholder", "table": "ship_order_line", "count": kept_budget,
               "example_keys": [], "note": "ftag='预算数据' 底层保留（含 fbudget_* 保底字段，D1）"})
    dq.append({"rule_id": "ship_unassigned_dept_rows", "table": "ship_order_line", "count": unassigned,
               "example_keys": [], "note": "fsales_number 未匹配组织视图；保留不入达成（B8）"})
    dq.append({"rule_id": "ship_unregistered_model_rows", "table": "ship_order_line", "count": unreg,
               "example_keys": df.loc[df["model_unregistered"] == 1, "zprod_name"].unique().tolist()[:8],
               "note": "fmate_type 不在 ods_sap_cw_product；保留事实、机型置空"})
    dq.append({"rule_id": "ship_negative_amount_rows", "table": "ship_order_line", "count": neg,
               "example_keys": [], "note": "销售退货/退补为有效发生体，保留（D7）"})
    return df


# --------------------------------------------------------------------------- #
# budgets (Plan — 与事实星物理不通连, B10)
# --------------------------------------------------------------------------- #


def build_dept_budget_month(d: dict[str, pd.DataFrame], dq: list[dict]) -> pd.DataFrame:
    f = d["fill_dept_budget"].copy().drop_duplicates()
    df = pd.DataFrame(
        {
            "fdept": norm_text(f["Fdept"]),
            "year": norm_text(f["Fyear"]),
            "month": to_num(f["Fmonth"]).astype("Int64"),
            "org_name": norm_text(f["OrgName"]),
            "product_dept": norm_text(f["ProductDept"]),
            "sales_dept": norm_text(f["SalesDept"]),
            "area": norm_text(f["Area"]),
            "area_fq": norm_text(f["Area_fq"]),
            "assessment_ship_budget_hs": round_num(to_num(f["Assessment_Ship_Budget_Hs"]), 2),
            "management_ship_budget_hs": round_num(to_num(f["Management_Ship_Budget_Hs"]), 2),
            "management_signed_contract_hs": round_num(to_num(f["Management_SignedContract_Hs"]), 2),
            "assessment_ship_budget": round_num(to_num(f["Assessment_Ship_Budget"]), 2),
            "management_ship_budget": round_num(to_num(f["Management_Ship_Budget"]), 2),
            "management_signed_contract": round_num(to_num(f["Management_SignedContract"]), 2),
        }
    )
    dq.append(
        {
            "rule_id": "dept_budget_unit_wan",
            "table": "dept_budget_month",
            "count": len(df),
            "example_keys": [],
            "note": "单位万元含税，保持原值不 x10000（D5）；与宽表比较须先 /10000",
        }
    )
    return df


def build_product_budget_month(d: dict[str, pd.DataFrame]) -> pd.DataFrame:
    f = d["fill_product_budget"].copy().drop_duplicates()
    return pd.DataFrame(
        {
            "product_type": norm_text(f["ProductType"]),
            "year": norm_text(f["Fyear"]),
            "month": to_num(f["Fmonth"]).astype("Int64"),
            "org_name": norm_text(f["OrgName"]),
            "product_name": norm_text(f["ProductName"]),
            "assessment_ship_budget_hs": round_num(to_num(f["Assessment_Ship_Budget_Hs"]), 2),
            "management_ship_budget_hs": round_num(to_num(f["Management_Ship_Budget_Hs"]), 2),
            "gl_management_signed_contract_hs": round_num(to_num(f["GL_Management_SignedContract_Hs"]), 2),
            "assessment_ship_budget": round_num(to_num(f["Assessment_Ship_Budget"]), 2),
            "management_ship_budget": round_num(to_num(f["Management_Ship_Budget"]), 2),
            "gl_management_signed_contract": round_num(to_num(f["GL_Management_SignedContract"]), 2),
        }
    )


# --------------------------------------------------------------------------- #
# 口径探针（审计用，不是分析报告 — B1 clean_only）
# --------------------------------------------------------------------------- #


def achieve_probe(ship: pd.DataFrame, sign: pd.DataFrame, dept_bud: pd.DataFrame, prod_bud: pd.DataFrame) -> dict:
    covered = sorted(prod_bud["product_type"].dropna().unique().tolist())
    layers = []

    def probe(df: pd.DataFrame, amt: str) -> list[dict]:
        out = []
        masks = [
            ("全宽表", pd.Series(True, index=df.index)),
            ("+组织=装备一", df["org_scope"] == "in_scope"),
            ("+机型=预算覆盖", (df["org_scope"] == "in_scope") & df["zprod_type"].isin(covered)),
            (
                "+科室非空(默认)",
                (df["org_scope"] == "in_scope") & df["zprod_type"].isin(covered) & (df["fdept"] != ""),
            ),
        ]
        for name, m in masks:
            out.append({"layer": name, "amount_wan": round(float(df.loc[m, amt].sum()), 2)})
        return out

    ship_layers = probe(ship, "total_money_fc_hs_wan")
    sign_layers = probe(sign, "total_money_fc_hs_wan")

    defult_ship = ship_layers[-1]["amount_wan"]
    default_sign = sign_layers[-1]["amount_wan"]
    budgets = {
        "assessment_ship_budget_hs": round(float(dept_bud["assessment_ship_budget_hs"].sum()), 2),
        "management_ship_budget_hs": round(float(dept_bud["management_ship_budget_hs"].sum()), 2),
        "management_signed_contract_hs": round(float(dept_bud["management_signed_contract_hs"].sum()), 2),
    }

    def pct(a: float, b: float) -> float | None:
        return round(a / b * 100, 1) if b else None

    return {
        "note": "口径审计探针，不是达成率报告（B1 clean_only）。默认口径 = 组织 in_scope ∧ 机型∈预算覆盖 ∧ 科室非空 ∧ 万元含税。",
        "budget_covered_product_types": covered,
        "budget_total_wan": budgets,
        "ship_layers": ship_layers,
        "sign_layers": sign_layers,
        "achieve_pct_default": {
            "assessment_ship": pct(defult_ship, budgets["assessment_ship_budget_hs"]),
            "management_ship": pct(defult_ship, budgets["management_ship_budget_hs"]),
            "management_sign": pct(default_sign, budgets["management_signed_contract_hs"]),
        },
        "product_budget_total_wan": {
            "assessment_ship_budget_hs": round(float(prod_bud["assessment_ship_budget_hs"].sum()), 2),
            "management_ship_budget_hs": round(float(prod_bud["management_ship_budget_hs"].sum()), 2),
            "gl_management_signed_contract_hs": round(float(prod_bud["gl_management_signed_contract_hs"].sum()), 2),
        },
    }


# --------------------------------------------------------------------------- #
# star model descriptor
# --------------------------------------------------------------------------- #


def build_model_star() -> dict:
    return {
        "model": "marketing_2026H1",
        "window": "2026-01~06",
        "design": "star + plan-star（两星物理不通连，A5 Plan ⊥ BusinessEvent）",
        "facts": {
            "sign_order_line": {"grain": "签单行", "key": ["docno", "docno_num"], "rows_hint": 7558},
            "ship_order_line": {"grain": "出货行", "key": ["docno", "line_no"], "rows_hint": 8036},
        },
        "dims": {
            "emp_dim": {"grain": "业务员", "key": "sales_code"},
            "dept_dim": {"grain": "科室", "key": "fdept"},
            "product_dim": {"grain": "机型", "key": "zprod_name"},
            "customer_dim": {"grain": "客户", "key": "cust_code"},
            "month_dim": {"grain": "自然月", "key": ["year", "month"]},
        },
        "plan": {
            "dept_budget_month": {"grain": "科室×月", "key": ["fdept", "year", "month"], "unit": "万元含税"},
            "product_budget_month": {"grain": "产品类型×月", "key": ["product_type", "year", "month"], "unit": "万元含税"},
        },
        "links_fact_to_dim": [
            ["sign_order_line", "sales_code", "emp_dim"],
            ["sign_order_line", "fdept", "dept_dim"],
            ["sign_order_line", "zprod_name", "product_dim"],
            ["sign_order_line", "cust_code", "customer_dim"],
            ["sign_order_line", ["year", "month"], "month_dim"],
            ["ship_order_line", "sales_code", "emp_dim"],
            ["ship_order_line", "fdept", "dept_dim"],
            ["ship_order_line", "zprod_name", "product_dim"],
            ["ship_order_line", "cust_code", "customer_dim"],
            ["ship_order_line", ["year", "month"], "month_dim"],
        ],
        "links_plan_measure_against": [
            ["dept_budget_month", ["fdept", "year", "month"], "query-time only"],
            ["product_budget_month", ["product_type", "year", "month"], "query-time only"],
        ],
        "forbidden_joins": [
            "dept_budget_month × product_budget_month（同一笔预算的两个投影，B10 mutually_exclusive）",
            "任何以空串为键的对照（B8）",
            "使用 ship_order_line.fdept_sap 对齐预算（ontology §5.6）",
        ],
        "hierarchy": ["business_group(org_name)", "area", "dept(fdept)", "emp(sales_code)"],
    }


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #


def main() -> None:
    ap = argparse.ArgumentParser(description="Clean csj_dw marketing CSV into parquet")
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    out: Path = args.out
    d = load_sources(args.src)
    dq: list[dict] = []

    emp = build_emp_dim(d, dq)
    dept = build_dept_dim(d, emp, dq)
    prod = build_product_dim(d)
    cust = build_customer_dim(d, dq)
    month = build_month_dim(d)

    sign = build_sign_order_line(d, emp, prod, dq)
    ship = build_ship_order_line(d, emp, prod, dq)

    dept_bud = build_dept_budget_month(d, dq)
    prod_bud = build_product_budget_month(d)

    # PII 审计（D3）
    ehr = d["bi_vpsempinfo_month"]
    dq.append(
        {
            "rule_id": "pii_columns_dropped",
            "table": "bi_vpsempinfo_month",
            "count": len(ehr),
            "example_keys": sorted(PII_COLS),
            "note": "EHR 月表只作血缘，PII 不进任何 parquet（D3）",
        }
    )
    dq.append(
        {
            "rule_id": "budget_projections_not_joined",
            "table": "dept_budget_month / product_budget_month",
            "count": 2,
            "example_keys": [],
            "note": "两张预算表合计差 <=1.26 万元 = 同一笔预算的两个投影，不建连接（B10）",
        }
    )

    write_parquet(emp, out / "emp_dim.parquet")
    write_parquet(dept, out / "dept_dim.parquet")
    write_parquet(prod, out / "product_dim.parquet")
    write_parquet(cust, out / "customer_dim.parquet")
    write_parquet(month, out / "month_dim.parquet")
    write_parquet(sign, out / "sign_order_line.parquet")
    write_parquet(ship, out / "ship_order_line.parquet")
    write_parquet(dept_bud, out / "dept_budget_month.parquet")
    write_parquet(prod_bud, out / "product_budget_month.parquet")

    probe = achieve_probe(ship, sign, dept_bud, prod_bud)
    report = {
        "window": "2026-01~06",
        "source": str(args.src),
        "tables": {
            "emp_dim": len(emp),
            "dept_dim": len(dept),
            "product_dim": len(prod),
            "customer_dim": len(cust),
            "month_dim": len(month),
            "sign_order_line": len(sign),
            "ship_order_line": len(ship),
            "dept_budget_month": len(dept_bud),
            "product_budget_month": len(prod_bud),
        },
        "rules": dq,
        "achieve_probe": probe,
    }
    write_json(out / "dq_report.json", report)
    write_json(out / "model_star.json", build_model_star())

    catalog = {
        "window": "2026-01~06",
        "unit": {"fact": "元", "derived_wan": "万元", "budget": "万元含税"},
        "measures": {
            "management_ship": {"expr": "SUM(ship_order_line.total_money_fc_hs_wan)", "unit": "万元"},
            "assessment_ship": {"expr": "SUM(ship_order_line.total_money_fc_hs_wan)", "unit": "万元"},
            "management_sign": {"expr": "SUM(sign_order_line.total_money_fc_hs_wan)", "unit": "万元"},
        },
        "budgets": {
            "management_ship_budget_hs": "dept_budget_month / product_budget_month",
            "assessment_ship_budget_hs": "dept_budget_month / product_budget_month",
            "management_signed_contract_hs": "dept_budget_month",
            "gl_management_signed_contract_hs": "product_budget_month",
        },
        "achieve_filter": ["org_scope=in_scope", "zprod_type in budget_covered", "fdept非空", "万元含税"],
        "not_comparable": ["预算两投影相加", "元与万元直接相除", "签单与出货混算"],
    }
    write_json(SEMANTIC_CATALOG, catalog)

    print(f"out -> {out}")
    for k, v in report["tables"].items():
        print(f"  {k}: {v}")
    print("achieve_pct_default:", probe["achieve_pct_default"])


if __name__ == "__main__":
    main()
