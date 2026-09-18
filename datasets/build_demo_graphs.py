"""Build Explorer-ready ContextGraph JSON files from in-repo demo sources."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

from semantica.context.context_graph import ContextGraph
from semantica.explorer.iot_metrics import DEVICE_DAY_NAMED, PRESETS, stamp_metrics

OUT_DIR = Path(__file__).resolve().parent / "json"
PROCESSED_IOT = Path(__file__).resolve().parent / "processed" / "iot_mar_aug_2026"


def _save(graph: ContextGraph, filename: str, *, source: str, title: str, tags: list[str]) -> dict:
    path = OUT_DIR / filename
    graph.save_to_file(str(path))
    payload = json.loads(path.read_text(encoding="utf-8"))
    meta = {
        "file": filename,
        "title": title,
        "source": source,
        "tags": tags,
        "node_count": len(payload.get("nodes", [])),
        "edge_count": len(payload.get("edges", [])),
        "explorer": f'SEMANTICA_ALLOW_ANONYMOUS=true semantica-explorer --graph datasets/json/{filename}',
    }
    print(f"  {filename:32} {meta['node_count']:3} nodes  {meta['edge_count']:3} edges")
    return meta


def alice_bob_acme() -> ContextGraph:
    graph = ContextGraph(advanced_analytics=False)
    graph.add_node("alice", "Person", content="Alice", color="#63E6FF")
    graph.add_node("bob", "Person", content="Bob", color="#63E6FF")
    graph.add_node("acme", "Organization", content="Acme", color="#A78BFA")
    graph.add_node("new_york", "Location", content="New York", color="#34D399")
    graph.add_edge("alice", "acme", "WORKS_AT")
    graph.add_edge("bob", "alice", "KNOWS")
    graph.add_edge("acme", "new_york", "LOCATED_IN")
    return graph


def apple_inc() -> ContextGraph:
    graph = ContextGraph(advanced_analytics=False)
    graph.add_node("apple", "Organization", content="Apple Inc.", founded="1976")
    graph.add_node("steve_jobs", "Person", content="Steve Jobs")
    graph.add_node("tim_cook", "Person", content="Tim Cook")
    graph.add_node("cupertino", "Location", content="Cupertino")
    graph.add_node("california", "Location", content="California")
    graph.add_edge("steve_jobs", "apple", "FOUNDED", valid_from="1976-04-01")
    graph.add_edge("tim_cook", "apple", "CEO_OF")
    graph.add_edge("apple", "cupertino", "HEADQUARTERED_IN")
    graph.add_edge("cupertino", "california", "LOCATED_IN")
    return graph


def tech_corp() -> ContextGraph:
    graph = ContextGraph(advanced_analytics=False)
    graph.add_node("alice", "Person", content="Alice", age=30)
    graph.add_node("bob", "Person", content="Bob", age=35)
    graph.add_node("tech_corp", "Organization", content="Tech Corp", founded=2010)
    graph.add_node("sf", "Location", content="San Francisco", country="USA")
    graph.add_edge("alice", "bob", "knows", since=2020)
    graph.add_edge("alice", "tech_corp", "works_for", role="Engineer")
    graph.add_edge("tech_corp", "sf", "located_in")
    return graph


def lab_alpha() -> ContextGraph:
    graph = ContextGraph(advanced_analytics=False)
    graph.add_node("alice", "Person", content="Alice Chen", role="Engineer", valid_from="2020-01-15")
    graph.add_node("bob", "Person", content="Bob Jones", role="CTO", valid_from="2020-03-01")
    graph.add_node("chen", "Person", content="Dr Chen", role="Researcher", valid_from="2021-06-01")
    graph.add_node("lab_alpha", "Organization", content="Lab Alpha", budget="High", valid_from="2020-01-01")
    graph.add_node("tech_corp", "Organization", content="Tech Corp", founded="2010")
    graph.add_node("startup_beta", "SpinOff", content="Startup Beta", valuation="5M", valid_from="2023-01-01")
    graph.add_node("sf", "Location", content="San Francisco", country="USA")
    graph.add_node("paper_x", "Publication", content="Paper X", citations=50, valid_from="2020-11-20")
    graph.add_node("paper_y", "Publication", content="Paper Y", citations=25, valid_from="2022-03-15")
    graph.add_node("grant_a", "Funding", content="Grant A", amount=1000000, valid_from="2021-01-01", valid_until="2022-12-31")
    graph.add_edge("alice", "lab_alpha", "WORKS_AT", valid_from="2020-01-15")
    graph.add_edge("bob", "lab_alpha", "WORKS_AT", valid_from="2020-03-01")
    graph.add_edge("chen", "lab_alpha", "WORKS_AT", valid_from="2021-06-01")
    graph.add_edge("alice", "bob", "KNOWS", since="2020")
    graph.add_edge("alice", "tech_corp", "WORKS_FOR", role="Engineer")
    graph.add_edge("tech_corp", "sf", "LOCATED_IN")
    graph.add_edge("alice", "paper_x", "AUTHORED", valid_from="2020-11-20")
    graph.add_edge("bob", "paper_x", "AUTHORED", valid_from="2020-11-20")
    graph.add_edge("chen", "paper_y", "AUTHORED", valid_from="2022-03-15")
    graph.add_edge("alice", "paper_y", "AUTHORED", valid_from="2022-03-15")
    graph.add_edge("lab_alpha", "grant_a", "RECEIVED", valid_from="2021-01-01")
    graph.add_edge("lab_alpha", "startup_beta", "SPUN_OFF", valid_from="2023-01-01")
    graph.add_edge("bob", "startup_beta", "CTO", valid_from="2023-02-01")
    return graph


def startup_investment() -> ContextGraph:
    graph = ContextGraph(advanced_analytics=False)
    graph.add_node("startup_1", "Startup", content="TechFlow AI", revenue=1000000, founded="2021-01-01")
    graph.add_node("startup_2", "Startup", content="GreenEnergy Co", revenue=500000, founded="2020-05-15")
    graph.add_node("investor_1", "Investor", content="Venture Capital X")
    graph.add_node("founder_1", "Person", content="Alice Chen")
    graph.add_node("founder_2", "Person", content="Bob Smith")
    graph.add_edge("founder_1", "startup_1", "FOUNDED", valid_from="2021-01-01")
    graph.add_edge("investor_1", "startup_1", "INVESTED_IN", amount=5000000, valid_from="2023-06-01")
    graph.add_edge("founder_1", "startup_2", "ADVISED", valid_from="2020-01-01", valid_until="2021-01-01")
    graph.add_edge("founder_2", "startup_2", "FOUNDED", valid_from="2020-05-15")
    return graph


def company_aliases() -> ContextGraph:
    graph = ContextGraph(advanced_analytics=False)
    graph.add_node("e1", "Company", content="Apple Inc.", industry="Technology", hq="Cupertino", founded=1976)
    graph.add_node("e2", "Company", content="Apple Inc", industry="Tech", hq="Cupertino, CA")
    graph.add_node("e3", "Company", content="Apple", industry="Consumer Electronics")
    graph.add_node("e4", "Company", content="Microsoft Corp", industry="Software", hq="Redmond")
    graph.add_node("e5", "Company", content="Microsoft", industry="Tech", hq="Redmond, WA")
    graph.add_node("e6", "Company", content="Google LLC", industry="Internet")
    graph.add_node("steve_jobs", "Person", content="Steve Jobs")
    graph.add_node("tim_cook", "Person", content="Tim Cook")
    graph.add_edge("e1", "steve_jobs", "founded_by")
    graph.add_edge("e3", "tim_cook", "ceo")
    graph.add_edge("e1", "e2", "same_as_candidate")
    graph.add_edge("e1", "e3", "same_as_candidate")
    graph.add_edge("e4", "e5", "same_as_candidate")
    return graph


def disease_network() -> ContextGraph:
    graph = ContextGraph(advanced_analytics=False)
    diseases = [
        {
            "name": "Type 2 Diabetes",
            "icd10": "E11",
            "prevalence": "High",
            "related": ["Hypertension", "Cardiovascular Disease", "Obesity"],
            "symptoms": ["Increased thirst", "Frequent urination", "Fatigue"],
            "treatments": ["Metformin", "Insulin", "Lifestyle changes"],
        },
        {
            "name": "Hypertension",
            "icd10": "I10",
            "prevalence": "Very High",
            "related": ["Type 2 Diabetes", "Cardiovascular Disease", "Kidney Disease"],
            "symptoms": ["High blood pressure", "Headaches", "Dizziness"],
            "treatments": ["ACE inhibitors", "Beta blockers", "Lifestyle changes"],
        },
        {
            "name": "Cardiovascular Disease",
            "icd10": "I25",
            "prevalence": "High",
            "related": ["Type 2 Diabetes", "Hypertension", "Obesity"],
            "symptoms": ["Chest pain", "Shortness of breath"],
            "treatments": ["Statins", "Lifestyle changes"],
        },
        {
            "name": "Obesity",
            "icd10": "E66",
            "prevalence": "Very High",
            "related": ["Type 2 Diabetes", "Hypertension"],
            "symptoms": ["Weight gain", "Fatigue"],
            "treatments": ["Lifestyle changes"],
        },
    ]
    seen: set[str] = set()

    def add_named(node_id: str, node_type: str, **props) -> None:
        if node_id in seen:
            return
        seen.add(node_id)
        graph.add_node(node_id, node_type, content=node_id, **props)

    for disease in diseases:
        add_named(disease["name"], "Disease", icd10_code=disease["icd10"], prevalence=disease["prevalence"])
        for related in disease["related"]:
            add_named(related, "Disease")
            graph.add_edge(disease["name"], related, "related_to")
        for symptom in disease["symptoms"]:
            add_named(symptom, "Symptom")
            graph.add_edge(disease["name"], symptom, "has_symptom")
        for treatment in disease["treatments"]:
            add_named(treatment, "Treatment")
            graph.add_edge(disease["name"], treatment, "treated_with")
    return graph


def python_ecosystem() -> ContextGraph:
    graph = ContextGraph(advanced_analytics=False)
    graph.add_node("python", "ProgrammingLanguage", content="Python")
    graph.add_node("cpython", "Interpreter", content="CPython")
    graph.add_node("psf", "Organization", content="Python Software Foundation")
    graph.add_node("docs", "Documentation", content="Python Documentation")
    graph.add_node("packaging", "Documentation", content="Python Packaging User Guide")
    graph.add_node("py313", "SoftwareVersion", content="Python 3.13")
    graph.add_node("asyncio", "StdlibModule", content="asyncio")
    graph.add_node("typing", "StdlibModule", content="typing")
    graph.add_node("pep703", "PEP", content="PEP 703")
    graph.add_node("pypi", "PackageRegistry", content="PyPI")
    graph.add_node("pandas", "Library", content="pandas")
    graph.add_node("numpy", "Library", content="numpy")
    graph.add_node("fastapi", "Library", content="fastapi")
    graph.add_edge("cpython", "python", "implements")
    graph.add_edge("psf", "python", "governs")
    graph.add_edge("docs", "python", "documents")
    graph.add_edge("packaging", "python", "documents")
    graph.add_edge("py313", "python", "version_of")
    graph.add_edge("asyncio", "python", "module_of")
    graph.add_edge("typing", "python", "module_of")
    graph.add_edge("pep703", "python", "proposes_for")
    graph.add_edge("pandas", "pypi", "published_on")
    graph.add_edge("numpy", "pypi", "published_on")
    graph.add_edge("fastapi", "pypi", "published_on")
    graph.add_edge("pandas", "numpy", "depends_on")
    graph.add_edge("pandas", "python", "written_in")
    graph.add_edge("fastapi", "python", "written_in")
    return graph


def programming_stack() -> ContextGraph:
    graph = ContextGraph(advanced_analytics=False)
    graph.add_node("python", "language", content="Python programming language", popularity="high")
    graph.add_node("javascript", "language", content="JavaScript programming language")
    graph.add_node("web_dev", "concept", content="Web Development")
    graph.add_node("ml", "concept", content="Machine Learning")
    graph.add_node("metformin", "drug", content="Metformin", aliases=["Glucophage"])
    graph.add_node(
        "decision_1",
        "decision",
        content="Approve ML framework",
        category="tech",
        outcome="approved",
        confidence="0.9",
    )
    graph.add_node(
        "decision_2",
        "decision",
        content="Reject legacy stack",
        category="tech",
        outcome="rejected",
        confidence="0.4",
    )
    graph.add_node(
        "temporal_node",
        "event",
        content="Conference talk",
        valid_from="2025-01-01T00:00:00",
        valid_until="2025-12-31T23:59:59",
    )
    graph.add_edge("python", "ml", "used_in", weight=0.9)
    graph.add_edge("javascript", "web_dev", "used_in", weight=0.8)
    graph.add_edge("python", "web_dev", "used_in", weight=0.5)
    graph.add_edge("decision_1", "ml", "about")
    return graph


def manufacturing_shopfloor() -> ContextGraph:
    graph = ContextGraph(advanced_analytics=False)
    graph.add_node("site_1", "Site", content="总厂")
    graph.add_node("wc_mill", "WorkCenter", content="数控铣削工段", workCenterCode="WC-MILL")
    graph.add_node("wc_turn", "WorkCenter", content="数控车削工段", workCenterCode="WC-TURN")
    graph.add_node("vmc_01", "CNCMill", content="VMC-01", assetCode="VMC-01")
    graph.add_node("ck_02", "CNCLathe", content="CK-02", assetCode="CK-02")
    graph.add_node("em_10", "CuttingTool", content="EM-10", toolLifeRemaining=80.0)
    graph.add_node("tn_08", "CuttingTool", content="TN-08", toolLifeRemaining=50.0)
    graph.add_node("vise_01", "Fixture", content="Vise-01", fixtureId="FIX-VISE-01")
    graph.add_node("steel_45", "Material", content="45钢")
    graph.add_node("dwg_flange", "PartDrawing", content="法兰盘", drawingNo="DWG-FLANGE-001")
    graph.add_node("wp_1001", "Workpiece", content="WP-1001", workpieceNo="WP-1001")
    graph.add_node("pp_flange", "ProcessPlan", content="法兰盘工艺", planNo="PP-FLANGE-A")
    graph.add_node("op10", "Operation", content="粗铣平面", operationNo="OP10", sequenceNo=10)
    graph.add_node("op20", "Operation", content="车外圆", operationNo="OP20", sequenceNo=20)
    graph.add_node("wo_2026", "WorkOrder", content="法兰盘工单", workOrderNo="WO-2026-001")
    graph.add_node("zhang", "Operator", content="张工")
    graph.add_node(
        "exec_op10",
        "OperationExecution",
        content="WO-2026-001/OP10",
        valid_from="2026-09-01T08:00:00",
        valid_until="2026-09-01T10:30:00",
    )
    graph.add_node("insp_1", "Inspection", content="WP-1001终检", result="pass")
    graph.add_node("meas_od", "Measurement", content="外径", measuredValue=50.02, specMin=49.90, specMax=50.10)

    graph.add_edge("wc_mill", "site_1", "locatedIn")
    graph.add_edge("wc_turn", "site_1", "locatedIn")
    graph.add_edge("vmc_01", "wc_mill", "installedAt")
    graph.add_edge("ck_02", "wc_turn", "installedAt")
    graph.add_edge("wp_1001", "steel_45", "madeFrom")
    graph.add_edge("wp_1001", "dwg_flange", "hasDrawing")
    graph.add_edge("pp_flange", "dwg_flange", "plansDrawing")
    graph.add_edge("op10", "pp_flange", "partOfPlan")
    graph.add_edge("op20", "pp_flange", "partOfPlan")
    graph.add_edge("op10", "em_10", "usesTool")
    graph.add_edge("op10", "vise_01", "usesFixture")
    graph.add_edge("op20", "tn_08", "usesTool")
    graph.add_edge("wo_2026", "pp_flange", "plannedBy")
    graph.add_edge("wo_2026", "wp_1001", "produces")
    graph.add_edge("exec_op10", "wo_2026", "belongsToWorkOrder")
    graph.add_edge("exec_op10", "op10", "executes")
    graph.add_edge("exec_op10", "vmc_01", "executedOn")
    graph.add_edge("exec_op10", "zhang", "performedBy")
    graph.add_edge("exec_op10", "em_10", "usedTool")
    graph.add_edge("insp_1", "wp_1001", "inspects")
    graph.add_edge("insp_1", "meas_od", "hasMeasurement")
    return graph


def corporate_org() -> ContextGraph:
    graph = ContextGraph(advanced_analytics=False)
    graph.add_node("acme", "Company", content="Acme Corp", founded="2010")
    graph.add_node("eng", "Department", content="Engineering")
    graph.add_node("sales", "Department", content="Sales")
    graph.add_node("alice", "Person", content="Alice Chen", role="VP Engineering")
    graph.add_node("bob", "Person", content="Bob Jones", role="Engineer")
    graph.add_node("carol", "Person", content="Carol Diaz", role="Account Lead")
    graph.add_node("project_x", "Project", content="Project X")
    graph.add_edge("eng", "acme", "partOf")
    graph.add_edge("sales", "acme", "partOf")
    graph.add_edge("alice", "eng", "leads")
    graph.add_edge("bob", "alice", "reports_to")
    graph.add_edge("carol", "sales", "works_for")
    graph.add_edge("alice", "project_x", "manages")
    graph.add_edge("bob", "project_x", "works_on")
    return graph


IOT_APIS = (
    ("GetEquipInfoPageList", "设备主数据", "identity"),
    ("GetEquipSpindleWithFeedData", "主轴进给快照", "telemetry"),
    ("GetEquipRunStatusList", "日运行状态", "run_status"),
    ("GetEquipAbnorPageList", "异常报警", "alarm"),
    ("GetEquipProgramPageList", "加工程序", "program"),
    ("GetEquipProductionProgressPageList", "生产进度", "progress"),
    ("GetEquipBootOrRunningTimeList", "开关机时长", "boot_time"),
    ("GetCustomerList", "客户名录", "customer"),
)

PROVINCE_NAMES = {
    "440000": "广东",
    "320000": "江苏",
    "330000": "浙江",
    "500000": "重庆",
    "310000": "上海",
    "340000": "安徽",
}

CITY_NAMES = {
    "441900": "东莞",
    "320500": "苏州",
    "440300": "深圳",
    "442000": "中山",
    "320400": "常州",
    "320200": "无锡",
    "440100": "广州",
    "500100": "重庆",
    "330300": "温州",
    "310100": "上海",
    "330200": "宁波",
    "340100": "合肥",
    "441300": "惠州",
}

KNOWN_CUSTOMER_NODES = {
    "f94ed18b-ccca-4e2b-ba5a-0121d86c2ffd": "customer:meirisheng",
    "4178c64a-9313-4b46-b7f0-d78d4da181f5": "customer:baoteng",
}

SAMPLE_API_EVENTS = (
    ("api:GetEquipSpindleWithFeedData", "telemetry:52893a81"),
    ("api:GetEquipRunStatusList", "runstatus:62500730:2026-05-09"),
    ("api:GetEquipAbnorPageList", "alarm:514affa9"),
    ("api:GetEquipProgramPageList", "program:e82008f3"),
    ("api:GetEquipProductionProgressPageList", "progress:456ee5f1"),
)


def _slug(value: str, fallback: str = "unknown") -> str:
    text = re.sub(r"\s+", "_", (value or "").strip())
    text = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "_", text).strip("._-")
    return text[:80] or fallback


def _ensure_node(graph: ContextGraph, node_id: str, node_type: str, content: str, **props) -> str:
    if node_id not in graph.nodes:
        clean = {key: val for key, val in props.items() if val not in (None, "")}
        graph.add_node(node_id, node_type, content=content, **clean)
    return node_id


def _util_band(rate: float) -> str:
    if rate >= 20:
        return "band:high"
    if rate >= 5:
        return "band:mid"
    return "band:low"


def _customer_node_id(company_id: str, company_name: str) -> str:
    if company_id in KNOWN_CUSTOMER_NODES:
        return KNOWN_CUSTOMER_NODES[company_id]
    if company_id:
        return f"customer:{company_id}"
    return f"customer:{_slug(company_name)}"


def _enrich_device_iot_lineage(graph: ContextGraph, excel_codes: set[str]) -> None:
    """Join complete Mar–Aug timeseries dimensions onto the 200-equip master graph."""
    ts_root = OUT_DIR / "iot_timeseries"
    complete_dir = ts_root / "_complete"
    catalog = json.loads((complete_dir / "catalog.json").read_text(encoding="utf-8"))
    fleet = json.loads((complete_dir / "fleet_trend.json").read_text(encoding="utf-8"))
    complete_codes = {str(row["OutFactoryCode"]) for row in catalog["devices"]}

    window_id = _ensure_node(
        graph,
        "window:2026-03-08",
        "TimeWindow",
        content="2026-03 ~ 2026-08",
        StartTime="2026-03-01",
        EndTime="2026-08-31",
        color="#818CF8",
    )
    ts_dataset = _ensure_node(
        graph,
        "dataset:iot_timeseries",
        "Dataset",
        content="IoT 时序采集",
        path="datasets/json/iot_timeseries",
        color="#A78BFA",
    )
    complete_dataset = _ensure_node(
        graph,
        "dataset:iot_complete",
        "Dataset",
        content="完备设备时序",
        path="datasets/json/iot_timeseries/_complete",
        complete_count=catalog.get("complete_count"),
        incomplete_count=catalog.get("incomplete_count"),
        color="#A78BFA",
    )
    graph.add_edge("openapi:iot", ts_dataset, "feeds")
    graph.add_edge(complete_dataset, ts_dataset, "derivedFrom")
    graph.add_edge(complete_dataset, "list:equip_master_200", "joins")
    graph.add_edge(complete_dataset, window_id, "covers")

    coverage_complete = _ensure_node(graph, "coverage:complete", "Coverage", content="OpenAPI 完备", color="#34D399")
    coverage_excel = _ensure_node(graph, "coverage:excel_only", "Coverage", content="仅 Excel 主数据", color="#94A3B8")
    graph.add_edge(complete_dataset, coverage_complete, "defines")
    graph.add_edge("list:equip_master_200", coverage_excel, "defines")

    _ensure_node(graph, "band:high", "UtilBand", content="高利用率 ≥20%", color="#F87171")
    _ensure_node(graph, "band:mid", "UtilBand", content="中利用率 5–20%", color="#FBBF24")
    _ensure_node(graph, "band:low", "UtilBand", content="低利用率 <5%", color="#94A3B8")
    _ensure_node(graph, "model:M80", "EquipModel", content="M80", EquipModelName="M80", color="#C084FC")

    for api_name, title, grain in IOT_APIS:
        api_id = f"api:{api_name}"
        _ensure_node(graph, api_id, "API", content=title, path=f"/OpenApi/{api_name}", grain=grain, color="#818CF8")
        graph.add_edge("openapi:iot", api_id, "exposes")
        if api_name == "GetCustomerList":
            graph.add_edge(api_id, ts_dataset, "feeds")
        else:
            graph.add_edge(api_id, complete_dataset, "feeds")

    for api_id, event_id in SAMPLE_API_EVENTS:
        if event_id in graph.nodes:
            graph.add_edge(api_id, event_id, "produces")

    for month, stats in (fleet.get("monthly") or {}).items():
        month_id = f"month:{month}"
        _ensure_node(
            graph,
            month_id,
            "Month",
            content=month,
            run_hours=stats.get("run_hours"),
            avg_run_rate_pct=stats.get("avg_run_rate_pct"),
            alarm_count=stats.get("alarm_count"),
            program_cycles=stats.get("program_cycles"),
            color="#818CF8",
        )
        graph.add_edge(complete_dataset, month_id, "aggregates")
        graph.add_edge(month_id, window_id, "during")

    # Shared NC programs and alarm types across complete devices.
    program_devices: dict[str, set[str]] = defaultdict(set)
    program_cycles: dict[str, int] = Counter()
    program_by_type: dict[str, Counter] = defaultdict(Counter)
    alarm_events: dict[str, int] = Counter()
    alarm_devices: dict[str, set[str]] = defaultdict(set)
    alarm_by_type: dict[str, Counter] = defaultdict(Counter)
    boot_by_customer: dict[str, dict] = {}

    for row in catalog["devices"]:
        code = str(row["OutFactoryCode"])
        ident = row.get("identity") or {}
        type_code = ident.get("EquipTypeCode") or row.get("excel_EquipTypeCode") or "T-V856S"
        api_dir = ts_root / code

        program_path = api_dir / "GetEquipProgramPageList.json"
        if program_path.exists():
            for rec in json.loads(program_path.read_text(encoding="utf-8")).get("rows") or []:
                program = (rec.get("ProgramCode") or "").strip() or "未知"
                program_devices[program].add(code)
                output = rec.get("Output")
                program_cycles[program] += int(output or 1)
                program_by_type[program][type_code] += int(output or 1)

        alarm_path = api_dir / "GetEquipAbnorPageList.json"
        if alarm_path.exists():
            for rec in json.loads(alarm_path.read_text(encoding="utf-8")).get("rows") or []:
                alarm_type = (rec.get("AbnoTypeName") or "其它").strip() or "其它"
                alarm_events[alarm_type] += 1
                alarm_devices[alarm_type].add(code)
                alarm_by_type[alarm_type][type_code] += 1

        boot_path = api_dir / "GetEquipBootOrRunningTimeList.json"
        company_id = ident.get("CompanyId") or ""
        if company_id and company_id not in boot_by_customer and boot_path.exists():
            boot_rows = json.loads(boot_path.read_text(encoding="utf-8")).get("rows") or []
            if boot_rows:
                boot_by_customer[company_id] = boot_rows[0]

    shared_programs = {
        name for name, devices in program_devices.items() if len(devices) >= 2 and name not in {"", "未知"}
    }
    for alarm_type, count in alarm_events.items():
        alarm_id = f"alarmtype:{_slug(alarm_type)}"
        _ensure_node(
            graph,
            alarm_id,
            "AlarmType",
            content=alarm_type,
            event_count=count,
            device_count=len(alarm_devices[alarm_type]),
            color="#F87171",
        )
        graph.add_edge(alarm_id, "api:GetEquipAbnorPageList", "sourcedFrom")
        for type_code, type_count in alarm_by_type[alarm_type].items():
            graph.add_edge(alarm_id, f"type:{type_code}", "seenOnType", weight=float(type_count), event_count=type_count)

    for program in shared_programs:
        program_id = f"program:{_slug(program)}"
        _ensure_node(
            graph,
            program_id,
            "Program",
            content=program,
            ProgramCode=program,
            device_count=len(program_devices[program]),
            cycle_count=program_cycles[program],
            color="#38BDF8",
        )
        graph.add_edge(program_id, "api:GetEquipProgramPageList", "sourcedFrom")
        for type_code, type_count in program_by_type[program].items():
            graph.add_edge(program_id, f"type:{type_code}", "runOnType", weight=float(type_count), cycle_count=type_count)

    area_cities: dict[str, set[str]] = defaultdict(set)
    type_areas: dict[str, set[str]] = defaultdict(set)
    customer_types: dict[str, set[str]] = defaultdict(set)

    for row in catalog["devices"]:
        code = str(row["OutFactoryCode"])
        ident = row.get("identity") or {}
        activity = row.get("activity") or {}
        monthly = row.get("monthly") or {}
        info_path = complete_dir / code / "GetEquipInfoPageList.json"
        info = {}
        if info_path.exists():
            info_rows = json.loads(info_path.read_text(encoding="utf-8")).get("rows") or []
            if info_rows:
                info = info_rows[0]

        company_name = (ident.get("CompanyName") or info.get("CompanyName") or "未知客户").strip() or "未知客户"
        company_id = ident.get("CompanyId") or info.get("CompanyId") or ""
        area = (ident.get("AreaName") or info.get("AreaName") or "").strip()
        type_code = ident.get("EquipTypeCode") or row.get("excel_EquipTypeCode") or "T-V856S"
        gw_code = ident.get("GwCode") or info.get("GwCode") or ""
        city_code = str(info.get("City") or "").strip()
        province_code = str(info.get("Province") or "").strip()
        rate = float(activity.get("avg_run_rate_pct") or 0)
        band = _util_band(rate)
        equip_id = f"equip:{code}"
        cust_id = _customer_node_id(company_id, company_name)

        graph.add_node_attribute(
            equip_id,
            {
                "EquipCode": ident.get("EquipCode") or info.get("EquipCode") or "",
                "EquipName": ident.get("EquipName") or info.get("EquipName") or "",
                "CompanyName": company_name,
                "CompanyId": company_id,
                "AreaName": area,
                "GwCode": gw_code,
                "EquipModelName": info.get("EquipModelName") or "M80",
                "complete": True,
                "run_hours": activity.get("run_hours"),
                "avg_run_rate_pct": rate,
                "alarm_count": activity.get("alarm_count"),
                "program_cycles": activity.get("program_cycles"),
                "progress_output": activity.get("progress_output"),
            },
        )

        _ensure_node(
            graph,
            cust_id,
            "Customer",
            content=company_name,
            CompanyId=company_id,
            AreaName=area,
            color="#34D399",
        )
        graph.add_edge("customer:century", cust_id, "covers")
        graph.add_edge(complete_dataset, cust_id, "covers")
        graph.add_edge(equip_id, cust_id, "ownedBy")
        customer_types[cust_id].add(type_code)

        if area:
            area_id = f"area:{area}"
            _ensure_node(graph, area_id, "Area", content=area, color="#F59E0B")
            graph.add_edge(equip_id, area_id, "locatedIn")
            graph.add_edge(cust_id, area_id, "locatedIn")
            graph.add_edge(complete_dataset, area_id, "covers")
            type_areas[type_code].add(area)

        city_id = ""
        if city_code:
            city_id = f"city:{city_code}"
            _ensure_node(
                graph,
                city_id,
                "City",
                content=CITY_NAMES.get(city_code, city_code),
                CityCode=city_code,
                color="#FB923C",
            )
            graph.add_edge(equip_id, city_id, "locatedIn")
            graph.add_edge(cust_id, city_id, "locatedIn")
            if area:
                area_cities[area].add(city_id)

        if province_code:
            province_id = f"province:{province_code}"
            _ensure_node(
                graph,
                province_id,
                "Province",
                content=PROVINCE_NAMES.get(province_code, province_code),
                ProvinceCode=province_code,
                color="#F97316",
            )
            if city_id:
                graph.add_edge(city_id, province_id, "inProvince")
            elif area:
                graph.add_edge(f"area:{area}", province_id, "inProvince")

        if gw_code:
            gw_id = f"gw:{gw_code}"
            _ensure_node(
                graph,
                gw_id,
                "Gateway",
                content=gw_code,
                GwCode=gw_code,
                GateId=info.get("GateId") or "",
                Ip=info.get("Ip") or "",
                SIMNo=info.get("SIMNo") or "",
                color="#64748B",
            )
            graph.add_edge(equip_id, gw_id, "collectedBy")
            graph.add_edge(gw_id, "api:GetEquipInfoPageList", "sourcedFrom")
            if area:
                graph.add_edge(gw_id, f"area:{area}", "locatedIn")
            if city_id:
                graph.add_edge(gw_id, city_id, "locatedIn")

        graph.add_edge(equip_id, "model:M80", "modeledAs")
        graph.add_edge(equip_id, band, "utilizes")
        graph.add_edge(equip_id, coverage_complete, "hasCoverage")
        graph.add_edge(complete_dataset, equip_id, "contains")
        graph.add_edge("openapi:iot", equip_id, "serves")

        for month, stats in monthly.items():
            month_id = f"month:{month}"
            if month_id not in graph.nodes:
                continue
            graph.add_edge(
                equip_id,
                month_id,
                "observedIn",
                weight=float(stats.get("avg_run_rate_pct") or 0),
                alarm_count=stats.get("alarm_count"),
                program_cycles=stats.get("program_cycles"),
                progress_output=stats.get("progress_output"),
                run_seconds=stats.get("run_seconds"),
                avg_run_rate_pct=stats.get("avg_run_rate_pct"),
                valid_from=f"{month}-01T00:00:00",
            )

        api_dir = ts_root / code
        local_alarms: Counter[str] = Counter()
        alarm_path = api_dir / "GetEquipAbnorPageList.json"
        if alarm_path.exists():
            for rec in json.loads(alarm_path.read_text(encoding="utf-8")).get("rows") or []:
                local_alarms[(rec.get("AbnoTypeName") or "其它").strip() or "其它"] += 1
        for alarm_type, count in local_alarms.items():
            graph.add_edge(
                equip_id,
                f"alarmtype:{_slug(alarm_type)}",
                "raises",
                weight=float(count),
                event_count=count,
            )

        local_programs: Counter[str] = Counter()
        program_path = api_dir / "GetEquipProgramPageList.json"
        if program_path.exists():
            for rec in json.loads(program_path.read_text(encoding="utf-8")).get("rows") or []:
                program = (rec.get("ProgramCode") or "").strip()
                if program in shared_programs:
                    local_programs[program] += int(rec.get("Output") or 1)
        for program, count in local_programs.items():
            graph.add_edge(
                equip_id,
                f"program:{_slug(program)}",
                "runs",
                weight=float(count),
                cycle_count=count,
            )

    for area, cities in area_cities.items():
        for city_id in cities:
            graph.add_edge(f"area:{area}", city_id, "contains")
    for type_code, areas in type_areas.items():
        for area in areas:
            graph.add_edge(f"type:{type_code}", f"area:{area}", "deployedIn")
    for cust_id, types in customer_types.items():
        for type_code in types:
            graph.add_edge(cust_id, f"type:{type_code}", "usesType")

    for company_id, boot in boot_by_customer.items():
        cust_id = _customer_node_id(company_id, boot.get("CustomerName") or company_id)
        boot_id = f"boot:{company_id}"
        _ensure_node(
            graph,
            boot_id,
            "BootTimeRollup",
            content=f"{boot.get('CustomerName') or company_id} 开关机",
            TotalRunningTime=boot.get("TotalRunningTime"),
            TotalBootTime=boot.get("TotalBootTime"),
            EquipCount=boot.get("EquipCount"),
            StatsEquipCount=boot.get("StatsEquipCount"),
            color="#2DD4BF",
        )
        graph.add_edge(cust_id, boot_id, "summarizedBy")
        graph.add_edge(boot_id, "api:GetEquipBootOrRunningTimeList", "sourcedFrom")
        graph.add_edge(boot_id, window_id, "during")

    for code in excel_codes:
        if code not in complete_codes:
            graph.add_edge(f"equip:{code}", coverage_excel, "hasCoverage")


def device_iot_model() -> ContextGraph:
    """Device master + MES/PdM telemetry model from the 200-equip Excel and OpenAPI docs."""
    master_path = OUT_DIR / "source" / "equip_master_200.json"
    master = json.loads(master_path.read_text(encoding="utf-8"))
    type_names = master.get("equip_type_names", {})
    graph = ContextGraph(advanced_analytics=False)

    graph.add_node(
        "list:equip_master_200",
        "Dataset",
        content="200台设备主数据",
        source_file=master.get("source", "200个设备信息(1).xls"),
    )
    graph.add_node(
        "openapi:iot",
        "OpenAPI",
        content="IoT OpenAPI",
        base_url="https://iotdev.szccm.com:9991",
    )

    graph.add_node("type:T-V856S", "EquipType", content="T-V856S", EquipTypeCode="T-V856S", EquipTypeName=type_names.get("T-V856S", "立式加工中心"))
    graph.add_node("type:T-600", "EquipType", content="T-600", EquipTypeCode="T-600", EquipTypeName=type_names.get("T-600", "钻攻机"))

    graph.add_node(
        "customer:century",
        "Customer",
        content="创世纪",
        CustomerId="21e224c9-2bb7-4c40-9815-8250916a4831",
    )
    graph.add_node(
        "customer:meirisheng",
        "Customer",
        content="东莞市美日升五金科技有限公司",
        CustomerId="f94ed18b-ccca-4e2b-ba5a-0121d86c2ffd",
        AreaName="华南区",
    )
    graph.add_node(
        "customer:baoteng",
        "Customer",
        content="东莞宝腾润滑技术有限公司",
        CustomerId="4178c64a-9313-4b46-b7f0-d78d4da181f5",
    )

    excel_codes = set()
    for record in master["records"]:
        code = str(record["OutFactoryCode"])
        type_code = str(record["EquipTypeCode"])
        excel_codes.add(code)
        node_id = f"equip:{code}"
        graph.add_node(
            node_id,
            "Equip",
            content=code,
            OutFactoryCode=code,
            EquipTypeCode=type_code,
            EquipTypeName=type_names.get(type_code, type_code),
            in_excel=True,
            source="excel_master",
        )
        graph.add_edge(node_id, f"type:{type_code}", "classifiedAs")
        graph.add_edge("list:equip_master_200", node_id, "contains")

    def ensure_equip(*, out_factory: str, type_code: str, type_name: str, equip_code: str, equip_name: str = "", source: str = "mes_doc_sample") -> str:
        node_id = f"equip:{out_factory}"
        if out_factory not in excel_codes and node_id not in graph.nodes:
            graph.add_node(
                node_id,
                "Equip",
                content=out_factory,
                OutFactoryCode=out_factory,
                EquipTypeCode=type_code,
                EquipTypeName=type_name,
                EquipCode=equip_code,
                EquipName=equip_name,
                in_excel=False,
                source=source,
            )
            graph.add_edge(node_id, f"type:{type_code}", "classifiedAs")
        elif node_id in graph.nodes:
            attrs = {"EquipCode": equip_code}
            if equip_name:
                attrs["EquipName"] = equip_name
            graph.add_node_attribute(node_id, attrs)
        return node_id

    # Excel device that also appears in spindle/feed telemetry samples.
    equip_512 = ensure_equip(
        out_factory="172603512",
        type_code="T-V856S",
        type_name="立式加工中心",
        equip_code="172603512_sk",
    )
    graph.add_node(
        "telemetry:52893a81",
        "TelemetrySnapshot",
        content="172603512 主轴进给快照",
        EquipCode="172603512_sk",
        XAC="470.084",
        XLoad="3",
        YAC="-393.615",
        YLoad="12",
        ZAC="-518.239",
        ZLoad="41",
        MainArbor="S1",
        Speed="6495",
        SpeedRate="100",
        Load="0",
        Feed="1949.991",
        FeedRate="130",
        KnifePosition="20",
        ProgramCode="O275-72-DJK",
        LineNo="8601",
        api="GetEquipSpindleWithFeedData",
    )
    graph.add_edge(equip_512, "telemetry:52893a81", "reports")
    graph.add_edge("openapi:iot", "telemetry:52893a81", "serves")

    # MES master-data sample (not in the 200-row Excel).
    equip_337 = ensure_equip(
        out_factory="172603337",
        type_code="T-V856S",
        type_name="立式加工中心",
        equip_code="172603337_sk",
    )
    graph.add_node(
        "gw:DAQ043068219",
        "Gateway",
        content="DAQ043068219",
        GwCode="DAQ043068219",
        GateId="3bb410fe-c04c-45f3-9582-1d4fa4f50444",
        Ip="192.168.1.83",
        SIMNo="898604A1192670001994",
    )
    graph.add_edge(equip_337, "gw:DAQ043068219", "collectedBy")
    graph.add_edge(equip_337, "customer:meirisheng", "ownedBy")
    graph.add_edge("openapi:iot", equip_337, "serves")

    equip_730 = ensure_equip(
        out_factory="62500730",
        type_code="T-600",
        type_name="钻攻机",
        equip_code="62500730",
        equip_name="02",
    )
    graph.add_node(
        "runstatus:62500730:2026-05-09",
        "RunStatusDaily",
        content="62500730 日运行状态",
        currentDate="2026-05-09",
        TotalTime="7小时30分钟11秒",
        RunTime="1小时37分钟40秒",
        RunTimeRate="21.69%",
        StandbyTime="5小时52分钟31秒",
        StandbyTimeRate="78.31%",
        StopTime="0秒",
        BreakDownTime="0秒",
        api="GetEquipRunStatusList",
        valid_from="2026-05-09T00:00:00",
        valid_until="2026-05-09T23:59:59",
    )
    graph.add_edge(equip_730, "runstatus:62500730:2026-05-09", "aggregates")
    graph.add_edge(equip_730, "customer:baoteng", "ownedBy")

    equip_773 = ensure_equip(
        out_factory="172604773",
        type_code="T-V856S",
        type_name="立式加工中心",
        equip_code="172604773_sk",
    )
    graph.add_node(
        "alarm:514affa9",
        "AlarmEvent",
        content="油位过低 O0005",
        AbnoCode="O0005",
        AbnoTypeName="油位过低",
        AbnoContent="2005.ATC维修模式",
        IsShutdown=1,
        ProcessStatus="已解决",
        DurationDetail="29分钟3秒",
        api="GetEquipAbnorPageList",
        valid_from="2026-05-09T15:21:02",
    )
    graph.add_edge(equip_773, "alarm:514affa9", "raises")
    graph.add_edge(equip_773, "customer:century", "ownedBy")

    graph.add_node(
        "equip:dgbt13",
        "Equip",
        content="dgbt13",
        OutFactoryCode="",
        EquipCode="dgbt13",
        EquipName="13",
        EquipTypeCode="T-600",
        EquipTypeName="钻攻机",
        in_excel=False,
        source="mes_doc_sample",
    )
    graph.add_edge("equip:dgbt13", "type:T-600", "classifiedAs")
    graph.add_edge("equip:dgbt13", "customer:baoteng", "ownedBy")
    graph.add_node(
        "program:e82008f3",
        "ProgramCycle",
        content="BFA-7",
        ProgramCode="BFA-7",
        Output=1,
        OutputSumSecond=1079,
        AvgOutPutTime="17分钟59秒",
        api="GetEquipProgramPageList",
        valid_from="2026-05-01T03:31:12",
        valid_until="2026-05-01T03:31:27",
    )
    graph.add_edge("equip:dgbt13", "program:e82008f3", "produces")
    graph.add_node(
        "progress:456ee5f1",
        "ProductionProgressDaily",
        content="BFA-05. 日进度",
        ProgramCode="BFA-05.",
        Output=32,
        PlanOutput=294,
        OutputSumSecond=22382,
        ProcessingTimeSum="6小时21分钟41秒",
        api="GetEquipProductionProgressPageList",
        valid_from="2026-05-09T00:00:00",
        valid_until="2026-05-09T23:59:59",
    )
    graph.add_node(
        "equip:dgbt11",
        "Equip",
        content="dgbt11",
        EquipCode="dgbt11",
        EquipName="11",
        EquipTypeCode="T-600",
        EquipTypeName="钻攻机",
        in_excel=False,
        source="mes_doc_sample",
    )
    graph.add_edge("equip:dgbt11", "type:T-600", "classifiedAs")
    graph.add_edge("equip:dgbt11", "customer:baoteng", "ownedBy")
    graph.add_edge("equip:dgbt11", "progress:456ee5f1", "tracks")

    graph.add_edge("openapi:iot", "customer:century", "serves")
    graph.add_edge("openapi:iot", "customer:baoteng", "serves")
    graph.add_edge("openapi:iot", "customer:meirisheng", "serves")
    _enrich_device_iot_lineage(graph, excel_codes)
    return graph


def complete_device_ledger() -> ContextGraph:
    """Explorer ledger of OpenAPI-complete devices (Mar–Aug 2026)."""
    complete_dir = OUT_DIR / "iot_timeseries" / "_complete"
    index = json.loads((complete_dir / "index.json").read_text(encoding="utf-8"))
    fleet = json.loads((complete_dir / "fleet_trend.json").read_text(encoding="utf-8"))
    graph = ContextGraph(advanced_analytics=False)

    graph.add_node(
        "ledger:complete",
        "Dataset",
        content="完整设备台账",
        range="2026-03-01/2026-08-31",
        device_count=len(index),
        color="#A78BFA",
    )
    graph.add_node("type:T-V856S", "EquipType", content="T-V856S 立加", EquipTypeCode="T-V856S", color="#63E6FF")
    graph.add_node("type:T-600", "EquipType", content="T-600 钻攻", EquipTypeCode="T-600", color="#34D399")
    graph.add_node("band:high", "UtilBand", content="高利用率 ≥20%", color="#F87171")
    graph.add_node("band:mid", "UtilBand", content="中利用率 5–20%", color="#FBBF24")
    graph.add_node("band:low", "UtilBand", content="低利用率 <5%", color="#94A3B8")

    for month, stats in (fleet.get("monthly") or {}).items():
        node_id = f"month:{month}"
        graph.add_node(
            node_id,
            "Month",
            content=month,
            run_hours=stats.get("run_hours"),
            avg_run_rate_pct=stats.get("avg_run_rate_pct"),
            alarm_count=stats.get("alarm_count"),
            program_cycles=stats.get("program_cycles"),
            color="#818CF8",
        )
        graph.add_edge("ledger:complete", node_id, "aggregates")

    customers: dict[str, str] = {}
    areas: set[str] = set()
    for row in index:
        code = str(row["OutFactoryCode"])
        company = (row.get("CompanyName") or "未知客户").strip() or "未知客户"
        area = (row.get("AreaName") or "").strip()
        type_code = row.get("EquipTypeCode") or "T-V856S"
        rate = float(row.get("avg_run_rate_pct") or 0)
        if rate >= 20:
            band = "band:high"
        elif rate >= 5:
            band = "band:mid"
        else:
            band = "band:low"

        cust_id = customers.get(company)
        if cust_id is None:
            meta_path = complete_dir / code / "meta.json"
            company_id = ""
            if meta_path.exists():
                ident = json.loads(meta_path.read_text(encoding="utf-8")).get("identity") or {}
                company_id = ident.get("CompanyId") or ""
            cust_id = f"customer:{company_id or company}"
            customers[company] = cust_id
            graph.add_node(cust_id, "Customer", content=company, CompanyId=company_id, color="#34D399")
            graph.add_edge("ledger:complete", cust_id, "covers")

        if area and area not in areas:
            areas.add(area)
            graph.add_node(f"area:{area}", "Area", content=area, color="#F59E0B")
            graph.add_edge("ledger:complete", f"area:{area}", "covers")

        equip_id = f"equip:{code}"
        graph.add_node(
            equip_id,
            "Equip",
            content=code,
            OutFactoryCode=code,
            EquipTypeCode=type_code,
            CompanyName=company,
            AreaName=area,
            run_hours=row.get("run_hours"),
            avg_run_rate_pct=rate,
            alarm_count=row.get("alarm_count"),
            program_cycles=row.get("program_cycles"),
            progress_output=row.get("progress_output"),
            complete=True,
        )
        graph.add_edge("ledger:complete", equip_id, "contains")
        graph.add_edge(equip_id, f"type:{type_code}", "classifiedAs")
        graph.add_edge(equip_id, cust_id, "ownedBy")
        graph.add_edge(equip_id, band, "utilizes")
        if area:
            graph.add_edge(equip_id, f"area:{area}", "locatedIn")
    return graph


def _num(value, digits: int | None = 1):
    if value is None:
        return 0 if digits is None else 0.0
    try:
        if pd.isna(value):
            return 0 if digits is None else 0.0
    except TypeError:
        pass
    number = float(value)
    if digits is None:
        return int(round(number))
    return round(number, digits)


def _text(value, default: str = "") -> str:
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except TypeError:
        pass
    text = str(value).strip()
    return text if text and text.lower() != "nan" else default


def _metric_props(row) -> dict:
    bases = {key: getattr(row, key) for key in DEVICE_DAY_NAMED if hasattr(row, key)}
    stamped = stamp_metrics(bases)
    share = getattr(row, "run_hours_share_of_month", None)
    try:
        if share is not None and not pd.isna(share):
            stamped["run_hours_share_of_month"] = round(float(share), 4)
    except TypeError:
        pass
    return stamped


def cleaned_iot_semantics() -> ContextGraph:
    """Explorer graph from cleaned Apr–Aug parquet (metrics.md slices)."""
    dim = pd.read_parquet(PROCESSED_IOT / "device_dim.parquet")
    day = pd.read_parquet(PROCESSED_IOT / "device_day.parquet")
    alarms = pd.read_parquet(PROCESSED_IOT / "alarm_event.parquet")
    report = json.loads((PROCESSED_IOT / "dq_report.json").read_text(encoding="utf-8"))
    graph = ContextGraph(advanced_analytics=False)

    graph.add_node(
        "dataset:cleaned",
        "Dataset",
        content="清洗后完备设备语义图",
        window="2026-04-01/2026-08-31",
        complete_devices=int(report.get("complete_devices") or len(dim)),
        color="#A78BFA",
    )
    graph.add_node("type:T-V856S", "EquipType", content="T-V856S 立加", EquipTypeCode="T-V856S", color="#63E6FF")
    graph.add_node("type:T-600", "EquipType", content="T-600 钻攻", EquipTypeCode="T-600", color="#34D399")
    graph.add_edge("dataset:cleaned", "type:T-V856S", "covers")
    graph.add_edge("dataset:cleaned", "type:T-600", "covers")
    graph.add_node("band:high", "UtilBand", content="高运行 ≥360h", color="#F87171")
    graph.add_node("band:mid", "UtilBand", content="中运行 80–360h", color="#FBBF24")
    graph.add_node("band:low", "UtilBand", content="低运行 <80h", color="#94A3B8")
    graph.add_node("domain:cnc_run", "MeasureDomain", content="CNC运行 / 时间结构", color="#818CF8")
    graph.add_node("domain:alarm", "MeasureDomain", content="报警 / 事件", color="#FB7185")
    graph.add_node("domain:program", "MeasureDomain", content="程序 / 产量", color="#2DD4BF")
    for domain in ("domain:cnc_run", "domain:alarm", "domain:program"):
        graph.add_edge("dataset:cleaned", domain, "defines")

    month_agg = day.groupby("month", as_index=False).agg(**DEVICE_DAY_NAMED).sort_values("month")
    for row in month_agg.itertuples(index=False):
        node_id = f"month:{row.month}"
        graph.add_node(node_id, "Month", content=str(row.month), color="#818CF8", **_metric_props(row))
        graph.add_edge("dataset:cleaned", node_id, "aggregates")
        graph.add_edge(node_id, "domain:cnc_run", "reports")

    type_month = day.groupby(["equip_type_code", "month"], as_index=False).agg(**DEVICE_DAY_NAMED)
    month_hours = type_month.groupby("month")["run_hours"].transform("sum")
    type_month = type_month.assign(run_hours_share_of_month=type_month["run_hours"] / month_hours.replace(0, pd.NA))
    for row in type_month.itertuples(index=False):
        slice_id = f"slice:{row.equip_type_code}:{row.month}"
        graph.add_node(
            slice_id,
            "TypeMonth",
            content=f"{row.equip_type_code} {row.month}",
            EquipTypeCode=row.equip_type_code,
            month=row.month,
            color="#C084FC",
            **_metric_props(row),
        )
        graph.add_edge("dataset:cleaned", slice_id, "slices")
        graph.add_edge(slice_id, f"type:{row.equip_type_code}", "ofType")
        graph.add_edge(slice_id, f"month:{row.month}", "inMonth", weight=max(float(row.run_hours), 0.1))

    type_stats = day.groupby("equip_type_code", as_index=False).agg(**DEVICE_DAY_NAMED)
    for row in type_stats.itertuples(index=False):
        graph.add_node_attribute(f"type:{row.equip_type_code}", _metric_props(row))

    device_stats = day.groupby("out_factory_code", as_index=False).agg(
        **DEVICE_DAY_NAMED,
        mean_run_rate_pct=("run_time_rate_pct", "mean"),
    )
    stats_by_code = {str(row.out_factory_code): row for row in device_stats.itertuples(index=False)}
    cust_stats = day.groupby("company_id", as_index=False).agg(**DEVICE_DAY_NAMED)
    cust_by_id = {_text(row.company_id): row for row in cust_stats.itertuples(index=False)}
    area_day = day.merge(dim[["out_factory_code", "area_name"]].drop_duplicates("out_factory_code"), on="out_factory_code", how="left")
    area_day["area_name"] = area_day["area_name"].fillna("空").replace("", "空")
    area_stats = area_day.groupby("area_name", as_index=False).agg(**DEVICE_DAY_NAMED)
    area_by_name = {_text(row.area_name, "空"): row for row in area_stats.itertuples(index=False)}

    for area in sorted({str(v).strip() for v in dim["area_name"].fillna("空")}):
        label = area if area and area != "None" else "空"
        stats = area_by_name.get(label)
        graph.add_node(f"area:{label}", "Area", content=label, color="#F59E0B", **(_metric_props(stats) if stats is not None else {}))
        graph.add_edge("dataset:cleaned", f"area:{label}", "covers")

    customers: dict[str, str] = {}
    for row in dim.itertuples(index=False):
        code = str(row.out_factory_code)
        company = _text(row.company_name, "未知客户")
        company_id = _text(row.company_id)
        area = _text(row.area_name, "空")
        type_code = _text(row.equip_type_code, "T-V856S")
        stats = stats_by_code.get(code)
        run_hours = _num(getattr(stats, "run_hours", 0))
        if run_hours >= 360:
            band = "band:high"
        elif run_hours >= 80:
            band = "band:mid"
        else:
            band = "band:low"

        cust_key = company_id or company
        cust_id = customers.get(cust_key)
        if cust_id is None:
            cust_id = f"customer:{cust_key}"
            customers[cust_key] = cust_id
            c_stats = cust_by_id.get(company_id)
            graph.add_node(
                cust_id,
                "Customer",
                content=company,
                CompanyId=company_id,
                color="#34D399",
                **(_metric_props(c_stats) if c_stats is not None else {}),
            )
            graph.add_edge("dataset:cleaned", cust_id, "covers")

        equip_id = f"equip:{code}"
        graph.add_node(
            equip_id,
            "Equip",
            content=code,
            OutFactoryCode=code,
            EquipTypeCode=type_code,
            EquipTypeName=row.equip_type_name,
            CompanyName=company,
            AreaName=area,
            mean_run_rate_pct=_num(getattr(stats, "mean_run_rate_pct", 0), 2),
            complete=True,
            **(_metric_props(stats) if stats is not None else {"run_hours": run_hours}),
        )
        graph.add_edge("dataset:cleaned", equip_id, "contains")
        graph.add_edge(equip_id, f"type:{type_code}", "classifiedAs")
        graph.add_edge(equip_id, cust_id, "ownedBy")
        graph.add_edge(equip_id, band, "utilizes")
        graph.add_edge(equip_id, f"area:{area}", "locatedIn")

    alarm_work = alarms.assign(_one=1)
    alarm_by_code = alarm_work.groupby("abno_code", as_index=False).agg(
        alarm_count=("_one", "sum"),
        alarm_shutdown_count=("is_shutdown", "sum"),
        alarm_duration_sec=("duration_sec", "sum"),
    )
    alarm_code_stats = {str(row.abno_code or "未知"): row for row in alarm_by_code.itertuples(index=False)}
    alarm_top = (
        alarm_work.groupby(["abno_code", "equip_type_code"], as_index=False)
        .agg(
            alarm_count=("_one", "sum"),
            alarm_shutdown_count=("is_shutdown", "sum"),
            alarm_duration_sec=("duration_sec", "sum"),
        )
        .sort_values("alarm_count", ascending=False)
        .head(12)
    )
    seen_codes: set[str] = set()
    for row in alarm_top.itertuples(index=False):
        code = str(row.abno_code or "未知")
        alarm_id = f"alarm:{code}"
        if code not in seen_codes:
            code_stats = alarm_code_stats.get(code, row)
            graph.add_node(
                alarm_id,
                "AlarmCode",
                content=code,
                color="#FB7185",
                **stamp_metrics(
                    {
                        "alarm_count": getattr(code_stats, "alarm_count", 0),
                        "alarm_shutdown_count": getattr(code_stats, "alarm_shutdown_count", 0),
                        "alarm_duration_sec": getattr(code_stats, "alarm_duration_sec", 0),
                    }
                ),
            )
            graph.add_edge("dataset:cleaned", alarm_id, "indexes")
            graph.add_edge(alarm_id, "domain:alarm", "belongsTo")
            seen_codes.add(code)
        graph.add_edge(
            alarm_id,
            f"type:{row.equip_type_code}",
            "raisedOn",
            weight=float(row.alarm_count),
            alarm_count=_num(row.alarm_count, None),
        )

    for rule in report.get("rules") or []:
        rule_id = rule.get("rule_id")
        table = rule.get("table")
        node_id = f"dq:{rule_id}:{table}"
        graph.add_node(
            node_id,
            "DataQuality",
            content=f"{rule_id} / {table}",
            count=_num(rule.get("count"), None),
            note=rule.get("note") or "",
            color="#F97316",
        )
        graph.add_edge("dataset:cleaned", node_id, "flagged")

    for row in report.get("excluded_incomplete") or []:
        code = str(row.get("out_factory_code"))
        node_id = f"excluded:{code}"
        graph.add_node(
            node_id,
            "IncompleteEquip",
            content=code,
            missing=",".join(row.get("missing") or []),
            color="#64748B",
        )
        graph.add_edge("dataset:cleaned", node_id, "excludes")
    _attach_workspace_semantics(graph, day, alarms)
    return graph


def _attach_workspace_semantics(graph: ContextGraph, day: pd.DataFrame, alarms: pd.DataFrame) -> None:
    """Richer links plus Decision / Ontology / Provenance / Enrich demo nodes."""
    onto = "http://semantica.local/iot/ontology"
    skos = "http://semantica.local/iot/skos"
    graph.add_node(
        onto,
        "owl:Ontology",
        content="IoT 设备清洗本体",
        **{"rdfs:label": "IoT 设备清洗本体", "uri": onto, "owl:versionInfo": "1.0", "color": "#E879F9"},
    )
    graph.add_edge("dataset:cleaned", onto, "conformsTo")
    classes = [
        (f"{onto}#Equip", "设备", "T-V856S / T-600 物理机"),
        (f"{onto}#Customer", "客户", "现场使用方，后续切分键"),
        (f"{onto}#AlarmCode", "报警号", "AbnoCode，不是故障秒"),
        (f"{onto}#TypeMonth", "机型×月", "推荐切片"),
        (f"{onto}#RunStatus", "运行状态四桶", "运行/待机/关机/故障"),
    ]
    for uri, label, comment in classes:
        graph.add_node(
            uri,
            "owl:Class",
            content=label,
            **{"rdfs:label": label, "rdfs:comment": comment, "scheme_uri": onto, "color": "#E879F9"},
        )
        graph.add_edge(uri, onto, "rdfs:isDefinedBy")
    graph.add_edge(f"{onto}#TypeMonth", f"{onto}#Equip", "rdfs:subClassOf")
    graph.add_edge("type:T-V856S", f"{onto}#Equip", "rdf:type")
    graph.add_edge("type:T-600", f"{onto}#Equip", "rdf:type")

    graph.add_node(
        skos,
        "skos:ConceptScheme",
        content="运行状态词表",
        **{"skos:prefLabel": "运行状态词表", "uri": skos, "scheme_uri": skos, "color": "#38BDF8"},
    )
    graph.add_edge(onto, skos, "owl:imports")
    concepts = [
        ("run", "运行", "RunTime，不是件数"),
        ("standby", "待机", "StandbyTime"),
        ("stop", "关机", "StopTime，不是停机"),
        ("breakdown", "故障", "BreakDownTime，不是停机报警条数"),
        ("idle", "停机", "仅 IsShutdown / IdleCount"),
        ("util30d", "近30天稼动率", "客户列表 UtilRate，禁止当每日运行占比"),
    ]
    for slug, label, definition in concepts:
        cid = f"{skos}#{slug}"
        graph.add_node(
            cid,
            "skos:Concept",
            content=label,
            **{
                "skos:prefLabel": label,
                "skos:definition": definition,
                "scheme_uri": skos,
                "color": "#38BDF8",
            },
        )
        graph.add_edge(cid, skos, "skos:inScheme")
    graph.add_edge(f"{skos}#run", f"{skos}#standby", "skos:related")
    graph.add_edge(f"{skos}#stop", f"{skos}#idle", "skos:related")
    graph.add_edge(f"{skos}#breakdown", f"{skos}#idle", "skos:related")
    graph.add_edge(f"{skos}#run", "domain:cnc_run", "denotes")
    graph.add_edge(f"{skos}#idle", "domain:alarm", "denotes")
    graph.add_edge(f"{skos}#util30d", "domain:cnc_run", "notToBeConfusedWith")

    for recipe in PRESETS:
        formula = f"{recipe['a']} {recipe['op']} {recipe['b']}" if recipe.get("b") else f"share({recipe['a']})"
        metric_id = f"metric:{recipe['id']}"
        graph.add_node(
            metric_id,
            "DerivedMetric",
            content=recipe["name_zh"],
            formula=formula,
            op=recipe["op"],
            domain=recipe.get("domain") or "",
            not_label=recipe.get("not") or "",
            color="#A78BFA",
        )
        domain_id = f"domain:{recipe.get('domain') or 'cnc_run'}"
        graph.add_edge(metric_id, domain_id, "measures")

    programs = pd.read_parquet(PROCESSED_IOT / "program_cycle.parquet")
    top_programs = (
        programs.groupby(["program_code", "equip_type_code"], as_index=False)
        .agg(cycles=("output", "sum"), devices=("out_factory_code", "nunique"))
        .sort_values("cycles", ascending=False)
        .head(8)
    )
    seen_prog: set[str] = set()
    for row in top_programs.itertuples(index=False):
        code = _text(row.program_code, "未知程序")
        pid = f"program:{code}"
        if code not in seen_prog:
            graph.add_node(pid, "ProgramCode", content=code, color="#2DD4BF")
            graph.add_edge("dataset:cleaned", pid, "indexes")
            graph.add_edge(pid, "domain:program", "belongsTo")
            seen_prog.add(code)
        graph.add_edge(
            pid,
            f"type:{row.equip_type_code}",
            "runsOn",
            weight=float(row.cycles or 0),
            cycles=_num(row.cycles, None),
        )

    o0005 = alarms[(alarms["abno_code"] == "O0005") & (alarms["equip_type_code"] == "T-V856S")]
    if not o0005.empty:
        top_equips = o0005.groupby("out_factory_code").size().sort_values(ascending=False).head(6)
        for code, count in top_equips.items():
            graph.add_edge("alarm:O0005", f"equip:{code}", "raisedOnEquip", weight=float(count), alarm_count=int(count))

    top_run = (
        day.groupby("out_factory_code", as_index=False)["run_hours"].sum().sort_values("run_hours", ascending=False).head(5)
    )
    for row in top_run.itertuples(index=False):
        graph.add_edge(f"equip:{row.out_factory_code}", "month:2026-08", "peakedIn", weight=float(row.run_hours))

    graph.add_node(
        "event:aug-run-surge",
        "event",
        content="8 月运行抬升到 3.8 万小时",
        valid_from="2026-08-01T00:00:00",
        valid_until="2026-08-31T23:59:59",
        run_hours=38226.3,
        color="#FBBF24",
    )
    graph.add_node(
        "event:jul-alarm-drop",
        "event",
        content="7 月报警掉到 2074 条",
        valid_from="2026-07-01T00:00:00",
        valid_until="2026-07-31T23:59:59",
        alarm_count=2074,
        color="#FB7185",
    )
    graph.add_edge("event:aug-run-surge", "month:2026-08", "about")
    graph.add_edge("event:jul-alarm-drop", "month:2026-07", "about")
    graph.add_edge("event:aug-run-surge", "domain:cnc_run", "measures")
    graph.add_edge("event:jul-alarm-drop", "domain:alarm", "measures")

    decisions = [
        (
            "decision:drop_mar",
            "丢掉 2026-03 空转月",
            "data_quality",
            "3 月几乎全停，若留在 device_day 会把利用率拉成近零",
            "Grill B5：3 月只进 dq_report，业务窗口从 4 月起",
            "approved",
            0.96,
            [("about", "domain:cnc_run"), ("resultedIn", "dq:dropped_march:device_day")],
        ),
        (
            "decision:drop_idle_month",
            "丢掉整月零运行的设备-月",
            "data_quality",
            "接口齐全不等于这段时间在干活",
            "Grill B3：台留在 device_dim，空月从 device_day 删除，4–8 月事件仍保留",
            "approved",
            0.93,
            [("about", "domain:cnc_run"), ("resultedIn", "dq:dropped_idle_device_month:device_day")],
        ),
        (
            "decision:exclude_172609583",
            "排除无台账设备 172609583",
            "data_quality",
            "GetEquipInfoPageList 空，没有 CompanyId/EquipCode",
            "D1 exclude：不编造身份，不进清洗集",
            "approved",
            0.99,
            [("about", "excluded:172609583")],
        ),
        (
            "decision:snapshot_keep",
            "主轴只作快照，不摊到 4–8 月",
            "signal_coverage",
            "GetEquipSpindleWithFeedData 无日期入参",
            "E1 snapshot_keep：禁止把 as_of 当工况时序",
            "approved",
            0.94,
            [("about", "domain:cnc_run")],
        ),
        (
            "decision:uncover_cmms",
            "没有保养换刀台账就不造维护表",
            "signal_coverage",
            "报警几乎全是已解决，ProcessDept 是正文不是部门",
            "E2 uncover：宁肯错杀，缺口写入 uncovered_signals",
            "approved",
            0.92,
            [("about", "domain:alarm")],
        ),
        (
            "decision:no_fleet_plan_kpi",
            "禁止把计划达成率做舰队平均",
            "metric_semantics",
            "PlanOutput 只有极少数设备非空",
            "只在 plan_output 非空且非 0 的进度行计算达成率",
            "approved",
            0.9,
            [("about", "domain:program")],
        ),
    ]
    for node_id, content, category, scenario, reasoning, outcome, confidence, links in decisions:
        graph.add_node(
            node_id,
            "decision",
            content=content,
            category=category,
            scenario=scenario,
            reasoning=reasoning,
            outcome=outcome,
            confidence=confidence,
            timestamp="2026-09-17",
            color="#F472B6",
        )
        for rel, target in links:
            graph.add_edge(node_id, target, rel)
    graph.add_edge("decision:drop_mar", "decision:drop_idle_month", "precedes")
    graph.add_edge("decision:snapshot_keep", "decision:uncover_cmms", "relatedTo")

    graph.add_node("agent:semantica-clean", "system", content="process_iot_timeseries.py", color="#94A3B8")
    graph.add_node("activity:iot-clean", "process", content="清洗 199 台 Mar–Aug JSON → parquet", color="#F59E0B")
    graph.add_node("entity:iot-json", "Dataset", content="datasets/json/iot_timeseries", color="#64748B")
    graph.add_node("entity:iot-parquet", "Dataset", content="datasets/processed/iot_mar_aug_2026", color="#64748B")
    graph.add_edge("activity:iot-clean", "agent:semantica-clean", "wasAssociatedWith")
    graph.add_edge("activity:iot-clean", "entity:iot-json", "used")
    graph.add_edge("activity:iot-clean", "entity:iot-parquet", "generated")
    graph.add_edge("dataset:cleaned", "entity:iot-parquet", "wasDerivedFrom")

    graph.add_node(
        "demo:status-stop",
        "Customer",
        content="关机时间",
        note="Enrich 合并样例：保留端",
        color="#FDE68A",
    )
    graph.add_node(
        "demo:status-idle-mislabel",
        "Customer",
        content="关机时间（误标停机）",
        note="Enrich 合并样例：重复端",
        color="#FDE68A",
    )
    graph.add_edge("demo:status-stop", f"{skos}#stop", "labeledAs")
    graph.add_edge("demo:status-idle-mislabel", f"{skos}#idle", "misreadAs")
    graph.add_edge("demo:status-idle-mislabel", "demo:status-stop", "sameAsCandidate")
    graph.add_node(
        "customer:alias-shebeiku",
        "Customer",
        content="设备库",
        note="与现场客户「设备库」同名，供 Entity Resolution 扫描",
        color="#FDE68A",
    )


DATASETS = [
    (
        "alice_bob_acme.json",
        alice_bob_acme,
        "examples/explorer_deterministic_rendering_example.py",
        "Explorer baseline: Alice, Bob, Acme, New York",
        ["explorer", "small", "org"],
    ),
    (
        "apple_inc.json",
        apple_inc,
        "cookbook/introduction/08_Your_First_Knowledge_Graph.ipynb + sample_document.txt",
        "Apple Inc. first knowledge graph",
        ["cookbook", "org"],
    ),
    (
        "tech_corp.json",
        tech_corp,
        "cookbook/introduction/16_Visualization.ipynb + cookbook/advanced/03_Complete_Visualization_Suite.ipynb",
        "Tech Corp visualization sample",
        ["cookbook", "visualization"],
    ),
    (
        "lab_alpha.json",
        lab_alpha,
        "cookbook/advanced/03_Complete_Visualization_Suite.ipynb temporal section",
        "Lab Alpha research network with timeline",
        ["cookbook", "temporal", "explorer"],
    ),
    (
        "startup_investment.json",
        startup_investment,
        "cookbook/advanced/02_Advanced_Graph_Analytics.ipynb",
        "Startup investment graph (dangling edge removed)",
        ["cookbook", "temporal", "analytics"],
    ),
    (
        "company_aliases.json",
        company_aliases,
        "cookbook/introduction/18_Deduplication.ipynb",
        "Company name aliases for entity resolution demos",
        ["cookbook", "dedup"],
    ),
    (
        "disease_network.json",
        disease_network,
        "tests/cookbook/test_disease_network_analysis.py",
        "Disease–symptom–treatment network",
        ["healthcare", "cookbook"],
    ),
    (
        "python_ecosystem.json",
        python_ecosystem,
        "cookbook/advanced/06_Multi_Source_Data_Integration.ipynb",
        "Python language / docs / PyPI libraries",
        ["cookbook", "software"],
    ),
    (
        "programming_stack.json",
        programming_stack,
        "tests/explorer/test_explorer_api.py",
        "Explorer API sample: languages, decisions, temporal event",
        ["explorer", "decisions", "temporal"],
    ),
    (
        "manufacturing_shopfloor.json",
        manufacturing_shopfloor,
        "cookbook/use_cases/manufacturing/sample/seed.sql",
        "Machine-tool shop floor: site, work orders, inspection",
        ["manufacturing", "temporal"],
    ),
    (
        "device_iot_model.json",
        device_iot_model,
        "datasets/json/source/equip_master_200.json + datasets/json/iot_timeseries/_complete",
        "200-equip master joined to complete IoT dimensions and API lineage",
        ["manufacturing", "iot", "telemetry", "lineage"],
    ),
    (
        "complete_device_ledger.json",
        complete_device_ledger,
        "datasets/json/iot_timeseries/_complete",
        "OpenAPI-complete device ledger with Mar–Aug utilization",
        ["manufacturing", "iot", "explorer", "ledger"],
    ),
    (
        "iot_cleaned_semantics.json",
        cleaned_iot_semantics,
        "datasets/processed/iot_mar_aug_2026",
        "清洗后完备设备语义图：机型×月衍生强度、客户×设备、报警号×机型",
        ["manufacturing", "iot", "explorer", "cleaned", "semantics"],
    ),
    (
        "corporate_org.json",
        corporate_org,
        "cookbook/introduction/corporate_ontology.ttl",
        "Corporate org chart aligned to the cookbook ontology",
        ["ontology", "org"],
    ),
]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Writing demo graphs to {OUT_DIR}")
    catalog = []
    for filename, builder, source, title, tags in DATASETS:
        catalog.append(_save(builder(), filename, source=source, title=title, tags=tags))
    catalog_path = OUT_DIR / "catalog.json"
    catalog_path.write_text(json.dumps({"datasets": catalog}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {catalog_path.relative_to(OUT_DIR.parent.parent)} ({len(catalog)} datasets)")


if __name__ == "__main__":
    main()
