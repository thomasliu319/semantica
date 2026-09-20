"""GraphRAG over the Explorer graph: lexical retrieve, 2-hop expand, record decision.

Does not require an LLM or FAISS. Hub nodes such as ``dataset:cleaned`` are
not expanded so a 2-hop walk cannot flood the evidence set.
"""

from __future__ import annotations

import re
from collections import defaultdict, deque
from typing import Any

from semantica.explorer.nl_metric_schema import metric_phrases, stop_phrases

MAX_QUERY_LEN = 500
DEFAULT_HOPS = 2
MAX_HOPS = 2
DEFAULT_SEEDS = 12
MAX_SOURCES = 16
_NEEDLE_RE = re.compile(r"[a-z0-9][a-z0-9_.:-]{1,}|[\u4e00-\u9fff]{2,}", re.IGNORECASE)
_CODE_RE = re.compile(r"^\d{6,}$")
_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
_MONTH_IN_TEXT_RE = re.compile(r"(20\d{2}-\d{2})")
_FULL_MONTH_RE = re.compile(r"(20\d{2})[-/.年](0?[1-9]|1[0-2])(?:月)?")
_BARE_MONTH_RE = re.compile(r"(0?[1-9]|1[0-2])月")
_RANGE_SEP_RE = re.compile(r"^(到|至|~|～|—|–|-)+$")
_MAX_MONTH_SPAN = 24
_NAME_RE = re.compile(r"^[\u4e00-\u9fff]{3,}$")
_TYPE_RE = re.compile(r"^[a-z][a-z0-9.-]*\d[a-z0-9.-]*$", re.IGNORECASE)
_STOP_NEEDLES = frozenset(
    {
        "设备",
        "工作",
        "情况",
        "运行",
        "小时",
        "时长",
        "分布",
        "报警",
        "客户",
        "机型",
        "为什么",
        "是不是",
        "能不能",
        "报警强度",
        "运行小时",
        "运行时长",
        "工作情况",
        "设备分布",
        "设备情况",
        "运行与报警",
        "运行时间",
        "运行天数",
        "运行日",
        *stop_phrases(),
    }
)


def _is_entity_name(token: str) -> bool:
    if not _NAME_RE.match(token) or token in _STOP_NEEDLES:
        return False
    return token.endswith(("区", "公司", "厂")) or "有限公司" in token


def _query_needles(query: str) -> list[str]:
    text = query
    for stop in sorted(_STOP_NEEDLES, key=len, reverse=True):
        text = text.replace(stop, " ")
    return [item.lower() for item in _NEEDLE_RE.findall(text)]


def _month_stamp(year: int | str, month: int | str) -> str:
    return f"{int(year):04d}-{int(month):02d}"


def _month_ord(stamp: str) -> int:
    year, month = stamp.split("-")
    return int(year) * 12 + int(month)


def _ord_to_month(value: int) -> str:
    year, month = divmod(value - 1, 12)
    return f"{year:04d}-{month + 1:02d}"


def _months_between(start: str, end: str) -> list[str]:
    lo, hi = _month_ord(start), _month_ord(end)
    if lo > hi:
        lo, hi = hi, lo
    if hi - lo > _MAX_MONTH_SPAN:
        return [start, end]
    return [_ord_to_month(idx) for idx in range(lo, hi + 1)]


def _extract_month_mentions(query: str) -> list[tuple[int, int, str]]:
    text = query or ""
    mentions: list[tuple[int, int, str]] = []
    consumed = [False] * len(text)
    for match in _FULL_MONTH_RE.finditer(text):
        stamp = _month_stamp(match.group(1), match.group(2))
        mentions.append((match.start(), match.end(), stamp))
        for index in range(match.start(), match.end()):
            consumed[index] = True
    last_year = int(mentions[-1][2][:4]) if mentions else None
    if last_year is not None:
        for match in _BARE_MONTH_RE.finditer(text):
            if any(consumed[index] for index in range(match.start(), match.end())):
                continue
            stamp = _month_stamp(last_year, match.group(1))
            mentions.append((match.start(), match.end(), stamp))
    mentions.sort(key=lambda item: item[0])
    return mentions


def _extract_months(query: str) -> list[str]:
    mentions = _extract_month_mentions(query)
    if not mentions:
        return []
    if len(mentions) == 2:
        between = (query or "")[mentions[0][1] : mentions[1][0]].strip()
        if between and _RANGE_SEP_RE.fullmatch(between):
            return _months_between(mentions[0][2], mentions[1][2])
    found: list[str] = []
    seen: set[str] = set()
    for _start, _end, stamp in mentions:
        if stamp in seen:
            continue
        seen.add(stamp)
        found.append(stamp)
    return found


def _parse_query(query: str) -> dict[str, list[str]]:
    needles = _query_needles(query)
    months = _extract_months(query)
    for month in months:
        if month not in needles:
            needles.append(month)
    return {
        "needles": needles,
        "codes": [item for item in needles if _CODE_RE.match(item)],
        "months": months,
        "names": [item for item in needles if _is_entity_name(item)],
        "types": [item for item in needles if _TYPE_RE.match(item)],
    }


def _node_month(node: dict[str, Any]) -> str:
    props = node.get("properties") or {}
    month = str(props.get("month") or "")
    if _MONTH_RE.match(month):
        return month
    found = _MONTH_IN_TEXT_RE.findall(str(node.get("id") or ""))
    return found[-1] if found else ""


def _node_type_code(node: dict[str, Any]) -> str:
    props = node.get("properties") or {}
    code = str(props.get("EquipTypeCode") or "")
    if code:
        return code.lower()
    node_id = str(node.get("id") or "")
    if node_id.startswith("slice:") and node_id.count(":") >= 2:
        return node_id.split(":")[1].lower()
    return ""


def _bind_dimension_sources(session: Any, query: str) -> list[dict[str, Any]]:
    parsed = _parse_query(query)
    months = parsed["months"]
    types = parsed["types"]
    codes = parsed["codes"]
    if not months or not (types or codes):
        return []
    bound: list[dict[str, Any]] = []
    if codes:
        nodes, _ = session.get_nodes(node_type="EquipMonth", skip=0, limit=20_000)
        wanted = set(codes)
        wanted_months = set(months)
        for node in nodes:
            hay = _haystack(node)
            if _node_month(node) in wanted_months and any(code in hay for code in wanted):
                bound.append(_source_from_node(node, 40.0, "retrieve", 0))
    if types:
        nodes, _ = session.get_nodes(node_type="TypeMonth", skip=0, limit=500)
        wanted = set(types)
        wanted_months = set(months)
        for node in nodes:
            if _node_type_code(node) in wanted and _node_month(node) in wanted_months:
                bound.append(_source_from_node(node, 48.0, "retrieve", 0))
    bound.sort(key=lambda row: (0 if row["type"] == "TypeMonth" else 1, row["id"]))
    return bound


def _prefer_bound_sources(bound: list[dict[str, Any]], sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not bound:
        return sources
    bound_ids = {row["id"] for row in bound}
    head = [row for row in sources if row["id"] in bound_ids]
    tail = [row for row in sources if row["id"] not in bound_ids]
    return (head + tail)[:MAX_SOURCES]


def _keep_asked_months(session: Any, query: str, sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    months = set(_parse_query(query)["months"])
    if not months:
        return sources
    kept: list[dict[str, Any]] = []
    for row in sources:
        if row.get("type") not in {"TypeMonth", "EquipMonth", "Month"}:
            kept.append(row)
            continue
        node = session.get_node(row["id"]) or {}
        if _node_month(node) in months:
            kept.append(row)
    return kept[:MAX_SOURCES]


MAX_ENTITIES = 8
MAX_PATH_EDGES = 24
HUB_IDS = frozenset({"dataset:cleaned"})
PREFERRED_TYPES = frozenset(
    {
        "TypeMonth",
        "Month",
        "EquipType",
        "AlarmCode",
        "ProgramCode",
        "decision",
        "process",
        "system",
        "MeasureDomain",
        "Customer",
        "Area",
        "DataQuality",
        "IncompleteEquip",
        "Equip",
        "EquipMonth",
        "language",
        "concept",
        "drug",
        "event",
    }
)
MAX_NEIGHBORS_PER_NODE = 8


def run_graphrag(
    session: Any,
    query: str,
    *,
    max_hops: int = DEFAULT_HOPS,
    max_results: int = DEFAULT_SEEDS,
) -> dict[str, Any]:
    text = (query or "").strip()
    if not text:
        raise ValueError("query must not be empty")
    if len(text) > MAX_QUERY_LEN:
        raise ValueError(f"query must be {MAX_QUERY_LEN} characters or less")
    hops = int(max_hops)
    if hops < 1 or hops > MAX_HOPS:
        raise ValueError(f"max_hops must be 1..{MAX_HOPS}")
    limit = int(max_results)
    if limit < 1 or limit > 20:
        raise ValueError("max_results must be 1..20")

    compiled = None
    try:
        from semantica.explorer.nl2sparql import compile_and_run

        compiled = compile_and_run(session, text)
    except Exception:
        compiled = None
    sparql_sources: list[dict[str, Any]] = []
    compose_rows: list[dict[str, Any]] | None = None
    if compiled:
        parsed = _parse_query(text)
        compose_rows = _align_asked_months(
            compiled["compose"],
            parsed["months"],
            text,
            parsed,
        )
        from semantica.explorer.nl2sparql import hydrate_compose_rows

        compose_rows = hydrate_compose_rows(session, compose_rows)
        for row in compose_rows:
            if row.get("missing") or not row.get("id"):
                continue
            node = session.get_node(row["id"])
            if node:
                sparql_sources.append(_source_from_node(node, 52.0, "sparql", 0))
    seeds = _retrieve_seeds(session, text, limit)
    bound = _bind_dimension_sources(session, text)
    seen = {row["id"] for row in sparql_sources}
    seen.update(row["id"] for row in bound)
    seeds = sparql_sources + bound + [row for row in seeds if row["id"] not in seen]
    seed_cap = max(limit, min(len(sparql_sources) + len(bound), MAX_SOURCES))
    seeds = seeds[:seed_cap]
    sparql_hit = bool(compiled and compiled.get("rows"))
    if compiled and not sparql_hit and compose_rows and any(not row.get("missing") for row in compose_rows):
        sparql_hit = True
    if compiled and sparql_hit:
        walk = {"nodes": {row["id"]: 0 for row in seeds}, "edges": []}
        sources = list(sparql_sources) or _merge_sources(session, seeds, walk)
        sources = _prefer_bound_sources(sparql_sources or bound, sources)
    else:
        if compiled and not sparql_hit:
            compiled = None
            compose_rows = None
        walk = _expand(session, [row["id"] for row in seeds], hops)
        sources = _merge_sources(session, seeds, walk)
        sources = _prefer_bound_sources(bound, sources)
    sources = _keep_asked_months(session, text, sources)
    path_edges = _select_path_edges(walk["edges"], {row["id"] for row in seeds})
    confidence = _confidence(sources) if sources else (0.95 if compiled else 0.0)
    reasoning_path = _format_path(session, path_edges)
    response = _summarize(
        session,
        text,
        sources,
        reasoning_path,
        confidence,
        compiled=compiled,
        compose_rows=compose_rows,
    )
    entity_ids = _entity_ids(sources)
    outcome = "answered" if sources else "no_evidence"

    decision_id = session.graph.record_decision(
        category="graphrag_query",
        scenario=text,
        reasoning=response,
        outcome=outcome,
        confidence=confidence,
        entities=entity_ids,
        decision_maker="explorer-graphrag",
    )
    session.handle_graph_mutation(
        "ADD_NODE",
        decision_id,
        session.get_node(decision_id) or {"id": decision_id, "type": "decision"},
    )

    chain = [
        {
            "id": neighbor.get("id"),
            "type": neighbor.get("type"),
            "relationship": neighbor.get("relationship"),
            "hop": neighbor.get("hop"),
            "content": neighbor.get("content", ""),
        }
        for neighbor in session.get_neighbors(decision_id, 5)
        if neighbor.get("id") not in HUB_IDS
    ]
    return {
        "decision_id": decision_id,
        "query": text,
        "response": response,
        "reasoning_path": reasoning_path,
        "confidence": confidence,
        "outcome": outcome,
        "num_sources": len(sources),
        "num_reasoning_paths": 1 if path_edges else 0,
        "sparql": (compiled or {}).get("sparql", "") if compiled else "",
        "mapping": (compiled or {}).get("mapping", []) if compiled else [],
        "sources": sources,
        "path": [
            {
                "source": src,
                "relationship": rel,
                "target": dst,
                "hop": hop,
            }
            for src, rel, dst, hop in path_edges
        ],
        "chain": chain,
    }


def _retrieve_seeds(session: Any, query: str, limit: int) -> list[dict[str, Any]]:
    parsed = _parse_query(query)
    needles = parsed["needles"]
    codes = parsed["codes"]
    months = parsed["months"]
    names = parsed["names"]
    types = parsed["types"]
    merged: dict[str, dict[str, Any]] = {}
    for hit in session.search(query, limit=max(limit * 3, 24)):
        node = hit.get("node") or {}
        node_id = str(node.get("id") or "")
        if not node_id or node_id in HUB_IDS:
            continue
        haystack = _haystack(node)
        if not _matches_constraints(haystack, node_id, codes, months, names, types):
            continue
        merged[node_id] = _source_from_node(
            node,
            float(hit.get("score") or 0) + _bonus(haystack, codes, months, names, types, node),
            "retrieve",
            0,
        )
    for extra in _scan_needles(session, codes, months, names, types, needles, limit * 3):
        current = merged.get(extra["id"])
        if current is None or extra["score"] > current["score"]:
            merged[extra["id"]] = extra
    ranked = sorted(merged.values(), key=lambda row: (-float(row["score"]), row["id"]))
    if names and not codes:
        dim_nodes = [row for row in ranked if row["type"] in {"Area", "Customer"}]
        other = [row for row in ranked if row["type"] not in {"Area", "Customer"}]
        ranked = dim_nodes + other
    if types and months:
        slices = [row for row in ranked if row["type"] == "TypeMonth"]
        other = [row for row in ranked if row["type"] != "TypeMonth"]
        ranked = slices + other
    return ranked[:limit]


def _metric_tokens(props: dict[str, Any]) -> list[str]:
    tokens: list[str] = []
    for key in ("run_hours", "run_days", "alarm_count", "devices", "alarm_per_run_hour"):
        value = props.get(key)
        if value in (None, ""):
            continue
        tokens.append(str(value))
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        tokens.append(str(int(round(number))))
    return tokens


def _haystack(node: dict[str, Any]) -> str:
    props = node.get("properties") or {}
    return " ".join(
        [
            str(node.get("id") or ""),
            str(node.get("content") or ""),
            str(node.get("type") or ""),
            str(props.get("OutFactoryCode") or ""),
            str(props.get("CompanyName") or ""),
            str(props.get("AreaName") or ""),
            str(props.get("month") or ""),
            str(props.get("EquipTypeCode") or ""),
            *_metric_tokens(props),
        ]
    ).lower()


def _matches_constraints(
    haystack: str,
    node_id: str,
    codes: list[str],
    months: list[str],
    names: list[str],
    types: list[str],
) -> bool:
    if codes and not any(code in haystack for code in codes):
        return False
    if types and not any(item in haystack for item in types):
        return False
    if months and node_id.startswith(("equipmonth:", "slice:", "month:")):
        return any(month in haystack for month in months)
    if names and not codes:
        return any(name in haystack for name in names)
    return True


def _bonus(
    haystack: str,
    codes: list[str],
    months: list[str],
    names: list[str],
    types: list[str],
    node: dict[str, Any],
) -> float:
    score = 0.0
    score += 3.0 * sum(1 for code in codes if code in haystack)
    score += 2.5 * sum(1 for item in types if item in haystack)
    score += 2.0 * sum(1 for month in months if month in haystack)
    score += 2.0 * sum(1 for name in names if name in haystack)
    node_type = str(node.get("type") or "")
    if names and node_type in {"Area", "Customer"}:
        score += 80.0
    if types and months and node_type == "TypeMonth":
        score += 3.0
    if node_type in PREFERRED_TYPES:
        score += 0.4
    return score


def _scan_needles(
    session: Any,
    codes: list[str],
    months: list[str],
    names: list[str],
    types: list[str],
    needles: list[str],
    limit: int,
) -> list[dict[str, Any]]:
    if not (codes or months or names or types or needles):
        return []
    nodes, _ = session.get_nodes(skip=0, limit=50_000)
    scored: list[tuple[float, dict[str, Any]]] = []
    for node in nodes:
        node_id = str(node.get("id") or "")
        if not node_id or node_id in HUB_IDS:
            continue
        haystack = _haystack(node)
        if not _matches_constraints(haystack, node_id, codes, months, names, types):
            continue
        weak = sum(1 for needle in needles if needle in haystack)
        if weak == 0:
            continue
        score = _bonus(haystack, codes, months, names, types, node) + 0.15 * weak
        scored.append((score, _source_from_node(node, round(score, 4), "retrieve", 0)))
    scored.sort(key=lambda item: (-item[0], item[1]["id"]))
    return [row for _score, row in scored[:limit]]


def _expand(session: Any, seed_ids: list[str], max_hops: int) -> dict[str, Any]:
    adjacency = _undirected_adjacency(session)
    hops = {node_id: 0 for node_id in seed_ids}
    visited = set(seed_ids)
    edges: list[tuple[str, str, str, int]] = []
    queue = deque((node_id, 0) for node_id in seed_ids)
    while queue:
        current, depth = queue.popleft()
        if depth >= max_hops or current in HUB_IDS:
            continue
        ranked = _rank_neighbors(session, adjacency.get(current, ()))
        for neighbor, rel, outgoing in ranked:
            if neighbor in HUB_IDS:
                continue
            hop = depth + 1
            src, dst = (current, neighbor) if outgoing else (neighbor, current)
            edges.append((src, rel, dst, hop))
            if neighbor in visited:
                continue
            visited.add(neighbor)
            hops[neighbor] = hop
            queue.append((neighbor, hop))
            if len(visited) >= 48:
                return {"nodes": hops, "edges": edges}
    return {"nodes": hops, "edges": edges}


def _undirected_adjacency(session: Any) -> dict[str, list[tuple[str, str, bool]]]:
    edges, _ = session.get_edges(skip=0, limit=50_000)
    adjacency: dict[str, list[tuple[str, str, bool]]] = defaultdict(list)
    seen: set[tuple[str, str, str]] = set()
    for edge in edges:
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        rel = str(edge.get("type") or "relatedTo")
        if not source or not target or source == target:
            continue
        key = (source, rel, target)
        if key in seen:
            continue
        seen.add(key)
        adjacency[source].append((target, rel, True))
        adjacency[target].append((source, rel, False))
    return adjacency


def _rank_neighbors(
    session: Any,
    neighbors: list[tuple[str, str, bool]],
) -> list[tuple[str, str, bool]]:
    scored: list[tuple[int, str, str, bool]] = []
    for neighbor, rel, outgoing in neighbors:
        node = session.get_node(neighbor) or {}
        preferred = 0 if str(node.get("type") or "") in PREFERRED_TYPES else 1
        scored.append((preferred, neighbor, rel, outgoing))
    scored.sort(key=lambda item: (item[0], item[1]))
    return [(neighbor, rel, outgoing) for _rank, neighbor, rel, outgoing in scored[:MAX_NEIGHBORS_PER_NODE]]


def _merge_sources(
    session: Any,
    seeds: list[dict[str, Any]],
    walk: dict[str, Any],
) -> list[dict[str, Any]]:
    by_id = {row["id"]: row for row in seeds}
    for node_id, hop in walk["nodes"].items():
        if node_id in by_id:
            continue
        node = session.get_node(node_id)
        if not node:
            continue
        decay = 1.0 / (1 + hop)
        by_id[node_id] = _source_from_node(node, round(0.35 * decay, 4), "expand", hop)
    ranked = sorted(
        by_id.values(),
        key=lambda row: (
            0 if row["type"] in PREFERRED_TYPES else 1,
            -float(row["score"]),
            row["hop"],
            row["id"],
        ),
    )
    return ranked[:MAX_SOURCES]


def _source_from_node(node: dict[str, Any], score: float, kind: str, hop: int) -> dict[str, Any]:
    properties = node.get("properties") or {}
    content = str(node.get("content") or properties.get("content") or "")
    return {
        "id": str(node.get("id") or ""),
        "type": str(node.get("type") or ""),
        "content": content,
        "score": float(score),
        "kind": kind,
        "hop": int(hop),
        "facts": _facts_from_props(str(node.get("type") or ""), properties),
    }


def _select_path_edges(
    edges: list[tuple[str, str, str, int]],
    seed_ids: set[str],
) -> list[tuple[str, str, str, int]]:
    if not edges:
        return []
    chosen: list[tuple[str, str, str, int]] = []
    seen: set[tuple[str, str, str]] = set()
    for src, rel, dst, hop in sorted(edges, key=lambda item: (item[3], item[0], item[2])):
        key = (src, rel, dst)
        if key in seen:
            continue
        if seed_ids and src not in seed_ids and dst not in seed_ids and hop > 1:
            if not any(item[2] == src or item[0] == src for item in chosen):
                continue
        seen.add(key)
        chosen.append((src, rel, dst, hop))
        if len(chosen) >= MAX_PATH_EDGES:
            break
    return chosen


_FACT_LABELS = {
    "devices": "设备",
    "run_hours": "运行",
    "run_days": "运行日",
    "alarm_count": "报警",
    "alarm_per_run_hour": "报警强度",
    "mean_run_rate_pct": "运行占比",
    "run_hours_per_device": "单台运行",
    "CompanyName": "客户",
    "AreaName": "区域",
    "month": "月份",
    "EquipTypeCode": "机型",
}
_TYPE_FACTS = {
    "Area": ("devices", "run_hours", "alarm_count", "alarm_per_run_hour"),
    "Customer": ("run_hours", "devices", "alarm_count"),
    "Equip": ("run_hours", "mean_run_rate_pct", "EquipTypeCode", "AreaName", "CompanyName"),
    "EquipMonth": ("month", "run_hours", "alarm_count", "alarm_per_run_hour", "EquipTypeCode"),
    "TypeMonth": ("month", "run_hours", "run_days", "devices", "alarm_count", "alarm_per_run_hour"),
    "Month": ("run_hours", "alarm_count"),
    "EquipType": ("run_hours", "alarm_count"),
}
_KIND_ZH = {"retrieve": "召回", "expand": "扩图", "sparql": "SPARQL"}
_METRIC_PHRASES = tuple(metric_phrases())
_RATIO_PARTS = {
    "alarm_per_run_hour": ("alarm_count", "run_hours"),
}
_ADDITIVE_FIELDS = frozenset(
    {
        "run_hours",
        "run_days",
        "alarm_count",
        "alarm_shutdown_count",
        "program_cycles",
        "program_seconds",
        "progress_output",
    }
)


def _format_path(session: Any, edges: list[tuple[str, str, str, int]]) -> str:
    if not edges:
        return ""
    lines = [
        "| # | 起点 | 关系 | 终点 |",
        "| --- | --- | --- | --- |",
    ]
    for index, (src, rel, dst, _hop) in enumerate(edges[:12], start=1):
        lines.append(
            f"| {index} | {_md_cell(_label(session, src))} | `{rel}` | {_md_cell(_label(session, dst))} |"
        )
    return "\n".join(lines)


def _label(session: Any, node_id: str) -> str:
    node = session.get_node(node_id) or {}
    content = str(node.get("content") or "").strip()
    return content or node_id


def _md_cell(value: Any) -> str:
    text = " ".join(str(value or "").split())
    return text.replace("|", "\\|")


def _fmt_fact(key: str, value: Any) -> str | None:
    if value in (None, "", "None"):
        return None
    label = _FACT_LABELS.get(key, key)
    if isinstance(value, bool):
        return f"{label} {value}"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        if key.endswith("_pct"):
            return f"{label} {number:.1f}%"
        if key in {"devices", "run_days", "alarm_count"}:
            return f"{label} {int(round(number))}"
        if abs(number) >= 100 or number.is_integer():
            return f"{label} {number:.0f}"
        return f"{label} {number:.2f}"
    return f"{label} {value}"


def _facts_from_props(node_type: str, props: dict[str, Any]) -> str:
    keys = _TYPE_FACTS.get(node_type, ("run_hours", "alarm_count", "CompanyName", "AreaName"))
    parts = []
    for key in keys:
        formatted = _fmt_fact(key, props.get(key))
        if formatted:
            parts.append(formatted)
    return " · ".join(parts)


def _source_facts(session: Any, source: dict[str, Any]) -> str:
    if source.get("facts"):
        return str(source["facts"])
    node = session.get_node(source["id"]) or {}
    return _facts_from_props(str(source.get("type") or ""), node.get("properties") or {})


def _metric_specs(query: str) -> list[tuple[str, str, str]]:
    found: list[tuple[int, str, str, str]] = []
    seen: set[str] = set()
    for phrase, key, zh, how in sorted(_METRIC_PHRASES, key=lambda item: -len(item[0])):
        idx = query.find(phrase)
        if idx < 0 or key in seen:
            continue
        seen.add(key)
        found.append((idx, key, zh, how))
    found.sort(key=lambda item: item[0])
    return [(key, zh, how) for _idx, key, zh, how in found]


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt_total(number: float, key: str) -> str:
    if key in {"devices", "run_days", "alarm_count"}:
        return str(int(round(number)))
    if abs(number - round(number)) < 0.05:
        return f"{number:.0f}"
    if abs(number) >= 100:
        return f"{number:.1f}"
    return f"{number:.2f}"


def _scope_label(query: str, parsed: dict[str, list[str]], rows: list[dict[str, Any]]) -> str:
    for row in rows:
        content = str(row.get("content") or "")
        if row.get("type") in {"TypeMonth", "EquipMonth"} and content:
            return content.rsplit(" ", 1)[0]
        if content:
            return content
    match = re.search(r"[A-Za-z][A-Za-z0-9.-]*\d[A-Za-z0-9.-]*", query or "")
    if match:
        return match.group(0)
    if parsed.get("codes"):
        return parsed["codes"][0]
    return ""


def _placeholder_row(scope: str, month: str, parsed: dict[str, list[str]]) -> dict[str, Any]:
    kind = "TypeMonth" if parsed.get("types") else "EquipMonth" if parsed.get("codes") else "Month"
    label = f"{scope} {month}".strip()
    return {
        "id": f"missing:{kind}:{month}",
        "type": kind,
        "content": label,
        "month": month,
        "props": {},
        "missing": True,
    }


def _align_asked_months(
    rows: list[dict[str, Any]],
    months: list[str],
    query: str,
    parsed: dict[str, list[str]],
) -> list[dict[str, Any]]:
    if not months:
        return rows
    by_month: dict[str, dict[str, Any]] = {}
    for row in rows:
        month = row.get("month") or ""
        if month and month not in by_month:
            by_month[month] = row
    scope = _scope_label(query, parsed, rows)
    return [by_month[month] if month in by_month else _placeholder_row(scope, month, parsed) for month in months]


def _compose_rows(session: Any, query: str, sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    parsed = _parse_query(query)
    months = parsed["months"]
    types = {item.lower() for item in parsed["types"]}
    codes = set(parsed["codes"])
    bound = _bind_dimension_sources(session, query)
    pool = bound or [row for row in sources if row.get("type") in {"TypeMonth", "EquipMonth", "Month", "Area", "Customer", "Equip"}]
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in pool:
        if not item.get("id"):
            continue
        node = session.get_node(item["id"]) or {}
        node_id = str(node.get("id") or item["id"])
        if node_id in seen:
            continue
        seen.add(node_id)
        props = node.get("properties") or {}
        month = _node_month(node)
        node_type = str(node.get("type") or item.get("type") or "")
        if months and node_type in {"TypeMonth", "EquipMonth", "Month"} and month not in months:
            continue
        if types and node_type == "TypeMonth" and _node_type_code(node) not in types:
            continue
        if codes and node_type == "EquipMonth" and not any(code in _haystack(node) for code in codes):
            continue
        rows.append(
            {
                "id": node_id,
                "type": node_type,
                "content": str(node.get("content") or item.get("content") or node_id),
                "month": month,
                "props": props,
            }
        )
    preferred = ("TypeMonth", "EquipMonth", "Month", "Area", "Customer", "Equip")
    if any(row["type"] == "TypeMonth" for row in rows):
        rows = [row for row in rows if row["type"] == "TypeMonth"]
    elif any(row["type"] == "EquipMonth" for row in rows):
        rows = [row for row in rows if row["type"] == "EquipMonth"]
    rows.sort(key=lambda row: (preferred.index(row["type"]) if row["type"] in preferred else 9, row["month"], row["id"]))
    return _align_asked_months(rows, months, query, parsed)


def _format_metric_block(field: str, label: str, how: str, rows: list[dict[str, Any]]) -> str:
    usable = []
    for row in rows:
        if row.get("missing"):
            usable.append({**row, "value": None})
            continue
        if how == "ratio":
            num_key, den_key = _RATIO_PARTS[field]
            num, den = _number(row["props"].get(num_key)), _number(row["props"].get(den_key))
            value = (num / den) if num is not None and den not in (None, 0) else _number(row["props"].get(field))
        else:
            value = _number(row["props"].get(field))
        if value is None and not row.get("missing"):
            usable.append({**row, "value": None, "missing": True})
            continue
        usable.append({**row, "value": value})
    if not usable:
        return ""
    valued = [row for row in usable if row.get("value") is not None]
    list_months = how == "each" or len(usable) > 1 or any(row.get("missing") for row in usable)
    if not list_months:
        parts = [f"{row['content']} {label} {_fmt_total(row['value'], field)}" for row in valued]
        return "；".join(parts)
    if how == "ratio":
        num_key, den_key = _RATIO_PARTS[field]
        num = sum(_number(row["props"].get(num_key)) or 0.0 for row in valued)
        den = sum(_number(row["props"].get(den_key)) or 0.0 for row in valued)
        total = (num / den) if den else None
    else:
        total = sum(row["value"] for row in valued) if field in _ADDITIVE_FIELDS or how == "sum" else None
    scope = usable[0]["content"].rsplit(" ", 1)[0] if usable[0]["type"] in {"TypeMonth", "EquipMonth"} else usable[0]["content"]
    window = "+".join(row["month"] for row in usable if row.get("month"))
    if total is not None:
        lines = [f"{scope} {window or '合计'} {label} = {_fmt_total(total, field)}"]
    else:
        lines = [f"{scope} {window} {label}".strip()]
    for row in usable:
        stamp = row["month"] or row["content"]
        if row.get("missing") or row.get("value") is None:
            lines.append(f"- {stamp}：图上无切片")
        else:
            lines.append(f"- {stamp}：{_fmt_total(row['value'], field)}")
    if total is not None:
        lines.append(f"- 合计：{_fmt_total(total, field)}")
    return "\n".join(lines)


def _metric_answer(
    session: Any,
    query: str,
    sources: list[dict[str, Any]],
    compose_rows: list[dict[str, Any]] | None = None,
) -> str:
    specs = _metric_specs(query)
    if not specs:
        return ""
    rows = compose_rows if compose_rows is not None else _compose_rows(session, query, sources)
    blocks = [_format_metric_block(field, label, how, rows) for field, label, how in specs]
    return "\n\n".join(block for block in blocks if block)


def _mapping_markdown(compiled: dict[str, Any] | None) -> list[str]:
    if not compiled:
        return []
    mapping = compiled.get("mapping") or []
    sparql = str(compiled.get("sparql") or "").strip()
    lines = [
        "",
        "### 模式映射",
        "",
        "| 自然语言 | 清洗表 | 图类型 | JOIN | 指标 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in mapping:
        lines.append(
            "| {nl} | {table} | {node} | {joins} | {metrics} |".format(
                nl=_md_cell(row.get("nl")),
                table=_md_cell(row.get("table")),
                node=_md_cell(row.get("node")),
                joins=_md_cell(row.get("joins")),
                metrics=_md_cell(row.get("metrics")),
            )
        )
    if sparql:
        lines.extend(["", "### SPARQL", "", "```sparql", sparql, "```"])
    return lines


def _summarize(
    session: Any,
    query: str,
    sources: list[dict[str, Any]],
    reasoning_path: str,
    confidence: float,
    compiled: dict[str, Any] | None = None,
    compose_rows: list[dict[str, Any]] | None = None,
) -> str:
    answer = _metric_answer(session, query, sources, compose_rows)
    if not sources and not answer:
        return f"## {query}\n\n图上没有检索到相连的证据节点。"
    how = "模式映射 + SPARQL" if compiled else f"词法召回 + {DEFAULT_HOPS} 跳扩图"
    lines = [
        f"## {query}",
        "",
        f"检索到 **{len(sources)}** 条图证据（{how}）。置信度 **{confidence:.2f}**。",
    ]
    if answer:
        lines.extend(["", "### 答案", "", answer])
    lines.extend(_mapping_markdown(compiled))
    lines.extend(
        [
            "",
            "### 主要命中",
            "",
            "| 节点 | 类型 | 来源 | 要点 |",
            "| --- | --- | --- | --- |",
        ]
    )
    for row in sources[:6]:
        lines.append(
            "| {name} | {typ} | {kind} | {facts} |".format(
                name=_md_cell(row.get("content") or row.get("id")),
                typ=_md_cell(row.get("type")),
                kind=_KIND_ZH.get(str(row.get("kind") or ""), str(row.get("kind") or "")),
                facts=_md_cell(_source_facts(session, row)),
            )
        )
    if reasoning_path:
        lines.extend(["", "### 证据链", "", reasoning_path])
    lines.extend(
        [
            "",
            "### 全部证据",
            "",
            "| # | 来源 | 跳数 | 类型 | 节点 | 要点 |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for index, row in enumerate(sources, start=1):
        lines.append(
            "| {n} | {kind} | {hop} | {typ} | {name} | {facts} |".format(
                n=index,
                kind=_KIND_ZH.get(str(row.get("kind") or ""), str(row.get("kind") or "")),
                hop=int(row.get("hop") or 0),
                typ=_md_cell(row.get("type")),
                name=_md_cell(row.get("content") or row.get("id")),
                facts=_md_cell(_source_facts(session, row)),
            )
        )
    return "\n".join(lines)


def _entity_ids(sources: list[dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    ordered = [row for row in sources if row["type"] in PREFERRED_TYPES] + [
        row for row in sources if row["type"] not in PREFERRED_TYPES
    ]
    for row in ordered:
        node_id = row["id"]
        if node_id and node_id not in ids and node_id not in HUB_IDS and len(node_id) <= 200:
            ids.append(node_id)
        if len(ids) >= MAX_ENTITIES:
            break
    return ids


def _confidence(sources: list[dict[str, Any]]) -> float:
    retrieved = [row for row in sources if row.get("kind") == "retrieve"]
    pool = retrieved or sources
    if not pool:
        return 0.0
    mean = sum(float(row["score"]) for row in pool) / len(pool)
    return round(min(1.0, max(0.0, mean if mean <= 1 else mean / (mean + 1))), 4)
