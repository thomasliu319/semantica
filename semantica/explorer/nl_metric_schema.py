"""Load NL ↔ field ↔ SPARQL bindings for GraphRAG (single source of truth)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_SCHEMA_PATH = Path(__file__).with_name("nl_metric_schema.json")


@lru_cache(maxsize=1)
def load_metric_schema() -> dict[str, Any]:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def measures() -> list[dict[str, Any]]:
    return list(load_metric_schema().get("measures") or [])


def metric_phrases() -> list[tuple[str, str, str, str]]:
    rows: list[tuple[str, str, str, str]] = []
    for item in measures():
        field = str(item["field"])
        label = str(item.get("label") or field)
        how = str(item.get("how") or "sum")
        for phrase in item.get("phrases") or []:
            rows.append((str(phrase), field, label, how))
    return rows


def stop_phrases() -> frozenset[str]:
    found = {phrase for phrase, _field, _label, _how in metric_phrases()}
    found.update({"设备", "台数"})
    return frozenset(found)


def stored_measures() -> list[dict[str, Any]]:
    return [item for item in measures() if not item.get("ratio")]


def sparql_select_vars() -> list[str]:
    return [str(item["sparql"]) for item in stored_measures() if item.get("sparql")]


def sparql_optionals(subject: str) -> str:
    lines = []
    for item in stored_measures():
        alias = item.get("sparql")
        prop = item.get("prop")
        if not alias or not prop:
            continue
        lines.append(f"  OPTIONAL {{ {subject} prop:{prop} ?{alias} }}")
    return "\n".join(lines) + ("\n" if lines else "")
