"""Tests for datasets/marketing_graphrag.py (OpenSpec marketing-graphrag).

Rule-based retrieval over the cleaned parquet + graph JSON. Skipped when the
cleaned artifacts are absent.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

_DS = Path(__file__).resolve().parents[2] / "datasets"
if str(_DS) not in sys.path:
    sys.path.insert(0, str(_DS))

from marketing_graphrag import MarketingGraphRAG  # noqa: E402

OUT = _DS / "processed" / "marketing_2026H1"
GRAPH = _DS / "json" / "marketing_cleaned_semantics.json"


@pytest.fixture(scope="module")
def rag():
    if not (OUT / "dq_report.json").exists() or not GRAPH.exists():
        pytest.skip("缺少清洗产物或图 JSON，先跑 process_marketing_data.py 与 build_marketing_graph.py")
    return MarketingGraphRAG(OUT, GRAPH)


# --- CQ 冒烟 --------------------------------------------------------------- #


def test_cq1_dept_month_achieve(rag):
    a = rag.answer("华南二区销售三科 6 月考核出机达成多少")
    assert a["intent"] == "achieve_dept"
    assert a["caliber"] == {"org_scope": "in_scope", "model_covered_only": True,
                            "dept_notnull": True, "unit": "万元含税"}
    assert a["scope"]["dept"] == "华南二区销售三科" and a["scope"]["month"] == 6
    assert a["achieve_pct"] is not None


def test_cq1_h1_baselines(rag):
    assert rag.answer("2026 H1 考核出机达成多少")["achieve_pct"] == 130.6
    assert rag.answer("2026 H1 管理出机达成多少")["achieve_pct"] == 91.1
    assert rag.answer("2026 H1 管理签单达成多少")["achieve_pct"] == 103.2


def test_cq2_behavior_emp(rag):
    a = rag.answer("有多少业务员连续3个月不签单")
    assert a["intent"] == "behavior_emp"
    assert a["caliber"]["user_role"] == "业务"
    assert a["consecutive_hit_count"] > 0
    assert a["consecutive_hit_count"] <= a["business_headcount"]


def test_cq3_product_achieve(rag):
    a = rag.answer("立加这个产品类型出机达成多少")
    assert a["intent"] == "achieve_product"
    assert a["scope"]["product_type"] == "立加"
    assert a["achieve_pct"] is not None


def test_cq4_area_rollup(rag):
    a = rag.answer("华东大区考核出机达成多少")
    assert a["intent"] == "achieve_dept"
    assert a["scope"]["area"] == "华东大区" and a["scope"]["dept"] is None


def test_cq5_customer_model(rag):
    a = rag.answer("C01005542 买了哪些机型")
    assert a["intent"] == "customer_model"
    assert a["customer"]["cust_code"] == "C01005542"
    assert a["top_models"]


def test_cq6_uncovered_type_caveat(rag):
    a = rag.answer("3C钻攻机出机达成多少")
    assert a["intent"] == "achieve_product"
    assert any("不在产品预算覆盖" in c for c in a["caveats"])


# --- 拒绝路径（G5） --------------------------------------------------------- #


@pytest.mark.parametrize(
    "q,kw",
    [
        ("某科室的立加预算达成多少", "B10"),
        ("张三主管的团队业绩是多少", "重名"),
        ("这个客户毛利率多少", "FinalCost"),
        ("全年出机达成多少", "H1"),
        ("这个业务员的手机号是多少", "PII"),
    ],
)
def test_refusals(rag, q, kw):
    a = rag.answer(q)
    assert a["intent"] == "refuse"
    assert a["answer"] is None
    assert kw in a["refusal_reason"]


# --- 图结构（B10 / A10） ---------------------------------------------------- #


def test_graph_no_budget_cross_edge():
    g = json.loads(GRAPH.read_text(encoding="utf-8"))
    for e in g["edges"]:
        pair = {e["source"].split(":")[0], e["target"].split(":")[0]}
        assert pair != {"dbudget", "pbudget"}, "两张预算表不得连通（B10）"


def test_graph_node_types():
    g = json.loads(GRAPH.read_text(encoding="utf-8"))
    types = g["meta"]["node_types"]
    for t in ["SalesPerson", "Dept", "Customer", "Product", "ProductType",
              "Month", "SignOrderLine", "ShipOrderLine"]:
        assert t in types
    for bad in ["Supervisor", "Factory", "Series", "Contract"]:
        assert bad not in types
