"""Compile NL metric questions to schema-mapped SPARQL (OpenSpec nl2sparql-graphrag)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from semantica.explorer.nl_metric_schema import sparql_optionals, sparql_select_vars, stored_measures

NS = "http://semantica.local/entity/"
PROP = "http://semantica.local/prop/"

GRAINS: dict[str, dict[str, Any]] = {
    "type_month": {
        "table": "device_day ⋈ device_dim GROUP BY equip_type_code, month",
        "node": "TypeMonth",
        "joins": ["ofType"],
        "subject": "slice",
    },
    "equip_month": {
        "table": "device_day GROUP BY out_factory_code, month",
        "node": "EquipMonth",
        "joins": ["ofEquip", "ofType", "locatedIn", "ownedBy"],
        "subject": "em",
    },
    "area": {
        "table": "device_dim GROUP BY area_name",
        "node": "Area",
        "joins": ["locatedIn"],
        "subject": "node",
    },
    "customer": {
        "table": "device_dim GROUP BY company_id",
        "node": "Customer",
        "joins": ["ownedBy"],
        "subject": "node",
    },
    "equip": {
        "table": "device_dim",
        "node": "Equip",
        "joins": ["locatedIn", "ownedBy"],
        "subject": "node",
    },
}

_FIELD_ALIAS = {str(item["field"]): str(item["sparql"]) for item in stored_measures() if item.get("sparql")}


@dataclass
class QueryPlan:
    grain: str
    node_type: str
    table: str
    joins: list[str]
    types: list[str] = field(default_factory=list)
    codes: list[str] = field(default_factory=list)
    months: list[str] = field(default_factory=list)
    names: list[str] = field(default_factory=list)
    metrics: list[tuple[str, str, str]] = field(default_factory=list)
    scope: str = ""


def _lit(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def _in_filter(var: str, values: list[str], *, lower: bool = False) -> str:
    if not values:
        return ""
    inner = ", ".join(f'"{_lit(item)}"' for item in values)
    expr = f"LCASE(STR({var}))" if lower else var
    if lower:
        inner = ", ".join(f'"{_lit(item.lower())}"' for item in values)
    return f"  FILTER({expr} IN ({inner}))\n"


def compile_plan(query: str) -> QueryPlan | None:
    from semantica.explorer.decision_graphrag import _metric_specs, _parse_query

    parsed = _parse_query(query)
    metrics = _metric_specs(query)
    types = list(parsed["types"])
    codes = list(parsed["codes"])
    months = list(parsed["months"])
    names = list(parsed["names"])
    if types and (months or metrics):
        grain = "type_month"
    elif codes and (months or metrics):
        grain = "equip_month"
    elif names and any(name.endswith("区") for name in names):
        grain = "area"
    elif names:
        grain = "customer"
    elif types:
        grain = "type_month"
    elif codes:
        grain = "equip"
    else:
        return None
    spec = GRAINS[grain]
    scope = ""
    if types:
        import re

        match = re.search(r"[A-Za-z][A-Za-z0-9.-]*\d[A-Za-z0-9.-]*", query or "")
        scope = match.group(0) if match else types[0]
    elif codes:
        scope = codes[0]
    elif names:
        scope = names[0]
    return QueryPlan(
        grain=grain,
        node_type=str(spec["node"]),
        table=str(spec["table"]),
        joins=list(spec["joins"]),
        types=types,
        codes=codes,
        months=months,
        names=names,
        metrics=metrics,
        scope=scope,
    )


def render_sparql(plan: QueryPlan) -> str:
    prefixes = (
        "PREFIX ent: <http://semantica.local/entity/>\n"
        "PREFIX prop: <http://semantica.local/prop/>\n"
        "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n"
    )
    extra = " ".join(f"?{alias}" for alias in sparql_select_vars())
    if plan.grain == "type_month":
        body = (
            f"SELECT ?slice ?type ?month {extra}\n"
            "WHERE {\n"
            "  ?slice a ent:TypeMonth ;\n"
            "         prop:EquipTypeCode ?type ;\n"
            "         prop:month ?month .\n"
            f"{sparql_optionals('?slice')}"
            "  OPTIONAL { ?slice prop:ofType ?etype }\n"
            f"{_in_filter('?type', plan.types, lower=True)}"
            f"{_in_filter('?month', plan.months)}"
            "}\n"
            "ORDER BY ?month\n"
        )
    elif plan.grain == "equip_month":
        body = (
            f"SELECT ?em ?code ?month ?type ?area ?customer {extra}\n"
            "WHERE {\n"
            "  ?em a ent:EquipMonth ;\n"
            "      prop:month ?month .\n"
            "  OPTIONAL { ?em prop:OutFactoryCode ?code }\n"
            "  OPTIONAL { ?em prop:EquipTypeCode ?type }\n"
            f"{sparql_optionals('?em')}"
            "  OPTIONAL {\n"
            "    ?em prop:ofEquip ?eq .\n"
            "    OPTIONAL { ?eq prop:locatedIn ?ar . ?ar rdfs:label ?area }\n"
            "    OPTIONAL { ?eq prop:ownedBy ?cu . ?cu rdfs:label ?customer }\n"
            "  }\n"
            f"{_in_filter('?code', plan.codes)}"
            f"{_in_filter('?month', plan.months)}"
            "}\n"
            "ORDER BY ?month\n"
        )
    elif plan.grain == "area":
        body = (
            "SELECT ?node ?label ?devices ?hours ?alarms\n"
            "WHERE {\n"
            "  ?node a ent:Area ;\n"
            "        rdfs:label ?label .\n"
            "  OPTIONAL { ?node prop:devices ?devices }\n"
            "  OPTIONAL { ?node prop:run_hours ?hours }\n"
            "  OPTIONAL { ?node prop:alarm_count ?alarms }\n"
            + _name_contains("?label", plan.names)
            + "}\n"
        )
    elif plan.grain == "customer":
        body = (
            "SELECT ?node ?label ?devices ?hours ?alarms\n"
            "WHERE {\n"
            "  ?node a ent:Customer ;\n"
            "        rdfs:label ?label .\n"
            "  OPTIONAL { ?node prop:devices ?devices }\n"
            "  OPTIONAL { ?node prop:run_hours ?hours }\n"
            "  OPTIONAL { ?node prop:alarm_count ?alarms }\n"
            + _name_contains("?label", plan.names)
            + "}\n"
        )
    else:
        body = (
            "SELECT ?node ?code ?type ?area ?customer ?hours\n"
            "WHERE {\n"
            "  ?node a ent:Equip .\n"
            "  OPTIONAL { ?node prop:OutFactoryCode ?code }\n"
            "  OPTIONAL { ?node prop:EquipTypeCode ?type }\n"
            "  OPTIONAL { ?node prop:run_hours ?hours }\n"
            "  OPTIONAL { ?node prop:locatedIn ?ar . ?ar rdfs:label ?area }\n"
            "  OPTIONAL { ?node prop:ownedBy ?cu . ?cu rdfs:label ?customer }\n"
            f"{_in_filter('?code', plan.codes)}"
            "}\n"
        )
    return prefixes + body


def _name_contains(var: str, names: list[str]) -> str:
    if not names:
        return ""
    clauses = " || ".join(f'CONTAINS(STR({var}), "{_lit(name)}")' for name in names)
    return f"  FILTER({clauses})\n"


def mapping_rows(plan: QueryPlan) -> list[dict[str, str]]:
    metrics = "、".join(label for _field, label, _how in plan.metrics) or "—"
    return [
        {
            "nl": plan.scope or "问句维度",
            "table": plan.table,
            "node": plan.node_type,
            "joins": " ".join(plan.joins) or "—",
            "metrics": metrics,
        }
    ]


def node_id_from_uri(uri: str | None) -> str:
    text = str(uri or "")
    if text.startswith(NS):
        return text[len(NS) :]
    return text.rsplit("/", 1)[-1] if text else ""


def sparql_to_compose_rows(plan: QueryPlan, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    composed: list[dict[str, Any]] = []
    for row in rows:
        props: dict[str, Any] = {}
        for field, alias in _FIELD_ALIAS.items():
            raw = row.get(alias)
            if raw in (None, "", "None"):
                continue
            try:
                props[field] = float(raw)
            except (TypeError, ValueError):
                props[field] = raw
        subject = row.get("slice") or row.get("em") or row.get("node") or ""
        month = str(row.get("month") or "")
        if month.startswith("http"):
            month = month.rsplit("/", 1)[-1]
        label = str(row.get("label") or "")
        scope = plan.scope or str(row.get("type") or row.get("code") or label)
        content = f"{scope} {month}".strip() if month else (label or scope)
        composed.append(
            {
                "id": node_id_from_uri(str(subject)),
                "type": plan.node_type,
                "content": content,
                "month": month,
                "props": props,
            }
        )
    return composed


def hydrate_compose_rows(session: Any, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fill SPARQL gaps from the stamped node so schema fields like devices still bind."""
    for row in rows:
        if row.get("missing") or not row.get("id"):
            continue
        node = session.get_node(row["id"]) or {}
        node_props = dict(node.get("properties") or {})
        if not node_props:
            continue
        merged = {**node_props, **(row.get("props") or {})}
        row["props"] = merged
        if not row.get("content"):
            row["content"] = str(node.get("content") or row["id"])
        if not row.get("type"):
            row["type"] = str(node.get("type") or row.get("type") or "")
    return rows


def compile_and_run(session: Any, query: str) -> dict[str, Any] | None:
    plan = compile_plan(query)
    if plan is None:
        return None
    sparql = render_sparql(plan)
    rows = execute_select(session, sparql)
    compose = hydrate_compose_rows(session, sparql_to_compose_rows(plan, rows))
    return {
        "plan": plan,
        "sparql": sparql,
        "mapping": mapping_rows(plan),
        "rows": rows,
        "compose": compose,
    }


def execute_select(session: Any, sparql: str) -> list[dict[str, Any]]:
    from semantica.explorer.routes.sparql import _build_rdflib_graph

    graph = _build_rdflib_graph(session)
    results = graph.query(sparql)
    columns = [str(var) for var in (results.vars or [])]
    rows: list[dict[str, Any]] = []
    for item in results:
        rows.append(
            {
                column: (str(item[index]) if item[index] is not None else None)
                for index, column in enumerate(columns)
            }
        )
    return rows
