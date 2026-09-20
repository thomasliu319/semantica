"""GraphRAG retrieve → expand → record_decision in Explorer Decisions."""

import pytest

from semantica.context.context_graph import ContextGraph

pytest.importorskip("fastapi")

from semantica.explorer.app import create_app
from semantica.explorer.decision_graphrag import _extract_months, run_graphrag
from semantica.explorer.nl2sparql import compile_plan, render_sparql
from semantica.explorer.session import GraphSession
from starlette.testclient import TestClient


def _graph() -> ContextGraph:
    graph = ContextGraph(advanced_analytics=False)
    graph.add_node("type:T-V856S", node_type="EquipType", content="T-V856S 立加")
    graph.add_node(
        "slice:T-V856S:2026-04",
        node_type="TypeMonth",
        content="T-V856S 2026-04",
        alarm_per_run_hour=8.8146,
        run_hours=1262,
        run_days=179,
        devices=19,
        alarm_count=11124,
        month="2026-04",
        EquipTypeCode="T-V856S",
    )
    graph.add_node(
        "slice:T-V856S:2026-05",
        node_type="TypeMonth",
        content="T-V856S 2026-05",
        run_hours=7818.6,
        run_days=749,
        devices=30,
        alarm_count=49114,
        month="2026-05",
        EquipTypeCode="T-V856S",
    )
    graph.add_node(
        "slice:T-V856S:2026-08",
        node_type="TypeMonth",
        content="T-V856S 2026-08",
        run_hours=9999,
        run_days=1,
        devices=1,
        alarm_count=1,
        month="2026-08",
        EquipTypeCode="T-V856S",
    )
    graph.add_node("decision:drop_mar", node_type="decision", content="丢掉几乎全停的 3 月", category="calendar", outcome="approved")
    graph.add_node("dataset:cleaned", node_type="Dataset", content="清洗后完备设备语义图")
    graph.add_node("equip:152600398", node_type="Equip", content="152600398", CompanyName="太仓卓立精密机械有限公司", AreaName="华东区")
    graph.add_node("equipmonth:152600398:2026-04", node_type="EquipMonth", content="152600398 2026-04", month="2026-04", OutFactoryCode="152600398")
    graph.add_node("equipmonth:152600398:2026-05", node_type="EquipMonth", content="152600398 2026-05", month="2026-05", OutFactoryCode="152600398")
    graph.add_node("area:华南区", node_type="Area", content="华南区", devices=125, run_hours=59963.3)
    graph.add_node("customer:tianzhu", node_type="Customer", content="深圳市天铸智造有限公司")
    for index in range(20):
        graph.add_node(f"dummy:{index}", node_type="Equip", content=f"无关设备 {index}")
        graph.add_edge("dataset:cleaned", f"dummy:{index}", edge_type="contains")
    graph.add_edge("dataset:cleaned", "type:T-V856S", edge_type="covers")
    graph.add_edge("slice:T-V856S:2026-04", "type:T-V856S", edge_type="ofType")
    graph.add_edge("slice:T-V856S:2026-05", "type:T-V856S", edge_type="ofType")
    graph.add_edge("slice:T-V856S:2026-08", "type:T-V856S", edge_type="ofType")
    graph.add_edge("decision:drop_mar", "slice:T-V856S:2026-04", edge_type="about")
    graph.add_edge("equipmonth:152600398:2026-04", "equip:152600398", edge_type="ofEquip")
    graph.add_edge("equipmonth:152600398:2026-05", "equip:152600398", edge_type="ofEquip")
    graph.add_edge("equip:152600398", "area:华南区", edge_type="locatedIn")
    graph.add_edge("equip:152600398", "customer:tianzhu", edge_type="ownedBy")
    return graph


@pytest.fixture
def rag_client():
    with TestClient(create_app(session=GraphSession(_graph()))) as client:
        yield client


def test_run_graphrag_records_evidence_and_skips_hub():
    session = GraphSession(_graph())
    payload = run_graphrag(session, "T-V856S 2026-04 报警强度为什么高", max_hops=2)
    source_ids = {row["id"] for row in payload["sources"]}
    assert "slice:T-V856S:2026-04" in source_ids
    assert "dataset:cleaned" not in source_ids
    assert not any(item.startswith("dummy:") for item in source_ids)
    assert payload["decision_id"]
    assert payload["chain"]
    assert "ofType" in payload["reasoning_path"] or payload["num_sources"] >= 1
    assert payload["response"].startswith("## ")
    assert "### 主要命中" in payload["response"]
    assert "| 节点 | 类型 | 来源 | 要点 |" in payload["response"]
    if payload["reasoning_path"]:
        assert "| # | 起点 | 关系 | 终点 |" in payload["reasoning_path"]
    recorded = session.get_node(payload["decision_id"])
    assert recorded is not None
    assert recorded["type"] == "decision"
    assert recorded["properties"].get("category") == "graphrag_query"


def test_device_month_and_area_customer_queries():
    session = GraphSession(_graph())
    device = run_graphrag(session, "设备 152600398 2026-04 工作情况")
    assert "equipmonth:152600398:2026-04" in {row["id"] for row in device["sources"]}
    months = run_graphrag(session, "设备 152600398 2026-04 2026-05 运行与报警")
    month_ids = {row["id"] for row in months["sources"]}
    assert "equipmonth:152600398:2026-04" in month_ids
    assert "equipmonth:152600398:2026-05" in month_ids
    area = run_graphrag(session, "华南区 运行小时")
    assert any(row["id"] == "area:华南区" for row in area["sources"])
    customer = run_graphrag(session, "深圳市天铸智造有限公司 设备情况")
    assert any(row["id"] == "customer:tianzhu" for row in customer["sources"])
    hours = run_graphrag(session, "T-V856S 2026-04 运行时间")
    assert "slice:T-V856S:2026-04" in {row["id"] for row in hours["sources"]}
    assert "1262" in hours["response"]
    assert hours["sources"][0]["id"] == "slice:T-V856S:2026-04"
    both = run_graphrag(session, "T-V856S 2026-04 2026-05 运行时间")
    both_ids = {row["id"] for row in both["sources"]}
    assert "slice:T-V856S:2026-04" in both_ids
    assert "slice:T-V856S:2026-05" in both_ids
    assert "1262" in both["response"]
    assert "7818.6" in both["response"] or "7819" in both["response"]
    assert "9080.6" in both["response"] or "9081" in both["response"]
    assert "slice:T-V856S:2026-08" not in both_ids
    assert "9999" not in both["response"].split("### 主要命中")[0]
    zh = run_graphrag(session, "T-V856S 2026年04月，2026年05月运行时间")
    zh_ids = {row["id"] for row in zh["sources"]}
    assert "slice:T-V856S:2026-04" in zh_ids
    assert "slice:T-V856S:2026-05" in zh_ids
    assert "slice:T-V856S:2026-08" not in zh_ids
    zh_answer = zh["response"].split("### 主要命中")[0]
    assert "1262" in zh_answer
    assert "7818.6" in zh_answer or "7819" in zh_answer
    assert "9080.6" in zh_answer or "9081" in zh_answer
    assert "9999" not in zh_answer
    assert "2026-08" not in zh_answer
    both_metrics = run_graphrag(session, "T-V856S 2026年4月，2026年5月运行时间，运行天数")
    metric_answer = both_metrics["response"].split("### 主要命中")[0]
    assert "9080.6" in metric_answer or "9081" in metric_answer
    assert "运行天数" in metric_answer
    assert "179" in metric_answer
    assert "749" in metric_answer
    assert "928" in metric_answer
    assert "9999" not in metric_answer
    three = run_graphrag(session, "T-V856S 2026年4月，2026年5月，2026年9月运行时间，运行天数")
    three_answer = three["response"].split("### 主要命中")[0]
    assert "2026-04+2026-05+2026-09" in three_answer
    assert "图上无切片" in three_answer
    assert "2026-09" in three_answer
    assert "9080.6" in three_answer or "9081" in three_answer
    assert "928" in three_answer
    assert "9999" not in three_answer
    spanned = run_graphrag(session, "T-V856S 2026年4月至2026年8月运行时间")
    span_answer = spanned["response"].split("### 主要命中")[0]
    assert "2026-06" in span_answer
    assert "2026-07" in span_answer
    assert "图上无切片" in span_answer
    assert "9999" in span_answer


def test_extract_months_reads_chinese_and_iso():
    assert _extract_months("T-V856S 2026-04 2026-05 运行时间") == ["2026-04", "2026-05"]
    assert _extract_months("T-V856S 2026年04月，2026年05月运行时间") == ["2026-04", "2026-05"]
    assert _extract_months("T-V856S 2026年4月运行时间") == ["2026-04"]
    assert _extract_months("T-V856S 2026年4月，2026年5月，2026年9月运行时间，运行天数") == [
        "2026-04",
        "2026-05",
        "2026-09",
    ]
    assert _extract_months("T-V856S 2026年4月、5月、9月运行时间") == ["2026-04", "2026-05", "2026-09"]
    assert _extract_months("T-V856S 2026年4月至2026年8月运行时间") == [
        "2026-04",
        "2026-05",
        "2026-06",
        "2026-07",
        "2026-08",
    ]


def test_nl2sparql_compiles_type_month_and_missing_month():
    query = "T-V856S 2026年4月，2026年5月，2026年9月运行时间，运行天数，设备台数"
    plan = compile_plan(query)
    assert plan is not None
    assert plan.grain == "type_month"
    assert plan.months == ["2026-04", "2026-05", "2026-09"]
    sparql = render_sparql(plan)
    assert "ent:TypeMonth" in sparql
    assert "2026-09" in sparql
    assert "ofType" in sparql
    assert "prop:devices" in sparql
    assert plan.metrics[-1][0] == "devices"
    session = GraphSession(_graph())
    payload = run_graphrag(session, query)
    assert payload["sparql"]
    assert payload["mapping"]
    assert payload["mapping"][0]["node"] == "TypeMonth"
    answer = payload["response"].split("### 主要命中")[0]
    assert "模式映射" in payload["response"]
    assert "```sparql" in payload["response"]
    assert "9080.6" in answer or "9081" in answer
    assert "928" in answer
    assert "图上无切片" in answer
    assert "设备台数" in answer
    assert "- 2026-04：19" in answer
    assert "- 2026-05：30" in answer
    assert "合计：49" not in answer
    assert any(row.get("kind") == "sparql" for row in payload["sources"])


def test_empty_query_rejected():
    session = GraphSession(_graph())
    with pytest.raises(ValueError):
        run_graphrag(session, "   ")


def test_graphrag_route_lists_new_decision(rag_client):
    before = {item["decision_id"] for item in rag_client.get("/api/decisions").json()}
    response = rag_client.post(
        "/api/decisions/graphrag",
        json={"query": "为什么丢掉 3 月", "max_hops": 2},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["decision_id"] not in before
    assert payload["query"] == "为什么丢掉 3 月"
    listed = rag_client.get("/api/decisions").json()
    assert any(item["decision_id"] == payload["decision_id"] for item in listed)
    chain = rag_client.get(f"/api/decisions/{payload['decision_id']}/chain")
    assert chain.status_code == 200
    assert chain.json()["chain"]


def test_graphrag_route_rejects_blank(rag_client):
    response = rag_client.post("/api/decisions/graphrag", json={"query": "   "})
    assert response.status_code == 422
