"""Machine-tool manufacturing overlay (company-side Semantica kit)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

PACKAGE_DIR = Path(__file__).resolve().parent
ONTOLOGY_DIR = PACKAGE_DIR / "ontology"
MAPPING_DIR = PACKAGE_DIR / "mapping"
SAMPLE_DIR = PACKAGE_DIR / "sample"

ONTOLOGY_NS = "https://company.local/ontology/machine-tool/"
DATA_NS = "https://company.local/data/"

REQUIRED_CLASS_NAMES = {
    "Site",
    "WorkCenter",
    "MachineTool",
    "CNCMill",
    "CNCLathe",
    "Grinder",
    "CuttingTool",
    "Fixture",
    "Material",
    "Workpiece",
    "PartDrawing",
    "ProcessPlan",
    "Operation",
    "NCProgram",
    "WorkOrder",
    "Operator",
    "OperationExecution",
    "Inspection",
    "Measurement",
}

REQUIRED_PROPERTY_NAMES = {
    "installedAt",
    "usesTool",
    "usesFixture",
    "plannedBy",
    "produces",
    "executes",
    "executedOn",
    "performedBy",
    "inspects",
    "partOfPlan",
    "assetCode",
    "toolLifeRemaining",
    "sequenceNo",
    "workOrderNo",
}


def load_yaml(path: Path) -> Any:
    """Load a YAML file as UTF-8."""
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_domain_template() -> Dict[str, Any]:
    """Return the manufacturing domain template dict."""
    return json.loads((ONTOLOGY_DIR / "domain_template.json").read_text(encoding="utf-8"))


def register_manufacturing_template(domains: Optional[Any] = None) -> Any:
    """Register the machine-tool template on a DomainOntologies manager."""
    from semantica.ontology import DomainOntologies

    manager = domains or DomainOntologies()
    manager.register_domain_template("manufacturing", load_domain_template())
    return manager


def load_ontology_dict() -> Dict[str, Any]:
    """Parse machine_tool.ttl into Semantica's ontology dictionary."""
    from semantica.ingest import OntologyIngestor

    ingested = OntologyIngestor().ingest_ontology(ONTOLOGY_DIR / "machine_tool.ttl")
    return ingested.data


def load_competency_questions() -> list:
    """Load competency-question records from YAML."""
    payload = load_yaml(ONTOLOGY_DIR / "competency_questions.yaml") or {}
    return list(payload.get("questions") or [])


def sqlite_url(db_path: Path) -> str:
    """Return a SQLAlchemy SQLite URL for an on-disk database."""
    return "sqlite:///" + Path(db_path).resolve().as_posix()
