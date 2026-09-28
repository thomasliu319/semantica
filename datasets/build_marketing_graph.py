"""Build the marketing knowledge graph from cleaned parquet (OpenSpec marketing-graphrag).

Input : datasets/processed/marketing_2026H1/*.parquet  (run process_marketing_data.py first)
Output: datasets/json/marketing_cleaned_semantics.json  (Explorer-loadable)
        datasets/json/marketing_ontology.ttl

Nodes follow the entity criteria in openspec/changes/marketing-data-processing/ontology.md §1.2:
no nodes for supervisor / factory / series / contract name / material number.
Edges follow §3. Empty keys never produce an edge (axiom A10).
The two budget projections are never connected (B10).
"""

from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path
from typing import Any

import pandas as pd

_DS = Path(__file__).resolve().parent
DEFAULT_IN = _DS / "processed" / "marketing_2026H1"
DEFAULT_JSON = _DS / "json" / "marketing_cleaned_semantics.json"
DEFAULT_TTL = _DS / "json" / "marketing_ontology.ttl"

NS = "http://semantica.local/marketing/ontology#"


def nid(prefix: str, key: str) -> str:
    return f"{prefix}:{key}"


def _num(value: Any, default: float = 0.0) -> float:
    """Coerce a pandas cell to a finite float, defaulting NaN/空 to ``default``.

    ``value or default`` 对 numpy.nan 失效（nan 为真值），会把 NaN 写进 JSON；
    严格消费者（如 rdflib Literal）不接受 NaN。
    """
    try:
        x = float(value)
    except (TypeError, ValueError):
        return default
    if pd.isna(x):
        return default
    return x


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )


# --------------------------------------------------------------------------- #
# nodes
# --------------------------------------------------------------------------- #


def add(nodes: dict, node_id: str, ntype: str, label: str, **props: Any) -> None:
    if node_id in nodes:
        return
    # 与 iot_cleaned_semantics.json 同构：属性嵌套在 ``properties`` 里（含
    # ``content``），这样 ContextGraph.add_nodes 才会把 amount_wan / org_scope /
    # fqty 等业务属性保留下来，供 SPARQL 投影与推理读取。顶层平铺会被丢弃。
    nodes[node_id] = {"id": node_id, "type": ntype, "properties": {"content": label, **props}}


def edge(edges: list, src: str, rel: str, dst: str, **props: Any) -> None:
    edges.append({"source": src, "relation": rel, "target": dst, **props})


def build_graph(inp: Path) -> dict:
    emp = pd.read_parquet(inp / "emp_dim.parquet")
    dept = pd.read_parquet(inp / "dept_dim.parquet")
    prod = pd.read_parquet(inp / "product_dim.parquet")
    cust = pd.read_parquet(inp / "customer_dim.parquet")
    month = pd.read_parquet(inp / "month_dim.parquet")
    sign = pd.read_parquet(inp / "sign_order_line.parquet")
    ship = pd.read_parquet(inp / "ship_order_line.parquet")
    dbud = pd.read_parquet(inp / "dept_budget_month.parquet")
    pbud = pd.read_parquet(inp / "product_budget_month.parquet")

    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    covered = sorted(pbud["product_type"].dropna().unique().tolist())

    # ---- 组织层级 -----------------------------------------------------------
    for _, r in dept.iterrows():
        d = str(r["fdept"] or "")
        if not d:
            continue
        add(nodes, nid("dept", d), "Dept", d, org_name=r.get("org_name", ""),
            sales_dept=r.get("sales_dept", ""), area=r.get("area", ""), area_fq=r.get("area_fq", ""))
        if r.get("area"):
            a = str(r["area"])
            add(nodes, nid("area", a), "Area", a)
            edge(edges, nid("dept", d), "partOf", nid("area", a))
            if r.get("org_name"):
                bg = str(r["org_name"])
                add(nodes, nid("bg", bg), "BusinessGroup", bg)
                edge(edges, nid("area", a), "partOf", nid("bg", bg))

    for _, r in emp.iterrows():
        c = str(r["sales_code"] or "")
        if not c:
            continue
        add(nodes, nid("emp", c), "SalesPerson", str(r.get("sales_name") or c),
            user_role=r.get("user_role", ""), employment_status=r.get("employment_status", ""),
            area=r.get("area", ""), province=r.get("province", ""), city=r.get("affiliation_city", ""))
        if r.get("fdept"):
            edge(edges, nid("emp", c), "belongsTo", nid("dept", str(r["fdept"])))

    # ---- 产品 ---------------------------------------------------------------
    for _, r in prod.iterrows():
        z = str(r["zprod_name"] or "")
        if not z:
            continue
        add(nodes, nid("model", z), "Product", z, zprod_type=r.get("zprod_type", ""),
            budget_covered=bool(r.get("zprod_type") in covered))
        if r.get("zprod_type"):
            t = str(r["zprod_type"])
            add(nodes, nid("ptype", t), "ProductType", t, budget_covered=True)
            edge(edges, nid("model", z), "categorizedAs", nid("ptype", t))

    # ---- 客户 ---------------------------------------------------------------
    for _, r in cust.iterrows():
        c = str(r["cust_code"] or "")
        if not c:
            continue
        add(nodes, nid("cust", c), "Customer", str(r.get("cust_name") or c),
            cust_area=r.get("cust_area", ""), cust_role=r.get("cust_role", ""))

    # ---- 月 -----------------------------------------------------------------
    for _, r in month.iterrows():
        m = f"{r['year']}-{int(r['month']):02d}"
        add(nodes, nid("month", m), "Month", m, year=str(r["year"]), month=int(r["month"]))

    # ---- 预算（Plan；两投影互不连接，B10）------------------------------------
    for _, r in dbud.iterrows():
        d, m = str(r["fdept"] or ""), f"{r['year']}-{int(r['month']):02d}"
        if not d:
            continue
        bid = nid("dbudget", f"{d}@{m}")
        add(nodes, bid, "DeptBudgetMonth", f"{d} {m} 预算",
            assessment_ship_budget_hs=_num(r["assessment_ship_budget_hs"]),
            management_ship_budget_hs=_num(r["management_ship_budget_hs"]),
            management_signed_contract_hs=_num(r["management_signed_contract_hs"]),
            unit="万元含税")
        edge(edges, bid, "budgetsFor", nid("dept", d))
        edge(edges, bid, "inMonth", nid("month", m))

    for _, r in pbud.iterrows():
        t, m = str(r["product_type"] or ""), f"{r['year']}-{int(r['month']):02d}"
        if not t:
            continue
        bid = nid("pbudget", f"{t}@{m}")
        add(nodes, bid, "ProductBudgetMonth", f"{t} {m} 预算",
            assessment_ship_budget_hs=_num(r["assessment_ship_budget_hs"]),
            management_ship_budget_hs=_num(r["management_ship_budget_hs"]),
            gl_management_signed_contract_hs=_num(r["gl_management_signed_contract_hs"]),
            unit="万元含税")
        edge(edges, bid, "budgetsFor", nid("ptype", t))
        edge(edges, bid, "inMonth", nid("month", m))

    # ---- 事件（G3 明细可回溯）------------------------------------------------
    def add_events(df: pd.DataFrame, kind: str, prefix: str, id_cols: list[str]) -> None:
        for _, r in df.iterrows():
            eid = nid(prefix, "|".join(str(r[c]) for c in id_cols))
            m = f"{r['year']}-{int(r['month']):02d}" if pd.notna(r.get("month")) else ""
            add(nodes, eid, kind, str(r.get("docno") or eid),
                fact=kind,
                org_scope=r.get("org_scope", "unknown"),
                amount_wan=_num(r.get("total_money_fc_hs_wan")),
                amount_yuan=_num(r.get("total_money_fc_hs")),
                unit="万元/元",
                fqty=_num(r.get("fqty")))
            if r.get("sales_code"):
                edge(edges, eid, "signedBy" if kind == "SignOrderLine" else "shippedBy",
                     nid("emp", str(r["sales_code"])))
            if r.get("fdept"):  # A10：空键不建边
                edge(edges, eid, "ofDept", nid("dept", str(r["fdept"])))
            if r.get("zprod_name"):
                edge(edges, eid, "ofModel", nid("model", str(r["zprod_name"])))
            if r.get("zprod_type"):
                edge(edges, eid, "ofType", nid("ptype", str(r["zprod_type"])))
            if r.get("cust_code"):
                rel = "contractParty" if kind == "SignOrderLine" else "shipTo"
                edge(edges, eid, rel, nid("cust", str(r["cust_code"])))
            if m:
                edge(edges, eid, "inMonth", nid("month", m))

    add_events(sign, "SignOrderLine", "sign", ["docno", "docno_num"])
    add_events(ship, "ShipOrderLine", "ship", ["docno", "line_no"])

    # ---- 溯源（PROV-O，供 Explorer 的 PROV-O Lineage 展示）------------------
    # 与 iot_cleaned_semantics.json 的 activity:iot-clean 同构：
    # activity → agent (wasAssociatedWith) / 输入 (used) / 输出 (generated)。
    add(nodes, "activity:marketing", "process", "清洗 10 张 CSV → parquet + 知识图谱",
        color="#F59E0B")
    add(nodes, "agent:process-marketing", "system", "process_marketing_data.py",
        color="#94A3B8")
    add(nodes, "entity:marketing-csv", "Dataset", "dataReport/dataset",
        color="#64748B")
    add(nodes, "entity:marketing-parquet", "Dataset", "datasets/processed/marketing_2026H1",
        color="#64748B")
    edge(edges, "activity:marketing", "wasAssociatedWith", "agent:process-marketing")
    edge(edges, "activity:marketing", "used", "entity:marketing-csv")
    edge(edges, "activity:marketing", "generated", "entity:marketing-parquet")

    # ---- 补全悬空端点（G3 明细可回溯）------------------------------------
    # 事实表引用的业务员/机型若不在维度表（out_of_scope / 未登记），边会悬空。
    # 与 iot 图一致：为这些端点补一个默认 entity 节点，保证边不悬空、图谱可加载。
    for e in edges:
        for endpoint in (e["source"], e["target"]):
            if endpoint not in nodes:
                add(nodes, endpoint, "entity", endpoint)

    by_type: dict[str, int] = {}
    for n in nodes.values():
        by_type[n["type"]] = by_type.get(n["type"], 0) + 1
    by_rel: dict[str, int] = {}
    for e in edges:
        by_rel[e["relation"]] = by_rel.get(e["relation"], 0) + 1

    return {
        "graph_id": str(uuid.uuid5(uuid.NAMESPACE_URL, "semantica/marketing/2026H1")),
        "name": "营销经营知识图 2026H1",
        "source": str(inp),
        "window": "2026-01~06",
        "nodes": list(nodes.values()),
        "edges": edges,
        "links": [],
        "meta": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "node_types": by_type,
            "edge_relations": by_rel,
            "budget_covered_product_types": covered,
            "achieve_caliber": {
                "org_scope": "in_scope",
                "model_covered_only": True,
                "dept_notnull": True,
                "unit": "万元含税",
            },
            "not_connected": ["DeptBudgetMonth × ProductBudgetMonth (B10)"],
        },
    }


# --------------------------------------------------------------------------- #
# ontology (ttl)
# --------------------------------------------------------------------------- #

TTL = """@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix : <{ns}> .

<http://semantica.local/marketing/ontology> a owl:Ontology ;
    rdfs:label "营销经营清洗本体" ;
    owl:versionInfo "1.0" ;
    rdfs:comment "科室键 = Fdept_add（不是 Fdept）；机型键 = ZPROD_NAME（不是 FmateNumber）；宽表金额元、预算万元，比较前 /10000。" .

:Continuant a owl:Class ; rdfs:label "持续体" .
:Occurrent  a owl:Class ; rdfs:label "发生体" .
:Plan       a owl:Class ; rdfs:label "计划" ;
    rdfs:comment "预算不是发生体；与 Occurrent 不相交（A5），禁止与实际相加。" .

:BusinessEvent a owl:Class ; rdfs:subClassOf :Occurrent .
:SignOrderLine a owl:Class ; rdfs:subClassOf :BusinessEvent ; rdfs:label "签单行" .
:ShipOrderLine a owl:Class ; rdfs:subClassOf :BusinessEvent ; rdfs:label "出货行" .
:DeptBudgetMonth a owl:Class ; rdfs:subClassOf :Plan ; rdfs:label "科室月度预算" .
:ProductBudgetMonth a owl:Class ; rdfs:subClassOf :Plan ; rdfs:label "产品类型月度预算" .

:SalesPerson a owl:Class ; rdfs:subClassOf :Continuant ; rdfs:label "业务员" ;
    rdfs:comment "键 SalesCode；458 行归一为 455 工号（B9 prefer_active）。" .
:Dept a owl:Class ; rdfs:subClassOf :Continuant ; rdfs:label "科室" ;
    rdfs:comment "键 Fdept_add；Fdept 是更细粒度（含 …科N组），禁止混用（B5）。" .
:Area a owl:Class ; rdfs:subClassOf :Continuant ; rdfs:label "大区" .
:BusinessGroup a owl:Class ; rdfs:subClassOf :Continuant ; rdfs:label "事业群" .
:Customer a owl:Class ; rdfs:subClassOf :Continuant ; rdfs:label "客户" ;
    rdfs:comment "KunnrCode（合同相对方）与 fcust_number（收货方）并为同一实体，保留角色区分。" .
:Product a owl:Class ; rdfs:subClassOf :Continuant ; rdfs:label "机型" ;
    rdfs:comment "键 ZPROD_NAME；FmateNumber 是物料编码（SKU），不是机型。" .
:ProductType a owl:Class ; rdfs:subClassOf :Continuant ; rdfs:label "产品类型" .
:Month a owl:Class ; rdfs:label "自然月" .

:belongsTo a owl:ObjectProperty ; rdfs:domain :SalesPerson ; rdfs:range :Dept .
:partOf a owl:ObjectProperty ; rdfs:domain :Dept ; rdfs:range :Area .
:categorizedAs a owl:FunctionalProperty ; rdfs:domain :Product ; rdfs:range :ProductType .
:signedBy a owl:ObjectProperty ; rdfs:domain :SignOrderLine ; rdfs:range :SalesPerson .
:shippedBy a owl:ObjectProperty ; rdfs:domain :ShipOrderLine ; rdfs:range :SalesPerson .
:ofModel a owl:ObjectProperty ; rdfs:domain :BusinessEvent ; rdfs:range :Product .
:ofDept a owl:ObjectProperty ; rdfs:domain :BusinessEvent ; rdfs:range :Dept ;
    rdfs:comment "空键不建边（A10）；未归属行进 unassigned 桶。" .
:ofType a owl:ObjectProperty ; rdfs:domain :BusinessEvent ; rdfs:range :ProductType .
:contractParty a owl:ObjectProperty ; rdfs:domain :SignOrderLine ; rdfs:range :Customer .
:shipTo a owl:ObjectProperty ; rdfs:domain :ShipOrderLine ; rdfs:range :Customer .
:inMonth a owl:ObjectProperty ; rdfs:domain :BusinessEvent ; rdfs:range :Month .
:budgetsFor a owl:ObjectProperty ; rdfs:domain :Plan ;
    rdfs:comment "计划对照组织/产品类型；不是 join，不同投影不可相加（B10）。" .
:measuredAgainst a owl:ObjectProperty ;
    rdfs:comment "查询时对照关系，物理图上不建边。" .

<http://semantica.local/marketing/skos> a skos:ConceptScheme ; skos:prefLabel "指标词表" .

<http://semantica.local/marketing/skos#managementShip> a skos:Concept ;
    skos:prefLabel "管理出机" ;
    skos:definition "出货含税 TotalMoneyFC_HS，对照 Management_Ship_Budget_Hs。" ;
    skos:inScheme <http://semantica.local/marketing/skos> .

<http://semantica.local/marketing/skos#assessmentShip> a skos:Concept ;
    skos:prefLabel "考核出机" ;
    skos:definition "与管理出机同一字段 TotalMoneyFC_HS，只有预算列不同（Assessment_Ship_Budget_Hs）。" ;
    skos:inScheme <http://semantica.local/marketing/skos> ;
    skos:related <http://semantica.local/marketing/skos#managementShip> .

<http://semantica.local/marketing/skos#managementSign> a skos:Concept ;
    skos:prefLabel "管理签单" ;
    skos:definition "签单含税 TotalMoneyFc_HS（不是不含税 TotalMoneyFc）。" ;
    skos:inScheme <http://semantica.local/marketing/skos> .
"""


def main() -> None:
    ap = argparse.ArgumentParser(description="Build marketing knowledge graph from cleaned parquet")
    ap.add_argument("--in", dest="inp", type=Path, default=DEFAULT_IN)
    ap.add_argument("--json-out", type=Path, default=DEFAULT_JSON)
    ap.add_argument("--ttl-out", type=Path, default=DEFAULT_TTL)
    a = ap.parse_args()

    g = build_graph(a.inp)
    write_json(a.json_out, g)
    a.ttl_out.parent.mkdir(parents=True, exist_ok=True)
    a.ttl_out.write_text(TTL.format(ns=NS), encoding="utf-8")

    m = g["meta"]
    print(f"json -> {a.json_out}")
    print(f"ttl  -> {a.ttl_out}")
    print(f"nodes {m['node_count']}  edges {m['edge_count']}")
    for k, v in sorted(m["node_types"].items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")
    print("relations:", m["edge_relations"])


if __name__ == "__main__":
    main()
