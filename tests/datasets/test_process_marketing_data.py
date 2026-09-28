"""Tests for datasets/process_marketing_data.py (OpenSpec marketing-data-processing).

Fixture CSVs only — never touches dataReport/dataset, never connects to the intranet.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

_DS = Path(__file__).resolve().parents[2] / "datasets"
import sys  # noqa: E402

if str(_DS) not in sys.path:
    sys.path.insert(0, str(_DS))

from process_marketing_data import (  # noqa: E402
    build_customer_dim,
    build_dept_budget_month,
    build_emp_dim,
    build_product_budget_month,
    build_product_dim,
    load_sources,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "marketing_min"


def _write_fixture(tmp_path: Path) -> Path:
    """两张最小夹具 CSV（组织 + 机型），足以覆盖键与单位规则。"""
    src = tmp_path / "src"
    src.mkdir(parents=True, exist_ok=True)

    (src / "fill_sales_dept.csv").write_text(
        "ID,SalesCode,SalesName,ForgName,SalesDept,Area,Fdept_add,Fdept,SupervisorName,"
        "Province,AffiliationCity,EmploymentStatus,User_role,Sales_Employment_Date\n"
        "1,C001,张三,装备一事业群,销售一部,华南大区,华南二区销售一科,华南二区销售一科一组,李四,广东省,深圳市,在职,业务,2020-01-01\n"
        "2,C002,李四,装备一事业群,销售一部,华南大区,华南二区销售一科,华南二区销售一科,王五,广东省,广州市,管理领导,2020-02-01\n"
        "3,C003,王五,装备一事业群,销售一部,华东大区,华东一区销售一科,华东一区销售一科,李四,江苏省,苏州市,离职,业务,2019-03-01\n"
        "4,C003,王五,装备一事业群,销售一部,华东大区,华东一区销售一科,华东一区销售一科,李四,江苏省,苏州市,在职,业务,2019-03-01\n",
        encoding="utf-8-sig",
    )
    (src / "v_sales_emp_info.csv").write_text(
        "SalesCode,SalesName,ForgName,SalesDept,Area,Fdept_add,SupervisorName,Province,"
        "AffiliationCity,entrydate,grade,EmploymentStatus,User_role,Sales_Employment_Date\n"
        "C001,张三,装备一事业群,销售一部,华南大区,华南二区销售一科,李四,广东省,深圳市,2020-01-01,03等,在职,业务,2020-01-01\n"
        "C002,李四,装备一事业群,销售一部,华南大区,华南二区销售一科,王五,广东省,广州市,2020-02-01,05等,管理领导,2020-02-01\n"
        "C003,王五,装备一事业群,销售一部,华东大区,华东一区销售一科,李四,江苏省,苏州市,2019-03-01,04等,在职,业务,2019-03-01\n",
        encoding="utf-8-sig",
    )
    (src / "ods_sap_cw_product.csv").write_text(
        "ZPROD_NAME,ZPROD_TYPE\nT-V856S,立加\nT-600S,通用钻攻机\n", encoding="utf-8-sig"
    )
    # 其余表：空壳（带表头），验证脚本不因缺列崩溃
    for name, header in [
        ("bi_vpsempinfo_month_2026H1.csv", "y1,m1,empcode,entrydate,grade,idcardnum,mobilephone,birthday"),
        ("dw_sgning_wide_table_2026H1.csv",
         "Orgname,SalesOrgName,SalesDocnoDate,Fyear,Fmonth,Auart,AuartName,Werks,ContractName,Docno,"
         "DocnoNum,KunnrCode,SalesCode,SalesName,FmateNumber,FmateSeris,FmateType,Area,Fqty,"
         "TotalMoneyFc,TotalMoneyFc_HS"),
        ("dw_sale_order_saptest_2026H1.csv",
         "ftag,SaleContractName,FORDER_TYPE,fbudget_category,DocNo,Org,BusinessDate,fyear,fperiod,"
         "fyearperiod,fsales_name,fdept,forg_name,fcust_number,fcust_name,fcust_short_name,fcust_area,"
         "fmate_number,fmate_name,fmate_model,fmate_attribute,fmate_series,fmate_strategy,fmate_type,"
         "fmate_main_category_name,fmate_category_number,fasset_category_name,FQTY,funit,FPRICEQTY,"
         "fsaleQty,TotalMoneyFC,TotalNetMoneyFC,TotalTaxFC,fbudget_qty,fbudget_amount,fsales_number,"
         "WERKS,Orgname,new_contract_Name,Area,TotalMoneyFC_HS,FinalCost,DataSources,factory"),
        ("v_sales_order_product_2026H1.csv", "SalesCode,Fdept,TotalMoneyFc_HS,ZPROD_TYPE"),
        ("v_sale_ship_order_emp_product_2026H1.csv", "SalesCode,Fdept,TotalMoneyFC_HS,ZPROD_TYPE,ftag"),
        ("fill_dept_budget_2026H1.csv",
         "ID,OrgName,ProductDept,SalesDept,Area,Area_fq,Fdept,Fyear,Fmonth,Assessment_Ship_Budget_Hs,"
         "Assessment_Ship_Budget,Management_Ship_Budget_Hs,Management_Ship_Budget,"
         "Management_SignedContract_Hs,Management_SignedContract"),
        ("fill_product_budget_2026H1.csv",
         "ID,OrgName,ProductName,ProductType,Fyear,Fmonth,Assessment_Ship_BudgetQty,"
         "Assessment_Ship_Budget,Assessment_Ship_Budget_Hs,Management_Ship_BudgetQty,"
         "Management_Ship_Budget,Management_Ship_Budget_Hs,GL_Management_SignedContractQty,"
         "GL_Management_SignedContract,GL_Management_SignedContract_Hs"),
    ]:
        (src / name).write_text(header + "\n", encoding="utf-8-sig")
    return src


def test_emp_dim_dedup_prefers_active(tmp_path: Path):
    src = _write_fixture(tmp_path)
    d = load_sources(src)
    dq: list[dict] = []
    emp = build_emp_dim(d, dq)

    # B9：C003 有在职/离职双行 -> 取在职；C001/C002 各一行
    assert len(emp) == 3
    row = emp[emp["sales_code"] == "C003"].iloc[0]
    assert row["employment_status"] == "在职"
    assert any(r["rule_id"] == "duplicate_sales_code" and r["count"] == 1 for r in dq)


def test_emp_dim_align_key_is_fdept_add(tmp_path: Path):
    src = _write_fixture(tmp_path)
    d = load_sources(src)
    dq: list[dict] = []
    emp = build_emp_dim(d, dq)

    # B5：规范键取 Fdept_add，不是更细的 Fdept
    assert emp[emp["sales_code"] == "C001"]["fdept"].iloc[0] == "华南二区销售一科"
    assert emp[emp["sales_code"] == "C001"]["fdept_raw"].iloc[0] == "华南二区销售一科一组"
    # 冲突（C001 两列不等）记 dq
    assert any(r["rule_id"] == "fdept_vs_fdept_add_conflict" and r["count"] == 1 for r in dq)


def test_product_dim_and_budget_shapes(tmp_path: Path):
    src = _write_fixture(tmp_path)
    d = load_sources(src)
    prod = build_product_dim(d)
    assert len(prod) == 2
    assert prod.set_index("zprod_name")["zprod_type"]["T-V856S"] == "立加"

    pb = build_product_budget_month(d)
    assert "gl_management_signed_contract_hs" in pb.columns
    db = build_dept_budget_month(d, [])
    assert "management_signed_contract_hs" in db.columns


def test_customer_dim_union(tmp_path: Path):
    src = _write_fixture(tmp_path)
    d = load_sources(src)
    cust = build_customer_dim(d, [])
    assert {"cust_code", "cust_name", "cust_area", "cust_role"} <= set(cust.columns)


def test_full_pipeline_on_real_output():
    """实跑产物存在时校验：无标签列 + 达成率基准 + 工号唯一。"""
    out = _DS / "processed" / "marketing_2026H1"
    if not (out / "dq_report.json").exists():
        pytest.skip("未生成清洗产物，先跑 datasets/process_marketing_data.py")

    report = json.loads((out / "dq_report.json").read_text(encoding="utf-8"))
    probe = report["achieve_probe"]

    # B1：不产标签列
    for name in ["emp_dim", "sign_order_line", "ship_order_line", "dept_budget_month"]:
        cols = set(pd.read_parquet(out / f"{name}.parquet").columns)
        assert not ({"label", "y", "split"} & cols), f"{name} 含禁列"

    # 达成率基准（默认口径）
    assert probe["achieve_pct_default"]["assessment_ship"] == 130.6
    assert probe["achieve_pct_default"]["management_ship"] == 91.1
    assert probe["achieve_pct_default"]["management_sign"] == 103.2

    # B9：工号唯一
    emp = pd.read_parquet(out / "emp_dim.parquet")
    assert emp["sales_code"].is_unique
    assert len(emp) == 455

    # D8：org_scope 三值完备
    for name in ["sign_order_line", "ship_order_line"]:
        f = pd.read_parquet(out / f"{name}.parquet")
        assert set(f["org_scope"].unique()) <= {"in_scope", "out_of_scope", "unknown"}, name

    # B6：in_scope 金额与探针一致
    ship = pd.read_parquet(out / "ship_order_line.parquet")
    assert round(float(ship.loc[ship["org_scope"] == "in_scope", "total_money_fc_hs_wan"].sum()), 2) == \
        probe["ship_layers"][1]["amount_wan"]

    # D3：PII 不进产物
    for f in out.glob("*.parquet"):
        assert not ({"idcardnum", "mobilephone", "birthday"} & set(pd.read_parquet(f).columns))

    # B10：两预算投影不通连（无共同键可 join）
    db = pd.read_parquet(out / "dept_budget_month.parquet")
    pb = pd.read_parquet(out / "product_budget_month.parquet")
    assert not ({"product_type"} & set(db.columns))
    assert not ({"fdept"} & set(pb.columns))
