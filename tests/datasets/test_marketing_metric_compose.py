"""Compose marketing measures into derived ratios. Synthetic frames — no parquet required."""

from __future__ import annotations

import pandas as pd
import pytest

from semantica.explorer.marketing_metrics import catalog, compose, stamp_metrics


def _marketing_frames() -> dict[str, pd.DataFrame]:
    ship = pd.DataFrame(
        [
            # in_scope + covered + fdept -> counted (100 万)
            {"month": "2026-01", "org_scope": "in_scope", "zprod_type": "立加", "fdept": "华南二区销售一科",
             "total_money_fc_hs_wan": 100.0, "total_money_fc_hs": 1000000.0, "total_money_fc": 1000000.0,
             "fqty": 1, "docno": "D1", "sales_code": "C001", "sales_name": "张三",
             "cust_code": "K1", "cust_name": "客户一", "area": "华南大区", "zprod_name": "T-V856S"},
            # out_of_scope -> excluded by element 1 (org)
            {"month": "2026-01", "org_scope": "out_of_scope", "zprod_type": "立加", "fdept": "华南二区销售一科",
             "total_money_fc_hs_wan": 50.0, "total_money_fc_hs": 500000.0, "total_money_fc": 500000.0,
             "fqty": 1, "docno": "D2", "sales_code": "C002", "sales_name": "李四",
             "cust_code": "K2", "cust_name": "客户二", "area": "华东大区", "zprod_name": "T-V856S"},
            # not budget-covered -> excluded by element 2 (product type)
            {"month": "2026-01", "org_scope": "in_scope", "zprod_type": "3C钻攻机", "fdept": "华南二区销售一科",
             "total_money_fc_hs_wan": 30.0, "total_money_fc_hs": 300000.0, "total_money_fc": 300000.0,
             "fqty": 1, "docno": "D3", "sales_code": "C001", "sales_name": "张三",
             "cust_code": "K3", "cust_name": "客户三", "area": "华南大区", "zprod_name": "T-600"},
            # empty fdept -> excluded by element 3 (non-empty dept)
            {"month": "2026-01", "org_scope": "in_scope", "zprod_type": "立加", "fdept": "",
             "total_money_fc_hs_wan": 20.0, "total_money_fc_hs": 200000.0, "total_money_fc": 200000.0,
             "fqty": 1, "docno": "D4", "sales_code": "C003", "sales_name": "王五",
             "cust_code": "K4", "cust_name": "客户四", "area": "华南大区", "zprod_name": "T-V856S"},
            {"month": "2026-02", "org_scope": "in_scope", "zprod_type": "立加", "fdept": "华南二区销售一科",
             "total_money_fc_hs_wan": 200.0, "total_money_fc_hs": 2000000.0, "total_money_fc": 2000000.0,
             "fqty": 2, "docno": "D5", "sales_code": "C001", "sales_name": "张三",
             "cust_code": "K1", "cust_name": "客户一", "area": "华南大区", "zprod_name": "T-V856S"},
        ]
    )
    sign = pd.DataFrame(
        [
            {"month": "2026-01", "org_scope": "in_scope", "zprod_type": "立加", "fdept": "华南二区销售一科",
             "total_money_fc_hs_wan": 100.0, "total_money_fc_hs": 1000000.0, "total_money_fc": 1000000.0,
             "fqty": 1, "docno": "S1", "sales_code": "C001", "sales_name": "张三", "cust_code": "K1"},
            {"month": "2026-01", "org_scope": "out_of_scope", "zprod_type": "立加", "fdept": "华南二区销售一科",
             "total_money_fc_hs_wan": 900.0, "total_money_fc_hs": 9000000.0, "total_money_fc": 9000000.0,
             "fqty": 1, "docno": "S2", "sales_code": "C002", "sales_name": "李四", "cust_code": "K2"},
        ]
    )
    dept_budget = pd.DataFrame(
        [
            {"fdept": "华南二区销售一科", "month": "2026-01", "area": "华南大区",
             "assessment_ship_budget_hs": 200.0, "management_ship_budget_hs": 300.0,
             "management_signed_contract_hs": 200.0},
            {"fdept": "华南二区销售一科", "month": "2026-02", "area": "华南大区",
             "assessment_ship_budget_hs": 200.0, "management_ship_budget_hs": 300.0,
             "management_signed_contract_hs": 200.0},
        ]
    )
    product_budget = pd.DataFrame(
        [
            {"product_type": "立加", "month": "2026-01", "assessment_ship_budget_hs": 200.0,
             "management_ship_budget_hs": 300.0, "gl_management_signed_contract_hs": 200.0},
            {"product_type": "立加", "month": "2026-02", "assessment_ship_budget_hs": 200.0,
             "management_ship_budget_hs": 300.0, "gl_management_signed_contract_hs": 200.0},
        ]
    )
    return {"ship": ship, "sign": sign, "dept_budget": dept_budget, "product_budget": product_budget}


def test_month_achieve_applies_4_element_caliber():
    result = compose(
        grain="month",
        bases=["ship_amount_fc_hs_wan"],
        derived=[{"id": "assessment_ship_achieve_pct", "op": "achieve",
                  "a": "ship_amount_fc_hs_wan", "b": "assessment_ship_budget_hs"}],
        apply_presets=False,
        frames=_marketing_frames(),
    )
    by_month = {row["month"]: row for row in result["rows"]}

    # 2026-01：只有 in_scope + 立加 + fdept 非空的 100 万计入分子
    jan = by_month["2026-01"]
    assert jan["assessment_ship_achieve_numerator_wan"] == 100
    assert jan["assessment_ship_achieve_denominator_wan"] == 200
    assert jan["assessment_ship_achieve_pct"] == 50.0

    feb = by_month["2026-02"]
    assert feb["assessment_ship_achieve_pct"] == 100.0


def test_sign_month_achieve_management_sign():
    result = compose(
        grain="sign_month",
        bases=["sign_amount_fc_hs_wan"],
        derived=[{"id": "management_sign_achieve_pct", "op": "achieve",
                  "a": "sign_amount_fc_hs_wan", "b": "management_signed_contract_hs"}],
        apply_presets=False,
        frames=_marketing_frames(),
    )
    jan = next(row for row in result["rows"] if row["month"] == "2026-01")
    assert jan["management_sign_achieve_pct"] == 50.0
    assert jan["management_sign_achieve_numerator_wan"] == 100


def test_product_type_share_preset():
    result = compose(
        grain="product_type",
        bases=["ship_amount_fc_hs_wan"],
        apply_presets=True,
        frames=_marketing_frames(),
    )
    rows = {row["zprod_type"]: row for row in result["rows"]}
    # 份额是全口径结构占比（不套达成四要素）：立加 (100+50+20+200) / 400, 3C钻攻机 30 / 400
    assert rows["立加"]["product_type_share"] == pytest.approx(370 / 400, abs=1e-4)
    assert rows["3C钻攻机"]["product_type_share"] == pytest.approx(30 / 400, abs=1e-4)


def test_rejects_forbidden_id_and_unknown_grain():
    with pytest.raises(ValueError, match="invalid derived id"):
        compose(
            grain="month",
            bases=["ship_amount_fc_hs_wan"],
            derived=[{"id": "gross_margin", "op": "div",
                      "a": "ship_amount_fc_hs_wan", "b": "ship_amount_fc_hs_wan"}],
            apply_presets=False,
            frames=_marketing_frames(),
        )
    with pytest.raises(ValueError, match="invalid derived id"):
        compose(
            grain="month",
            bases=["ship_amount_fc_hs_wan"],
            derived=[{"id": "毛利", "op": "div",
                      "a": "ship_amount_fc_hs_wan", "b": "ship_amount_fc_hs_wan"}],
            apply_presets=False,
            frames=_marketing_frames(),
        )
    with pytest.raises(ValueError, match="unknown grain"):
        compose(grain="not_a_grain", apply_presets=False, frames=_marketing_frames())


def test_achieve_requires_budget_projection():
    # model 粒度没有预算投影，achieve 应报错
    with pytest.raises(ValueError, match="no budget projection"):
        compose(
            grain="model",
            bases=["ship_amount_fc_hs_wan"],
            derived=[{"id": "assessment_ship_achieve_pct", "op": "achieve",
                      "a": "ship_amount_fc_hs_wan", "b": "assessment_ship_budget_hs"}],
            apply_presets=False,
            frames=_marketing_frames(),
        )


def test_budget_projections_never_joined():
    # B10：任一粒度的预算投影来源唯一，科室预算与产品预算不会同时出现
    cat = catalog()
    for grain in cat["grains"]:
        budget = grain.get("budget")
        if budget:
            assert budget["source"] in {"dept_budget", "product_budget"}


def test_stamp_metrics_skips_share_and_achieve():
    stamped = stamp_metrics({"ship_amount_fc_hs_wan": 200, "ship_emps": 10})
    assert stamped["ship_per_emp"] == pytest.approx(20.0)
    assert "product_type_share" not in stamped
    assert "assessment_ship_achieve_pct" not in stamped


def test_full_h1_baseline_on_real_output():
    """产物存在时校验月度汇总达成率回到 H1 基准（考核 130.6 / 管理 91.1 / 管理签单 103.2）。"""
    from pathlib import Path
    processed = Path(__file__).resolve().parents[2] / "datasets" / "processed" / "marketing_2026H1"
    if not (processed / "ship_order_line.parquet").exists():
        pytest.skip("未生成清洗产物，先跑 datasets/process_marketing_data.py")

    ship = compose(grain="month", bases=["ship_amount_fc_hs_wan"], apply_presets=True)
    ship_num = sum(r["assessment_ship_achieve_numerator_wan"] for r in ship["rows"])
    ship_den = sum(r["assessment_ship_achieve_denominator_wan"] for r in ship["rows"])
    assessment = ship_num / ship_den * 100

    mgmt_num = sum(r["management_ship_achieve_numerator_wan"] for r in ship["rows"])
    mgmt_den = sum(r["management_ship_achieve_denominator_wan"] for r in ship["rows"])
    management = mgmt_num / mgmt_den * 100

    assert assessment == pytest.approx(130.6, abs=1.5)
    assert management == pytest.approx(91.1, abs=1.5)

    sign = compose(grain="sign_month", bases=["sign_amount_fc_hs_wan"], apply_presets=True)
    sign_num = sum(r["management_sign_achieve_numerator_wan"] for r in sign["rows"])
    sign_den = sum(r["management_sign_achieve_denominator_wan"] for r in sign["rows"])
    assert sign_num / sign_den * 100 == pytest.approx(103.2, abs=1.5)
