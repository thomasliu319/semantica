"""Deterministic table-to-graph linking for the machine-tool overlay."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

from semantica.kg.entity_resolver import EntityResolver
from semantica.kg.graph_builder import GraphBuilder
from semantica.ontology.associative_class import AssociativeClassBuilder

from .. import MAPPING_DIR, load_yaml, sqlite_url
from ..sample.build_sample_db import build_sample_db

EntityId = str


def _entity_id(table: str, row_id: Any) -> EntityId:
    return f"{table}:{row_id}"


def _load_tables_via_sqlite(db_path: Path) -> Dict[str, List[Dict[str, Any]]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        names = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        tables: Dict[str, List[Dict[str, Any]]] = {}
        for name in names:
            tables[name] = [dict(r) for r in conn.execute(f'SELECT * FROM "{name}"')]
        return tables
    finally:
        conn.close()


def _load_tables_via_ingestor(db_path: Path) -> Dict[str, List[Dict[str, Any]]]:
    from semantica.ingest import DBIngestor

    payload = DBIngestor().ingest_database(sqlite_url(db_path))
    tables: Dict[str, List[Dict[str, Any]]] = {}
    for name, table in (payload.get("tables") or {}).items():
        tables[name] = list(table.get("rows") or [])
    return tables


def load_shop_tables(db_path: Path) -> Dict[str, List[Dict[str, Any]]]:
    """Load table rows through DBIngestor when SQLAlchemy is available."""
    try:
        return _load_tables_via_ingestor(db_path)
    except Exception:
        return _load_tables_via_sqlite(db_path)


def _copy_attributes(row: Dict[str, Any], spec: Dict[str, Any]) -> Dict[str, Any]:
    attrs: Dict[str, Any] = {}
    for column, mapping in (spec.get("attributes") or {}).items():
        property_name = mapping["property"] if isinstance(mapping, dict) else mapping
        if column in row and row[column] is not None:
            attrs[property_name] = row[column]
    return attrs


def _rdf_types(spec: Dict[str, Any], specific: Optional[str]) -> List[str]:
    types = list(spec.get("rdf_types") or [spec["class"]])
    if specific and specific not in types:
        types.insert(0, specific)
    return types


def map_tables_to_graph(
    tables: Dict[str, List[Dict[str, Any]]],
    table_map: Optional[Dict[str, Any]] = None,
    relation_map: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Convert shop tables to entities and object-property relationships."""
    table_map = table_map or load_yaml(MAPPING_DIR / "table_to_class.yaml")
    relation_map = relation_map or load_yaml(MAPPING_DIR / "fk_to_relation.yaml")
    table_specs = table_map["tables"]

    entities: List[Dict[str, Any]] = []
    relationships: List[Dict[str, Any]] = []

    for table_name, spec in table_specs.items():
        rows = tables.get(table_name) or []
        type_map = spec.get("type_map") or {}
        type_field = spec.get("type_field")
        for row in rows:
            specific = None
            if type_field and row.get(type_field) in type_map:
                specific = type_map[row[type_field]]
            entity_type = specific or spec["class"]
            name_field = spec.get("name_field", "name")
            entity: Dict[str, Any] = {
                "id": _entity_id(table_name, row[spec["id_field"]]),
                "type": entity_type,
                "name": row.get(name_field) or str(row[spec["id_field"]]),
                "rdf_types": _rdf_types(spec, specific),
                "table": table_name,
            }
            entity.update(_copy_attributes(row, spec))
            entities.append(entity)

            nc_field = spec.get("nc_program_field")
            if nc_field and row.get(nc_field):
                nc_id = f"nc_program:{entity['id']}"
                entities.append(
                    {
                        "id": nc_id,
                        "type": "NCProgram",
                        "name": row[nc_field],
                        "rdf_types": ["NCProgram"],
                        "programPath": row[nc_field],
                    }
                )
                relationships.append(
                    {
                        "source": entity["id"],
                        "target": nc_id,
                        "source_id": entity["id"],
                        "target_id": nc_id,
                        "type": "hasNCProgram",
                    }
                )

    for rel in relation_map.get("relations") or []:
        spec = table_specs[rel["table"]]
        target_table = rel["target_table"]
        column = rel["column"]
        for row in tables.get(rel["table"]) or []:
            fk_value = row.get(column)
            if fk_value is None or fk_value == "":
                continue
            source_id = _entity_id(rel["table"], row[spec["id_field"]])
            target_id = _entity_id(target_table, fk_value)
            if rel.get("invert"):
                source_id, target_id = target_id, source_id
            relationships.append(
                {
                    "source": source_id,
                    "target": target_id,
                    "source_id": source_id,
                    "target_id": target_id,
                    "type": rel["property"],
                }
            )

    return {"entities": entities, "relationships": relationships}


def _index_by_class_key(
    entities: Iterable[Dict[str, Any]], table_specs: Dict[str, Any]
) -> Dict[Tuple[str, str], Dict[str, Any]]:
    class_key = {}
    for spec in table_specs.values():
        key_name = spec.get("business_key")
        if key_name:
            class_key[spec["class"]] = key_name
            for mapped in (spec.get("type_map") or {}).values():
                class_key[mapped] = key_name
    indexed: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for entity in entities:
        key_name = class_key.get(entity.get("type") or "")
        if not key_name:
            continue
        value = entity.get(key_name)
        if value in (None, ""):
            continue
        indexed[(key_name, str(value))] = entity
    return indexed


def apply_identifier_aliases(
    graph: Dict[str, Any],
    aliases_doc: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Attach alias names and inject alias entities for master-data keys."""
    aliases_doc = aliases_doc or load_yaml(MAPPING_DIR / "identifier_aliases.yaml")
    table_specs = load_yaml(MAPPING_DIR / "table_to_class.yaml")["tables"]
    entities = list(graph["entities"])
    indexed = _index_by_class_key(entities, table_specs)
    try:
        from semantica.normalize.entity_normalizer import EntityNormalizer

        normalizer = EntityNormalizer()
    except Exception:
        normalizer = None

    extra: List[Dict[str, Any]] = []
    for class_name, records in (aliases_doc.get("by_class") or {}).items():
        for record in records:
            business_key = str(record["business_key"])
            if class_name == "MachineTool":
                canonical = indexed.get(("assetCode", business_key))
            elif class_name == "CuttingTool":
                canonical = indexed.get(("toolId", business_key))
            else:
                canonical = next(
                    (
                        entity
                        for (key_name, value), entity in indexed.items()
                        if entity.get("type") == class_name and str(value) == business_key
                    ),
                    None,
                )
            if canonical is None:
                continue
            alias_names = list(record.get("aliases") or [])
            canonical_name = record.get("canonical_name") or canonical.get("name")
            canonical["name"] = canonical_name
            canonical["aliases"] = sorted(
                set(canonical.get("aliases") or []) | set(alias_names)
            )
            for alias in alias_names:
                extra_entity = {
                    "id": f"alias:{class_name}:{alias}",
                    "type": canonical.get("type") or class_name,
                    "name": alias,
                    "normalized_name": (
                        normalizer.normalize_entity(alias, entity_type=class_name)
                        if normalizer is not None
                        else alias.strip()
                    ),
                    "rdf_types": list(canonical.get("rdf_types") or [class_name]),
                }
                if class_name == "MachineTool":
                    extra_entity["assetCode"] = business_key
                elif class_name == "CuttingTool":
                    extra_entity["toolId"] = business_key
                extra.append(extra_entity)
    entities.extend(extra)
    graph = {**graph, "entities": entities}
    return graph


def merge_by_business_key(graph: Dict[str, Any]) -> Dict[str, Any]:
    """Exact-merge entities that share a master-data key (assetCode, toolId, ...)."""
    table_specs = load_yaml(MAPPING_DIR / "table_to_class.yaml")["tables"]
    key_by_type: Dict[str, str] = {}
    for spec in table_specs.values():
        key_name = spec.get("business_key")
        if not key_name:
            continue
        key_by_type[spec["class"]] = key_name
        for mapped in (spec.get("type_map") or {}).values():
            key_by_type[mapped] = key_name

    groups: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    unmatched: List[Dict[str, Any]] = []
    for entity in graph["entities"]:
        key_name = key_by_type.get(entity.get("type") or "")
        value = entity.get(key_name) if key_name else None
        if not key_name or value in (None, ""):
            unmatched.append(entity)
            continue
        groups.setdefault((key_name, str(value)), []).append(entity)

    merged: List[Dict[str, Any]] = []
    id_map: Dict[str, str] = {}
    for members in groups.values():
        canonical = next((item for item in members if not str(item["id"]).startswith("alias:")), members[0])
        aliases = []
        rdf_types = list(canonical.get("rdf_types") or [])
        for member in members:
            id_map[member["id"]] = canonical["id"]
            aliases.extend(member.get("aliases") or [])
            if member is not canonical:
                aliases.append(member.get("name"))
            for rdf_type in member.get("rdf_types") or []:
                if rdf_type not in rdf_types:
                    rdf_types.append(rdf_type)
        canonical["aliases"] = sorted({name for name in aliases if name and name != canonical.get("name")})
        canonical["rdf_types"] = rdf_types
        merged.append(canonical)

    remapped = []
    for rel in graph["relationships"]:
        source = id_map.get(rel["source"], rel["source"])
        target = id_map.get(rel["target"], rel["target"])
        remapped.append(
            {
                **rel,
                "source": source,
                "target": target,
                "source_id": source,
                "target_id": target,
            }
        )
    return {"entities": merged + unmatched, "relationships": remapped}


def operation_execution_associative_class() -> Any:
    """Declare OperationExecution as a temporal n-ary associative class."""
    builder = AssociativeClassBuilder()
    return builder.create_temporal_association(
        "OperationExecution",
        ["WorkOrder", "Operation", "MachineTool", "Operator", "CuttingTool"],
        properties={"startedAt": "xsd:dateTime", "endedAt": "xsd:dateTime"},
    )


def ingest_and_link(
    db_path: Optional[Union[str, Path]] = None,
    include_violations: bool = False,
    build_if_missing: bool = True,
) -> Dict[str, Any]:
    """Build (optionally) the sample DB, map rows, resolve aliases, and construct a KG."""
    path = Path(db_path) if db_path else None
    if path is None:
        path = build_sample_db(include_violations=include_violations)
    elif not path.exists():
        if not build_if_missing:
            raise FileNotFoundError(path)
        path = build_sample_db(path, include_violations=include_violations)

    tables = load_shop_tables(path)
    mapped = map_tables_to_graph(tables)
    aliased = apply_identifier_aliases(mapped)
    resolved = merge_by_business_key(aliased)
    leftover = EntityResolver(strategy="exact", similarity_threshold=1.0).resolve_entities(
        resolved["entities"]
    )
    graph = GraphBuilder(merge_entities=False, resolve_conflicts=False).build(
        {"entities": leftover, "relationships": resolved["relationships"]}
    )
    assoc = operation_execution_associative_class()
    metadata = dict(graph.get("metadata") or {})
    metadata["associative_classes"] = [
        {
            "name": assoc.name,
            "connects": list(assoc.connects),
            "temporal": assoc.temporal,
            "properties": dict(assoc.properties),
        }
    ]
    metadata["source_db"] = str(path)
    graph["metadata"] = metadata
    return graph


def neighbors(
    graph: Dict[str, Any],
    entity_id: str,
    rel_type: Optional[str] = None,
    direction: str = "out",
) -> List[str]:
    """Return neighboring entity IDs for a relationship type."""
    found: List[str] = []
    for rel in graph.get("relationships") or []:
        if rel_type and rel.get("type") != rel_type:
            continue
        if direction in {"out", "both"} and rel.get("source") == entity_id:
            found.append(rel.get("target"))
        if direction in {"in", "both"} and rel.get("target") == entity_id:
            found.append(rel.get("source"))
    return found


def entity_by_attribute(graph: Dict[str, Any], attr: str, value: Any) -> Optional[Dict[str, Any]]:
    """Find the first entity with a matching attribute."""
    for entity in graph.get("entities") or []:
        if entity.get(attr) == value:
            return entity
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest the machine-shop sample DB into a KG.")
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument("--violations", action="store_true")
    args = parser.parse_args()
    graph = ingest_and_link(args.db, include_violations=args.violations)
    print(
        f"entities={len(graph['entities'])} relationships={len(graph['relationships'])}"
    )


if __name__ == "__main__":
    main()
