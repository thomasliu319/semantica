"""Company-side machine-tool overlay: ontology, linking, and governance."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
USE_CASES = REPO_ROOT / "cookbook" / "use_cases"
if str(USE_CASES) not in sys.path:
    sys.path.insert(0, str(USE_CASES))

from manufacturing import (  # noqa: E402
    REQUIRED_CLASS_NAMES,
    REQUIRED_PROPERTY_NAMES,
    load_competency_questions,
    load_ontology_dict,
    register_manufacturing_template,
)
from manufacturing.pipeline.govern import govern  # noqa: E402
from manufacturing.pipeline.ingest_and_link import (  # noqa: E402
    entity_by_attribute,
    ingest_and_link,
    neighbors,
)
from manufacturing.sample.build_sample_db import build_sample_db  # noqa: E402


def _local_names(items):
    names = set()
    for item in items:
        name = item.get("name") or ""
        uri = item.get("uri") or ""
        names.add(name)
        if "#" in uri:
            names.add(uri.rsplit("#", 1)[-1])
        elif "/" in uri:
            names.add(uri.rstrip("/").rsplit("/", 1)[-1])
    return names


def test_ontology_ingest_contains_shop_classes_and_properties():
    ontology = load_ontology_dict()
    class_names = _local_names(ontology.get("classes") or [])
    property_names = _local_names(ontology.get("properties") or [])
    missing_classes = REQUIRED_CLASS_NAMES - class_names
    missing_properties = REQUIRED_PROPERTY_NAMES - property_names
    assert not missing_classes, missing_classes
    assert not missing_properties, missing_properties
    assert len(ontology.get("classes") or []) >= len(REQUIRED_CLASS_NAMES)
    assert len(ontology.get("properties") or []) >= len(REQUIRED_PROPERTY_NAMES)


def test_register_manufacturing_template_at_runtime():
    domains = register_manufacturing_template()
    assert "manufacturing" in domains.list_domains()
    ontology = domains.create_domain_ontology(
        "manufacturing", uri="https://company.local/ontology/machine-tool/"
    )
    class_names = {item["name"] for item in ontology["classes"]}
    assert "MachineTool" in class_names
    assert "OperationExecution" in class_names
    assert any(prop["name"] == "installedAt" for prop in ontology["properties"])


def test_competency_questions_are_answerable():
    ontology = load_ontology_dict()
    from semantica.ontology.competency_questions import CompetencyQuestionsManager

    manager = CompetencyQuestionsManager()
    for item in load_competency_questions():
        manager.add_question(item["question"], category=item["category"])
    result = manager.validate_ontology(ontology)
    assert result["total_questions"] == 4
    assert result["answerable"] == result["total_questions"]


def test_clean_seed_graph_and_governance(tmp_path):
    db_path = tmp_path / "clean.sqlite"
    build_sample_db(db_path, include_violations=False)
    graph = ingest_and_link(db_path, include_violations=False, build_if_missing=False)
    assert graph["entities"]
    assert graph["relationships"]
    report = govern(graph)
    assert report["shop_rules"]["passed"], report["shop_rules"]["issues"]
    if report["shacl"].get("available"):
        assert report["shacl"]["conforms"], report["shacl"]["violations"]
    assert report["quality_gate"]["passed"], report["quality_gate"]["issues"]

    work_order = entity_by_attribute(graph, "workOrderNo", "WO-2026-001")
    assert work_order is not None
    executions = neighbors(graph, work_order["id"], "belongsToWorkOrder", direction="in")
    assert executions
    execution_id = executions[0]
    machines = neighbors(graph, execution_id, "executedOn")
    tools = neighbors(graph, execution_id, "usedTool")
    operators = neighbors(graph, execution_id, "performedBy")
    assert machines and tools and operators
    workpiece_ids = neighbors(graph, work_order["id"], "produces")
    assert workpiece_ids
    inspections = neighbors(graph, workpiece_ids[0], "inspects", direction="in")
    assert inspections

    vmc = entity_by_attribute(graph, "assetCode", "VMC-01")
    assert vmc is not None
    assert "立加01" in (vmc.get("aliases") or [])


def test_violation_seed_fails_governance(tmp_path):
    db_path = tmp_path / "dirty.sqlite"
    build_sample_db(db_path, include_violations=True)
    graph = ingest_and_link(db_path, include_violations=True, build_if_missing=False)
    report = govern(graph)
    assert not report["shop_rules"]["passed"]
    codes = {issue["code"] for issue in report["shop_rules"]["issues"]}
    assert "MACHINE_MISSING_WORK_CENTER" in codes
    assert "TOOL_NEGATIVE_LIFE" in codes
    if report["shacl"].get("available"):
        blob = " ".join(
            str(item.get("message") or "")
            + str(item.get("result_path") or "")
            + str(item.get("explanation") or "")
            for item in report["shacl"]["violations"]
        ).lower()
        assert "installedat" in blob or "workcenter" in blob or "toolLife".lower() in blob or "toollife" in blob or not report["shacl"]["conforms"]
        assert report["shacl"]["conforms"] is False


def test_associative_class_is_recorded(tmp_path):
    db_path = tmp_path / "assoc.sqlite"
    graph = ingest_and_link(db_path, include_violations=False)
    classes = graph["metadata"]["associative_classes"]
    assert classes[0]["name"] == "OperationExecution"
    assert "MachineTool" in classes[0]["connects"]
    assert classes[0]["temporal"] is True
