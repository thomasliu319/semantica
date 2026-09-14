"""Governance: SHACL, shop rules, graph validation, and ontology quality gate."""

from __future__ import annotations

import argparse
import copy
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from rdflib import Graph, Literal, Namespace, RDF, XSD
from rdflib.term import URIRef

from semantica.kg.graph_validator import GraphValidator
from semantica.ontology.competency_questions import CompetencyQuestionsManager
from semantica.ontology.ontology_validator import run_shacl_validation
from semantica.ontology.quality_gate import OntologyQualityGate

from .. import (
    DATA_NS,
    ONTOLOGY_DIR,
    ONTOLOGY_NS,
    load_competency_questions,
    load_domain_template,
    load_ontology_dict,
)

MT = Namespace(ONTOLOGY_NS)


def ontology_for_quality_gate(ontology: Dict[str, Any]) -> Dict[str, Any]:
    """Copy ingested OWL into the dict shape OntologyQualityGate expects."""
    prepared = copy.deepcopy(ontology)
    for cls in prepared.get("classes") or []:
        if not isinstance(cls, dict):
            continue
        parents = cls.get("parents") or cls.get("parent")
        if parents and "parent" not in cls:
            cls["parent"] = parents
    return prepared


def _node_uri(entity_id: str) -> URIRef:
    safe = str(entity_id).replace(" ", "_")
    return URIRef(DATA_NS + safe)


def _literal(value: Any, datatype: str) -> Optional[Literal]:
    if value is None:
        return None
    if datatype == "integer":
        return Literal(int(value), datatype=XSD.integer)
    if datatype == "decimal":
        try:
            return Literal(Decimal(str(value)), datatype=XSD.decimal)
        except (InvalidOperation, ValueError):
            return Literal(str(value))
    if datatype == "datetime":
        text = str(value)
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return Literal(parsed, datatype=XSD.dateTime)
        except ValueError:
            return Literal(text, datatype=XSD.dateTime)
    return Literal(str(value), datatype=XSD.string)


_ATTR_DATATYPES = {
    "name": "string",
    "assetCode": "string",
    "workCenterCode": "string",
    "machineType": "string",
    "toolId": "string",
    "toolLifeRemaining": "decimal",
    "fixtureId": "string",
    "drawingNo": "string",
    "workpieceNo": "string",
    "planNo": "string",
    "operationNo": "string",
    "sequenceNo": "integer",
    "ncProgramPath": "string",
    "programPath": "string",
    "workOrderNo": "string",
    "startedAt": "datetime",
    "endedAt": "datetime",
    "result": "string",
    "dimension": "string",
    "measuredValue": "decimal",
    "specMin": "decimal",
    "specMax": "decimal",
}

_SKIP_KEYS = {
    "id",
    "type",
    "name",
    "rdf_types",
    "table",
    "aliases",
    "normalized_name",
    "metadata",
    "confidence",
}


def graph_to_turtle(graph: Dict[str, Any]) -> str:
    """Serialize KG instances into the machine-tool namespace for SHACL."""
    rdf = Graph()
    rdf.bind("mt", MT)
    for entity in graph.get("entities") or []:
        subject = _node_uri(entity["id"])
        types = list(entity.get("rdf_types") or [])
        entity_type = entity.get("type")
        if entity_type and entity_type not in types:
            types.insert(0, entity_type)
        for rdf_type in types:
            rdf.add((subject, RDF.type, MT[rdf_type]))
        name = entity.get("name")
        if name:
            rdf.add((subject, MT.name, Literal(str(name), datatype=XSD.string)))
        for key, value in entity.items():
            if key in _SKIP_KEYS or value is None:
                continue
            datatype = _ATTR_DATATYPES.get(key, "string")
            literal = _literal(value, datatype)
            if literal is not None:
                rdf.add((subject, MT[key], literal))
    for rel in graph.get("relationships") or []:
        rdf.add(
            (
                _node_uri(rel["source"]),
                MT[rel["type"]],
                _node_uri(rel["target"]),
            )
        )
    return rdf.serialize(format="turtle")


def _rel_index(graph: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    index: Dict[str, List[Dict[str, Any]]] = {}
    for rel in graph.get("relationships") or []:
        index.setdefault(rel.get("source"), []).append(rel)
    return index


def evaluate_shop_rules(graph: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic shop constraints used even when pySHACL is unavailable."""
    issues: List[Dict[str, Any]] = []
    outgoing = _rel_index(graph)
    machine_codes: Dict[str, List[str]] = {}

    def _is_machine(entity: Dict[str, Any]) -> bool:
        types = set(entity.get("rdf_types") or [])
        types.add(entity.get("type"))
        return bool(types & {"MachineTool", "CNCMill", "CNCLathe", "Grinder"})

    for entity in graph.get("entities") or []:
        etype = entity.get("type")
        types = set(entity.get("rdf_types") or [])
        types.add(etype)
        eid = entity.get("id")
        rels = outgoing.get(eid, [])
        rel_types = {rel.get("type") for rel in rels}

        if _is_machine(entity):
            if "installedAt" not in rel_types:
                issues.append(
                    {
                        "code": "MACHINE_MISSING_WORK_CENTER",
                        "message": "MachineTool must be installedAt a WorkCenter.",
                        "element_id": eid,
                    }
                )
            code = entity.get("assetCode")
            if not code:
                issues.append(
                    {
                        "code": "MACHINE_MISSING_ASSET_CODE",
                        "message": "MachineTool must have assetCode.",
                        "element_id": eid,
                    }
                )
            else:
                machine_codes.setdefault(str(code), []).append(eid)

        if etype == "CuttingTool":
            life = entity.get("toolLifeRemaining")
            if life is None:
                issues.append(
                    {
                        "code": "TOOL_MISSING_LIFE",
                        "message": "CuttingTool must have toolLifeRemaining.",
                        "element_id": eid,
                    }
                )
            else:
                try:
                    if Decimal(str(life)) < 0:
                        issues.append(
                            {
                                "code": "TOOL_NEGATIVE_LIFE",
                                "message": "CuttingTool toolLifeRemaining must be >= 0.",
                                "element_id": eid,
                            }
                        )
                except (InvalidOperation, ValueError):
                    issues.append(
                        {
                            "code": "TOOL_INVALID_LIFE",
                            "message": "CuttingTool toolLifeRemaining is not numeric.",
                            "element_id": eid,
                        }
                    )

        if etype == "WorkOrder":
            if "plannedBy" not in rel_types:
                issues.append(
                    {
                        "code": "WORK_ORDER_MISSING_PLAN",
                        "message": "WorkOrder must be plannedBy a ProcessPlan.",
                        "element_id": eid,
                    }
                )
            if "produces" not in rel_types:
                issues.append(
                    {
                        "code": "WORK_ORDER_MISSING_WORKPIECE",
                        "message": "WorkOrder must produce a Workpiece.",
                        "element_id": eid,
                    }
                )
            if not entity.get("workOrderNo"):
                issues.append(
                    {
                        "code": "WORK_ORDER_MISSING_NO",
                        "message": "WorkOrder must have workOrderNo.",
                        "element_id": eid,
                    }
                )

        if etype == "Operation":
            if entity.get("sequenceNo") is None:
                issues.append(
                    {
                        "code": "OPERATION_MISSING_SEQUENCE",
                        "message": "Operation must have sequenceNo.",
                        "element_id": eid,
                    }
                )
            if "partOfPlan" not in rel_types:
                issues.append(
                    {
                        "code": "OPERATION_MISSING_PLAN",
                        "message": "Operation must belong to a ProcessPlan.",
                        "element_id": eid,
                    }
                )

        if etype == "OperationExecution":
            started = entity.get("startedAt")
            ended = entity.get("endedAt")
            if not started or not ended:
                issues.append(
                    {
                        "code": "EXECUTION_MISSING_TIME",
                        "message": "OperationExecution must have startedAt and endedAt.",
                        "element_id": eid,
                    }
                )
            elif str(ended) < str(started):
                issues.append(
                    {
                        "code": "EXECUTION_TIME_ORDER",
                        "message": "OperationExecution endedAt must not be before startedAt.",
                        "element_id": eid,
                    }
                )

    for code, ids in machine_codes.items():
        if len(ids) > 1:
            issues.append(
                {
                    "code": "DUPLICATE_ASSET_CODE",
                    "message": f"assetCode {code} is not unique.",
                    "element_id": ",".join(ids),
                }
            )

    return {"passed": not issues, "issues": issues}


def _run_shacl(data_ttl: str) -> Dict[str, Any]:
    shapes = (ONTOLOGY_DIR / "machine_tool_shapes.ttl").read_text(encoding="utf-8")
    try:
        report = run_shacl_validation(data_ttl, shapes)
    except ImportError as exc:
        return {
            "available": False,
            "conforms": None,
            "error": str(exc),
            "violations": [],
        }
    violations = []
    for item in list(report.violations) + list(report.warnings):
        violations.append(
            {
                "focus_node": item.focus_node,
                "result_path": item.result_path,
                "constraint": item.constraint,
                "severity": item.severity,
                "message": item.message,
                "explanation": getattr(item, "explanation", None),
            }
        )
    return {
        "available": True,
        "conforms": report.conforms,
        "violations": violations,
        "raw_report": report.raw_report,
    }


def _competency_coverage(ontology: Dict[str, Any]) -> Dict[str, Any]:
    manager = CompetencyQuestionsManager()
    questions = load_competency_questions()
    for item in questions:
        cq = manager.add_question(
            item["question"],
            category=item.get("category", "general"),
            priority=int(item.get("priority") or 1),
        )
        cq.trace_to_elements = list(item.get("trace_to") or [])
    return manager.generate_report(ontology)


def govern(
    graph: Dict[str, Any],
    ontology: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run SHACL, shop rules, GraphValidator, and OntologyQualityGate."""
    ontology = ontology or load_ontology_dict()
    gate_ontology = ontology_for_quality_gate(ontology)
    data_ttl = graph_to_turtle(graph)
    shacl = _run_shacl(data_ttl)
    shop_rules = evaluate_shop_rules(graph)
    graph_result = GraphValidator().validate(graph)
    quality = OntologyQualityGate().check(
        gate_ontology,
        graph_data=graph,
        competency_questions=[
            item["question"] for item in load_competency_questions()
        ],
    )
    competency = _competency_coverage(gate_ontology)

    shacl_ok = True if shacl.get("conforms") is None else bool(shacl.get("conforms"))
    passed = bool(shop_rules["passed"] and shacl_ok and quality.passed)
    return {
        "passed": passed,
        "shacl": shacl,
        "shop_rules": shop_rules,
        "graph_validator": graph_result.to_dict(),
        "quality_gate": quality.to_dict(),
        "competency_questions": competency,
        "ontology": {
            "class_count": len(ontology.get("classes") or []),
            "property_count": len(ontology.get("properties") or []),
            "template_class_count": len(load_domain_template().get("classes") or []),
        },
        "data_graph_ttl": data_ttl,
    }


def main() -> None:
    from .ingest_and_link import ingest_and_link

    parser = argparse.ArgumentParser(description="Govern a machine-shop knowledge graph.")
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument("--violations", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    graph = ingest_and_link(args.db, include_violations=args.violations)
    report = govern(graph)
    if args.json:
        payload = dict(report)
        payload.pop("data_graph_ttl", None)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    print(f"passed={report['passed']}")
    print(f"shop_rules={report['shop_rules']['passed']}")
    print(f"shacl={report['shacl'].get('conforms')}")
    print(f"quality_gate={report['quality_gate'].get('passed')}")
    for issue in report["shop_rules"]["issues"]:
        print(f"  {issue['code']}: {issue['message']} ({issue.get('element_id')})")


if __name__ == "__main__":
    main()
