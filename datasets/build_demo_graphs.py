"""Build Explorer-ready ContextGraph JSON files from in-repo demo sources."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from semantica.context.context_graph import ContextGraph

OUT_DIR = Path(__file__).resolve().parent / "json"


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
