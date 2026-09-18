"""Clean complete-device IoT JSON into parquet tables (OpenSpec iot-data-processing).

Reads Excel master + per-device JSON. Does not call OpenAPI.
Does not modify source JSON except `_semantic/metric_catalog.json`.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

_DS = Path(__file__).resolve().parent
if str(_DS) not in sys.path:
    sys.path.insert(0, str(_DS))

from fetch_iot_timeseries import (  # noqa: E402
    MASTER_PATH as DEFAULT_MASTER,
    ROOT as DEFAULT_ROOT,
    device_gaps,
    duration_to_seconds,
    load_json,
    parse_pct,
    write_json,
)

WINDOW_START = date(2026, 4, 1)
WINDOW_END = date(2026, 8, 31)
DEFAULT_DAYS = 184
DEFAULT_OUT = _DS / "processed" / "iot_mar_aug_2026"
SEMANTIC_CATALOG = DEFAULT_ROOT / "_semantic" / "metric_catalog.json"
FORBIDDEN_COLS = {"label", "y", "is_fault", "split"}
UNCOVERED_SIGNALS = [
    "跟随误差",
    "轴温",
    "冷却液",
    "液压",
    "振动",
    "保养台账",
    "换刀事件",
]
PII_KEYS = {
    "Ip",
    "SIMNo",
    "Reportor",
    "ReportPhone",
    "Repairtor",
    "RepairPhone",
    "Address",
    "CompanyPhone",
}

DEVICE_DIM_COLS = [
    "out_factory_code",
    "equip_code",
    "equip_name",
    "equip_type_id",
    "equip_type_code",
    "equip_type_name",
    "gate_id",
    "gw_code",
    "company_id",
    "company_name",
    "area_name",
    "out_factory_date",
    "info_create_date",
    "excel_equip_type_code",
    "info_id",
]
DEVICE_DAY_COLS = [
    "out_factory_code",
    "date",
    "month",
    "equip_code",
    "equip_name",
    "equip_type_code",
    "equip_type_name",
    "company_id",
    "total_time_raw",
    "run_time_raw",
    "standby_time_raw",
    "stop_time_raw",
    "breakdown_time_raw",
    "run_time_sec",
    "standby_time_sec",
    "stop_time_sec",
    "breakdown_time_sec",
    "total_time_sec",
    "run_time_rate_pct",
    "standby_time_rate_pct",
    "stop_time_rate_pct",
    "breakdown_time_rate_pct",
    "alarm_count",
    "alarm_shutdown_count",
    "program_cycle_count",
    "program_seconds",
    "progress_output",
    "progress_plan_output",
    "is_run_day",
    "run_hours",
]
ALARM_COLS = [
    "alarm_id",
    "out_factory_code",
    "equip_code",
    "equip_name",
    "equip_type_code",
    "equip_type_name",
    "abno_code",
    "abno_type_name",
    "abno_content",
    "create_time",
    "duration_sec_api",
    "duration_detail",
    "duration_sec",
    "is_shutdown",
    "process_status",
    "is_concerned",
    "process_time",
    "level",
]
PROGRAM_COLS = [
    "program_id",
    "equip_code",
    "equip_name",
    "equip_type_code",
    "equip_type_name",
    "out_factory_code",
    "program_code",
    "output",
    "output_sum_second",
    "output_sum_raw",
    "avg_output_time_second",
    "avg_output_time_raw",
    "start_time",
    "end_time",
]
PROGRESS_COLS = [
    "progress_id",
    "out_factory_code",
    "equip_code",
    "equip_name",
    "equip_type_code",
    "equip_type_name",
    "company_id",
    "workshop_id",
    "program_code",
    "stat_date",
    "output",
    "plan_output",
    "plan_achievement_pct",
    "avg_output_time_second",
    "output_sum_second",
    "processing_time_sum_raw",
    "processing_time_sum_sec",
    "avg_processing_time_raw",
    "avg_processing_time_sec",
    "shift_start_time",
    "shift_end_time",
    "row_create_time",
]
SPINDLE_COLS = [
    "out_factory_code",
    "equip_code",
    "as_of",
    "x_ac",
    "x_load",
    "y_ac",
    "y_load",
    "z_ac",
    "z_load",
    "a_ac",
    "a_load",
    "c_ac",
    "c_load",
    "main_arbor",
    "speed",
    "speed_rate",
    "spindle_load",
    "feed",
    "feed_rate",
    "program_name",
    "program_code",
    "knife_position",
    "electricity",
    "line_no",
    "program_ac",
    "program_order",
    "son_program_code",
    "gcode_content",
]
CUSTOMER_ASOF_COLS = [
    "company_id",
    "company_name",
    "en_code",
    "area_name",
    "fault_count",
    "processing_count",
    "idle_count",
    "standby_count",
    "box_disconnect_count",
    "total_equip_count",
    "boot_rate_30d",
    "util_rate_30d",
    "as_of",
    "is_summary",
]
BOOT_COLS = [
    "company_id",
    "company_name",
    "equip_count",
    "total_running_time_sec",
    "total_boot_time_sec",
    "start_time",
    "end_time",
    "as_of",
]


class DqReport:
    def __init__(self) -> None:
        self.rules: dict[str, dict[str, Any]] = {}
        self.excluded_incomplete: list[dict[str, Any]] = []

    def add(self, rule_id: str, table: str, key: Any, note: str = "") -> None:
        bucket = self.rules.setdefault(
            (rule_id, table),
            {"rule_id": rule_id, "table": table, "count": 0, "example_keys": [], "note": note},
        )
        if note and not bucket["note"]:
            bucket["note"] = note
        bucket["count"] += 1
        if len(bucket["example_keys"]) < 8 and key is not None:
            rendered = key if isinstance(key, (str, int)) else str(key)
            if rendered not in bucket["example_keys"]:
                bucket["example_keys"].append(rendered)

    def to_dict(self, *, complete: int) -> dict[str, Any]:
        return {
            "window": {"start": WINDOW_START.isoformat(), "end": WINDOW_END.isoformat()},
            "complete_devices": complete,
            "excluded_incomplete": self.excluded_incomplete,
            "uncovered_signals": UNCOVERED_SIGNALS,
            "rules": sorted(self.rules.values(), key=lambda r: (r["rule_id"], r["table"])),
        }


def parse_day(value: Any) -> date | None:
    if value is None or value == "":
        return None
    text = str(value).strip()
    if not text or text in {"-", "null"}:
        return None
    text = text.replace("/", "-")
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        try:
            return datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S").date()
        except ValueError:
            return None


def parse_dt(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    text = str(value).strip()
    if not text or text.startswith("0001-"):
        return None
    text = text.replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:19] if fmt.endswith("%S") else text[:10], fmt)
        except ValueError:
            continue
    return None


def as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def as_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def is_shutdown_flag(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if value in (1, "1", True, "true", "True"):
        return 1
    if value in (0, "0", False, "false", "False"):
        return 0
    return None


def is_summary_row(row: dict) -> bool:
    if row.get("IsSummary") in (True, "true", 1, "1"):
        return True
    name = str(row.get("CustomerName") or row.get("CompanyName") or "")
    return name.strip() in {"合计", "汇总"}


def in_window(day: date | None) -> bool:
    return day is not None and WINDOW_START <= day <= WINDOW_END


def is_march(day: date | None) -> bool:
    return day is not None and day.year == 2026 and day.month == 3


def seconds_or_parse(sec_value: Any, raw_value: Any) -> int | None:
    parsed = as_int(sec_value)
    if parsed is not None:
        return parsed
    return duration_to_seconds(raw_value)


def rate_or_parse(pct_value: Any, raw_value: Any) -> float | None:
    parsed = as_float(pct_value)
    if parsed is not None:
        return parsed
    return parse_pct(raw_value)


def resolve_alarm_duration(duration_api: int | None, duration_detail: Any) -> tuple[int | None, bool]:
    detail = duration_to_seconds(duration_detail)
    if detail is None:
        return duration_api, False
    if duration_api is None or duration_api == 0:
        return detail, False
    if duration_api == detail:
        return detail, False
    return None, True


def payload_rows(payload: dict | None) -> list[dict]:
    if not payload:
        return []
    rows = payload.get("rows") or []
    return [row for row in rows if isinstance(row, dict)]


def write_table(path: Path, rows: list[dict], columns: list[str]) -> None:
    frame = pd.DataFrame(rows, columns=columns)
    overlap = FORBIDDEN_COLS.intersection(frame.columns)
    if overlap:
        raise ValueError(f"forbidden columns in {path.name}: {sorted(overlap)}")
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)


def write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def metric_catalog(complete: int, excluded: list[str]) -> dict[str, Any]:
    return {
        "title": "完备设备语义指标目录",
        "window": {"StartTime": WINDOW_START.isoformat(), "EndTime": WINDOW_END.isoformat()},
        "population": {
            "complete_devices": complete,
            "excluded": excluded,
            "note": "磁盘完备，非 _complete/catalog.json",
        },
        "decisions": [
            "B1 clean_only",
            "B4 pooled_flag",
            "B5 drop_mar",
            "D3 by_company",
            "E1 snapshot_keep",
            "E2 uncover",
        ],
        "dimensions": [
            {"id": "out_factory_code", "name_zh": "出厂编号", "role": "device_key"},
            {"id": "equip_code", "name_zh": "数控系统编码", "role": "join_key"},
            {"id": "equip_name", "name_zh": "客户设备编码", "role": "site_label"},
            {"id": "equip_type_code", "name_zh": "设备类型编码", "role": "type"},
            {"id": "equip_type_name", "name_zh": "设备名称", "role": "type_label"},
            {"id": "company_id", "name_zh": "客户ID", "role": "split_key"},
            {"id": "company_name", "name_zh": "客户名称", "role": "split_label"},
            {"id": "area_name", "name_zh": "区域", "role": "geo"},
            {"id": "date", "name_zh": "统计日期", "role": "time_day"},
            {"id": "month", "name_zh": "自然月", "role": "time_month"},
            {"id": "program_code", "name_zh": "加工程序名", "role": "job"},
            {"id": "abno_code", "name_zh": "报警号", "role": "alarm"},
            {"id": "abno_type_name", "name_zh": "报警类别", "role": "alarm_type"},
            {"id": "is_shutdown", "name_zh": "是否停机报警", "role": "alarm_flag"},
            {"id": "as_of", "name_zh": "快照时刻", "role": "snapshot", "not": "history"},
        ],
        "measures": [
            {"id": "run_time_sec", "name_zh": "运行时间", "grain": "device_day", "domain": "cnc_run", "unit": "s", "not": "件数"},
            {"id": "standby_time_sec", "name_zh": "待机时间", "grain": "device_day", "domain": "cnc_run", "unit": "s", "not": "停机"},
            {"id": "stop_time_sec", "name_zh": "关机时间", "grain": "device_day", "domain": "cnc_run", "unit": "s", "not": "停机"},
            {"id": "breakdown_time_sec", "name_zh": "故障时间", "grain": "device_day", "domain": "cnc_run", "unit": "s", "not": "停机报警条数"},
            {"id": "run_time_rate_pct", "name_zh": "运行时间占比", "grain": "device_day", "domain": "cnc_run", "unit": "%", "not": "客户近30天稼动率"},
            {"id": "is_run_day", "name_zh": "有运行日", "grain": "device_day", "domain": "cnc_run", "unit": "flag", "formula": "run_time_sec>0"},
            {"id": "run_hours", "name_zh": "运行小时", "grain": "additive", "domain": "cnc_run", "unit": "h", "formula": "run_time_sec/3600"},
            {"id": "alarm_count", "name_zh": "报警条数", "grain": "alarm|device_day", "domain": "alarm", "unit": "count"},
            {"id": "alarm_shutdown_count", "name_zh": "停机报警条数", "grain": "alarm|device_day", "domain": "alarm", "unit": "count", "formula": "IsShutdown=1"},
            {"id": "alarm_duration_sec", "name_zh": "报警持续秒", "grain": "alarm", "domain": "alarm", "unit": "s", "source": "DurationDetail"},
            {"id": "program_cycles", "name_zh": "累计循环次数", "grain": "program_cycle|device_day", "domain": "program", "unit": "count"},
            {"id": "program_seconds", "name_zh": "累计循环时间", "grain": "program_cycle", "domain": "program", "unit": "s"},
            {"id": "progress_output", "name_zh": "日产量循环次数", "grain": "progress_day", "domain": "program", "unit": "count"},
            {"id": "plan_output", "name_zh": "计划产量", "grain": "progress_day", "domain": "program", "unit": "count", "coverage": "sparse"},
            {"id": "plan_achievement_pct", "name_zh": "计划达成率", "grain": "progress_day", "domain": "program", "unit": "%", "formula": "output/plan_output", "do_not": "fleet_average"},
            {"id": "spindle_load", "name_zh": "主轴负载", "grain": "spindle_asof", "domain": "axis_snapshot", "unit": "raw"},
            {"id": "feed", "name_zh": "进给", "grain": "spindle_asof", "domain": "axis_snapshot", "unit": "raw"},
            {"id": "speed", "name_zh": "转速", "grain": "spindle_asof", "domain": "axis_snapshot", "unit": "raw"},
        ],
        "slices": [
            "equip_type_code × month",
            "company_id × out_factory_code",
            "out_factory_code × date",
            "abno_code × equip_type_code",
            "program_code × out_factory_code",
        ],
        "derived_recipes": [
            {"id": "alarm_per_run_hour", "op": "div", "a": "alarm_count", "b": "run_hours", "name_zh": "每运行小时报警", "not": "故障率 / OEE"},
            {"id": "shutdown_alarm_rate", "op": "div", "a": "alarm_shutdown_count", "b": "alarm_count", "name_zh": "停机报警占比", "not": "故障时长占比"},
            {"id": "run_hours_per_run_day", "op": "div", "a": "run_hours", "b": "run_days", "name_zh": "有运行日均运行小时", "not": "开机率"},
            {"id": "run_hours_per_device", "op": "div", "a": "run_hours", "b": "devices", "name_zh": "单台运行小时", "not": "客户近30天稼动率"},
            {"id": "cycles_per_run_hour", "op": "div", "a": "program_cycles", "b": "run_hours", "name_zh": "每运行小时循环", "not": "计划达成率"},
            {"id": "seconds_per_cycle", "op": "div", "a": "program_seconds", "b": "program_cycles", "name_zh": "单次循环秒"},
            {"id": "alarm_per_device", "op": "div", "a": "alarm_count", "b": "devices", "name_zh": "单台报警条数"},
            {"id": "run_time_share", "op": "div", "a": "run_time_sec", "b": "total_time_sec", "name_zh": "运行时间结构占比", "not": "客户近30天稼动率"},
            {"id": "standby_time_share", "op": "div", "a": "standby_time_sec", "b": "total_time_sec", "name_zh": "待机时间结构占比", "not": "停机"},
            {"id": "stop_time_share", "op": "div", "a": "stop_time_sec", "b": "total_time_sec", "name_zh": "关机时间结构占比", "not": "停机"},
            {"id": "breakdown_time_share", "op": "div", "a": "breakdown_time_sec", "b": "total_time_sec", "name_zh": "故障时间结构占比", "not": "停机报警占比"},
            {"id": "run_hours_share", "op": "share", "a": "run_hours", "name_zh": "运行小时舰队份额", "not": "稼动率"},
            {"id": "alarm_duration_per_event", "op": "div", "a": "alarm_duration_sec", "b": "alarm_count", "name_zh": "单条报警持续秒"},
            {"id": "compose", "note": "Analyze 可对基础指标做 ÷ × + − 份额；除零为 null；禁止 OEE / is_fault / 舰队平均计划达成率"},
        ],
    }


def build_device_dim(info: dict, excel_type: str | None, dq: DqReport) -> dict[str, Any] | None:
    rows = payload_rows(info)
    if not rows:
        return None
    row = rows[0]
    dim = {
        "out_factory_code": as_str(row.get("OutFactoryCode")),
        "equip_code": as_str(row.get("EquipCode")),
        "equip_name": as_str(row.get("EquipName")),
        "equip_type_id": as_str(row.get("EquipTypeId")),
        "equip_type_code": as_str(row.get("EquipTypeCode")),
        "equip_type_name": as_str(row.get("EquipTypeName")),
        "gate_id": as_str(row.get("GateId")),
        "gw_code": as_str(row.get("GwCode")),
        "company_id": as_str(row.get("CompanyId")),
        "company_name": as_str(row.get("CompanyName")),
        "area_name": as_str(row.get("AreaName")),
        "out_factory_date": as_str(row.get("OutFactoryDate")),
        "info_create_date": as_str(row.get("CreateDate")),
        "excel_equip_type_code": as_str(excel_type),
        "info_id": as_str(row.get("Id")),
    }
    if not dim["equip_type_code"]:
        raise ValueError(f"empty equip_type_code for {dim['out_factory_code']}")
    if dim["excel_equip_type_code"] and dim["excel_equip_type_code"] != dim["equip_type_code"]:
        dq.add(
            "excel_type_mismatch",
            "device_dim",
            dim["out_factory_code"],
            "Excel EquipTypeCode 与台账不一致",
        )
    leaked = PII_KEYS.intersection(dim)
    if leaked:
        raise ValueError(f"PII leaked into device_dim: {leaked}")
    return dim


def build_spindle(code: str, payload: dict, dim: dict) -> dict[str, Any] | None:
    data = payload.get("ResultData")
    if not isinstance(data, dict):
        return None
    return {
        "out_factory_code": code,
        "equip_code": as_str(data.get("EquipCode")) or dim.get("equip_code"),
        "as_of": as_str(payload.get("Timestamp") or payload.get("fetched_at")),
        "x_ac": as_str(data.get("XAC")),
        "x_load": as_str(data.get("XLoad")),
        "y_ac": as_str(data.get("YAC")),
        "y_load": as_str(data.get("YLoad")),
        "z_ac": as_str(data.get("ZAC")),
        "z_load": as_str(data.get("ZLoad")),
        "a_ac": as_str(data.get("AAC")),
        "a_load": as_str(data.get("ALoad")),
        "c_ac": as_str(data.get("CAC")),
        "c_load": as_str(data.get("CLoad")),
        "main_arbor": as_str(data.get("MainArbor")),
        "speed": as_str(data.get("Speed")),
        "speed_rate": as_str(data.get("SpeedRate")),
        "spindle_load": as_str(data.get("Load")),
        "feed": as_str(data.get("Feed")),
        "feed_rate": as_str(data.get("FeedRate")),
        "program_name": as_str(data.get("ProgramName")),
        "program_code": as_str(data.get("ProgramCode")),
        "knife_position": as_str(data.get("KnifePosition")),
        "electricity": as_str(data.get("Electricity")),
        "line_no": as_str(data.get("LineNo")),
        "program_ac": as_str(data.get("ProgramAC")),
        "program_order": as_str(data.get("ProgramOrder")),
        "son_program_code": as_str(data.get("SonProgramCode")),
        "gcode_content": as_str(data.get("GcodeCoent")),
    }


def identity_ok(row: dict, dim: dict) -> bool:
    row_code = as_str(row.get("EquipCode"))
    dim_code = dim.get("equip_code")
    if not row_code or not dim_code or row_code != dim_code:
        return False
    row_of = as_str(row.get("OutFactoryCode"))
    if row_of and row_of != dim.get("out_factory_code"):
        return False
    return True


def reject_row(table: str, reason: str, dim: dict, row: dict) -> dict[str, Any]:
    return {
        "table": table,
        "reason": reason,
        "out_factory_code": dim.get("out_factory_code"),
        "equip_code": as_str(row.get("EquipCode")),
        "source_id": as_str(row.get("Id") or row.get("EquipProgramOutPutInDayId")),
    }


def process_alarms(rows: list[dict], dim: dict, dq: DqReport) -> tuple[list[dict], list[dict]]:
    kept: list[dict] = []
    rejected: list[dict] = []
    for row in rows:
        if not identity_ok(row, dim):
            rejected.append(reject_row("alarm_event", "equip_code_mismatch", dim, row))
            dq.add("equip_code_mismatch", "alarm_event", as_str(row.get("Id")))
            continue
        day = parse_day(row.get("CreateTime") or row.get("StrCreateTime"))
        if is_march(day):
            dq.add("dropped_march", "alarm_event", as_str(row.get("Id")))
            continue
        if not in_window(day):
            continue
        duration_api = as_int(row.get("Duration"))
        duration_sec, conflict = resolve_alarm_duration(duration_api, row.get("DurationDetail"))
        if conflict:
            dq.add("duration_conflict", "alarm_event", as_str(row.get("Id")), "Duration 与 DurationDetail 冲突")
        kept.append(
            {
                "alarm_id": as_str(row.get("Id")),
                "out_factory_code": dim["out_factory_code"],
                "equip_code": as_str(row.get("EquipCode")),
                "equip_name": as_str(row.get("EquipName")),
                "equip_type_code": as_str(row.get("EquipTypeCode")) or dim.get("equip_type_code"),
                "equip_type_name": as_str(row.get("EquipTypeName")) or dim.get("equip_type_name"),
                "abno_code": as_str(row.get("AbnoCode")),
                "abno_type_name": as_str(row.get("AbnoTypeName")),
                "abno_content": as_str(row.get("AbnoContent")),
                "create_time": as_str(row.get("CreateTime")),
                "duration_sec_api": duration_api,
                "duration_detail": as_str(row.get("DurationDetail")),
                "duration_sec": duration_sec,
                "is_shutdown": is_shutdown_flag(row.get("IsShutdown")),
                "process_status": as_str(row.get("ProcessStatus")),
                "is_concerned": is_shutdown_flag(row.get("IsConcerned")),
                "process_time": as_str(row.get("ProcessTime")),
                "level": as_str(row.get("Level")),
            }
        )
    return kept, rejected


def process_programs(rows: list[dict], dim: dict, dq: DqReport) -> tuple[list[dict], list[dict]]:
    kept: list[dict] = []
    rejected: list[dict] = []
    for row in rows:
        if not identity_ok(row, dim):
            rejected.append(reject_row("program_cycle", "equip_code_mismatch", dim, row))
            dq.add("equip_code_mismatch", "program_cycle", as_str(row.get("Id")))
            continue
        start = parse_dt(row.get("StartTime"))
        end = parse_dt(row.get("EndTime"))
        day = start.date() if start else parse_day(row.get("StartTime"))
        if is_march(day):
            dq.add("dropped_march", "program_cycle", as_str(row.get("Id")))
            continue
        if day is not None and not in_window(day):
            continue
        if start and end and end < start:
            dq.add("program_end_before_start", "program_cycle", as_str(row.get("Id")))
        kept.append(
            {
                "program_id": as_str(row.get("Id")),
                "equip_code": as_str(row.get("EquipCode")),
                "equip_name": as_str(row.get("EquipName")),
                "equip_type_code": as_str(row.get("EquipTypeCode")) or dim.get("equip_type_code"),
                "equip_type_name": as_str(row.get("EquipTypeName")) or dim.get("equip_type_name"),
                "out_factory_code": dim["out_factory_code"],
                "program_code": as_str(row.get("ProgramCode")),
                "output": as_int(row.get("Output")),
                "output_sum_second": as_int(row.get("OutputSumSecond")),
                "output_sum_raw": as_str(row.get("OutputSum")),
                "avg_output_time_second": as_int(row.get("AvgOutPutTimeSecond")),
                "avg_output_time_raw": as_str(row.get("AvgOutPutTime")),
                "start_time": as_str(row.get("StartTime")),
                "end_time": as_str(row.get("EndTime")),
            }
        )
    return kept, rejected


def process_progress(rows: list[dict], dim: dict, dq: DqReport) -> tuple[list[dict], list[dict]]:
    kept: list[dict] = []
    rejected: list[dict] = []
    for row in rows:
        if not identity_ok(row, dim):
            rejected.append(reject_row("progress_day", "equip_code_mismatch", dim, row))
            dq.add("equip_code_mismatch", "progress_day", as_str(row.get("EquipProgramOutPutInDayId")))
            continue
        day = parse_day(row.get("StatisticalDateStr") or row.get("StatisticalDate"))
        if is_march(day):
            dq.add("dropped_march", "progress_day", as_str(row.get("EquipProgramOutPutInDayId")))
            continue
        if not in_window(day):
            continue
        output = as_int(row.get("Output"))
        plan_output = as_int(row.get("PlanOutput"))
        achievement = None
        if output is not None and plan_output not in (None, 0):
            achievement = round(output / plan_output * 100, 4)
        kept.append(
            {
                "progress_id": as_str(row.get("EquipProgramOutPutInDayId")),
                "out_factory_code": as_str(row.get("OutFactoryCode")) or dim["out_factory_code"],
                "equip_code": as_str(row.get("EquipCode")),
                "equip_name": as_str(row.get("EquipName")),
                "equip_type_code": as_str(row.get("EquipTypeCode")) or dim.get("equip_type_code"),
                "equip_type_name": as_str(row.get("EquipTypeName")) or dim.get("equip_type_name"),
                "company_id": as_str(row.get("CompanyId")) or dim.get("company_id"),
                "workshop_id": as_str(row.get("WorkshopId")),
                "program_code": as_str(row.get("ProgramCode")),
                "stat_date": day.isoformat() if day else None,
                "output": output,
                "plan_output": plan_output,
                "plan_achievement_pct": achievement,
                "avg_output_time_second": as_int(row.get("AvgOutPutTimeSecond")),
                "output_sum_second": as_int(row.get("OutputSumSecond")),
                "processing_time_sum_raw": as_str(row.get("ProcessingTimeSum")),
                "processing_time_sum_sec": duration_to_seconds(row.get("ProcessingTimeSum")),
                "avg_processing_time_raw": as_str(row.get("AvgProcessingTime")),
                "avg_processing_time_sec": duration_to_seconds(row.get("AvgProcessingTime")),
                "shift_start_time": as_str(row.get("ShiftStartTime")),
                "shift_end_time": as_str(row.get("ShiftEndTime")),
                "row_create_time": as_str(row.get("CreateTime")),
            }
        )
    return kept, rejected


def process_run_days(rows: list[dict], dim: dict, dq: DqReport) -> list[dict]:
    candidates: list[dict] = []
    for row in rows:
        if not row.get("ok", True):
            continue
        day = parse_day(row.get("date"))
        if is_march(day):
            dq.add("dropped_march", "device_day", f"{dim['out_factory_code']}|{day}")
            continue
        if not in_window(day):
            continue
        run_sec = seconds_or_parse(row.get("RunTimeSec"), row.get("RunTime")) or 0
        standby_sec = seconds_or_parse(row.get("StandbyTimeSec"), row.get("StandbyTime")) or 0
        stop_sec = seconds_or_parse(row.get("StopTimeSec"), row.get("StopTime")) or 0
        breakdown_sec = seconds_or_parse(row.get("BreakDownTimeSec"), row.get("BreakDownTime")) or 0
        total_sec = seconds_or_parse(row.get("TotalTimeSec"), row.get("TotalTime"))
        bucket_sum = run_sec + standby_sec + stop_sec + breakdown_sec
        if total_sec is not None and bucket_sum != total_sec:
            dq.add(
                "four_bucket_imbalance",
                "device_day",
                f"{dim['out_factory_code']}|{day.isoformat()}",
                "四桶秒之和 ≠ total_time_sec",
            )
        candidates.append(
            {
                "out_factory_code": dim["out_factory_code"],
                "date": day.isoformat(),
                "month": day.strftime("%Y-%m"),
                "equip_code": as_str(row.get("EquipCode")) or dim.get("equip_code"),
                "equip_name": as_str(row.get("EquipName")) or dim.get("equip_name"),
                "equip_type_code": as_str(row.get("EquipTypeCode")) or dim.get("equip_type_code"),
                "equip_type_name": as_str(row.get("EquipTypeName")) or dim.get("equip_type_name"),
                "company_id": dim.get("company_id"),
                "total_time_raw": as_str(row.get("TotalTime")),
                "run_time_raw": as_str(row.get("RunTime")),
                "standby_time_raw": as_str(row.get("StandbyTime")),
                "stop_time_raw": as_str(row.get("StopTime")),
                "breakdown_time_raw": as_str(row.get("BreakDownTime")),
                "run_time_sec": run_sec,
                "standby_time_sec": standby_sec,
                "stop_time_sec": stop_sec,
                "breakdown_time_sec": breakdown_sec,
                "total_time_sec": total_sec,
                "run_time_rate_pct": rate_or_parse(row.get("RunTimeRatePct"), row.get("RunTimeRate")),
                "standby_time_rate_pct": rate_or_parse(row.get("StandbyTimeRatePct"), row.get("StandbyTimeRate")),
                "stop_time_rate_pct": rate_or_parse(row.get("StopTimeRatePct"), row.get("StopTimeRate")),
                "breakdown_time_rate_pct": rate_or_parse(
                    row.get("BreakDownTimeRatePct"), row.get("BreakDownTimeRate")
                ),
                "is_run_day": 1 if run_sec > 0 else 0,
                "run_hours": round(run_sec / 3600, 6),
            }
        )
    by_month: dict[str, list[dict]] = defaultdict(list)
    for row in candidates:
        by_month[row["month"]].append(row)
    kept: list[dict] = []
    for month, month_rows in by_month.items():
        if sum(item["run_time_sec"] or 0 for item in month_rows) == 0:
            dq.add(
                "dropped_idle_device_month",
                "device_day",
                f"{dim['out_factory_code']}|{month}",
                "整月运行秒为 0",
            )
            continue
        kept.extend(month_rows)
    return kept


def attach_daily_facts(
    days: list[dict],
    alarms: list[dict],
    programs: list[dict],
    progress: list[dict],
) -> None:
    alarm_n: dict[str, int] = defaultdict(int)
    alarm_sd: dict[str, int] = defaultdict(int)
    for row in alarms:
        key = parse_day(row.get("create_time"))
        if key is None:
            continue
        iso = key.isoformat()
        alarm_n[iso] += 1
        if row.get("is_shutdown") == 1:
            alarm_sd[iso] += 1
    prog_n: dict[str, int] = defaultdict(int)
    prog_sec: dict[str, int] = defaultdict(int)
    for row in programs:
        key = parse_day(row.get("start_time"))
        if key is None:
            continue
        iso = key.isoformat()
        prog_n[iso] += row.get("output") or 0
        prog_sec[iso] += row.get("output_sum_second") or 0
    out_n: dict[str, int] = defaultdict(int)
    plan_n: dict[str, int] = defaultdict(int)
    for row in progress:
        iso = row.get("stat_date")
        if not iso:
            continue
        out_n[iso] += row.get("output") or 0
        plan_n[iso] += row.get("plan_output") or 0
    for row in days:
        iso = row["date"]
        row["alarm_count"] = alarm_n.get(iso, 0)
        row["alarm_shutdown_count"] = alarm_sd.get(iso, 0)
        row["program_cycle_count"] = prog_n.get(iso, 0)
        row["program_seconds"] = prog_sec.get(iso, 0)
        row["progress_output"] = out_n.get(iso, 0)
        row["progress_plan_output"] = plan_n.get(iso, 0)


def process_customers(payload: dict, company_ids: set[str], as_of: str | None) -> list[dict]:
    rows = []
    for row in payload_rows(payload):
        if is_summary_row(row):
            continue
        cid = as_str(row.get("CustomerId"))
        if cid not in company_ids:
            continue
        rows.append(
            {
                "company_id": cid,
                "company_name": as_str(row.get("CustomerName")),
                "en_code": as_str(row.get("EnCode")),
                "area_name": as_str(row.get("AreaName")),
                "fault_count": as_int(row.get("FaultCount")),
                "processing_count": as_int(row.get("ProcessingCount")),
                "idle_count": as_int(row.get("IdleCount")),
                "standby_count": as_int(row.get("StandbyCount")),
                "box_disconnect_count": as_int(row.get("BoxDisconnectCount")),
                "total_equip_count": as_int(row.get("TotalEquipCount")),
                "boot_rate_30d": as_float(row.get("BootRate")),
                "util_rate_30d": as_float(row.get("UtilRate")),
                "as_of": as_of or as_str(payload.get("fetched_at")),
                "is_summary": False,
            }
        )
    return rows


def process_boot(payload: dict, company_ids: set[str]) -> list[dict]:
    rows = []
    query = payload.get("query") or {}
    start = as_str(query.get("StartTime"))
    end = as_str(query.get("EndTime"))
    as_of = as_str(payload.get("fetched_at"))
    for row in payload_rows(payload):
        if is_summary_row(row):
            continue
        cid = as_str(row.get("CustomerId"))
        if cid not in company_ids:
            continue
        rows.append(
            {
                "company_id": cid,
                "company_name": as_str(row.get("CustomerName")),
                "equip_count": as_int(row.get("EquipCount")),
                "total_running_time_sec": as_int(row.get("TotalRunningTime")),
                "total_boot_time_sec": as_int(row.get("TotalBootTime")),
                "start_time": start,
                "end_time": end,
                "as_of": as_of,
            }
        )
    return rows


def process_folder(
    folder: Path,
    excel_type: str | None,
    dq: DqReport,
) -> dict[str, Any] | None:
    info = load_json(folder / "GetEquipInfoPageList.json")
    dim = build_device_dim(info, excel_type, dq)
    if dim is None:
        return None
    alarms, alarm_rej = process_alarms(payload_rows(load_json(folder / "GetEquipAbnorPageList.json")), dim, dq)
    programs, program_rej = process_programs(
        payload_rows(load_json(folder / "GetEquipProgramPageList.json")), dim, dq
    )
    progress, progress_rej = process_progress(
        payload_rows(load_json(folder / "GetEquipProductionProgressPageList.json")), dim, dq
    )
    days = process_run_days(payload_rows(load_json(folder / "GetEquipRunStatusList.json")), dim, dq)
    attach_daily_facts(days, alarms, programs, progress)
    spindle_payload = load_json(folder / "GetEquipSpindleWithFeedData.json")
    spindle = build_spindle(dim["out_factory_code"], spindle_payload, dim)
    boot = process_boot(load_json(folder / "GetEquipBootOrRunningTimeList.json"), {dim["company_id"]} if dim.get("company_id") else set())
    return {
        "dim": dim,
        "days": days,
        "alarms": alarms,
        "programs": programs,
        "progress": progress,
        "spindle": spindle,
        "boot": boot,
        "rejected": alarm_rej + program_rej + progress_rej,
    }


def run(
    *,
    root: Path = DEFAULT_ROOT,
    master_path: Path = DEFAULT_MASTER,
    out_dir: Path = DEFAULT_OUT,
    days: int = DEFAULT_DAYS,
    write_catalog: bool = True,
) -> dict[str, Any]:
    master = load_json(master_path)
    dq = DqReport()
    complete: list[tuple[dict, Path]] = []
    for record in master.get("records") or []:
        code = str(record["OutFactoryCode"])
        folder = root / code
        gaps = device_gaps(folder, days=days)
        if gaps:
            dq.excluded_incomplete.append({"out_factory_code": code, "missing": gaps})
            continue
        complete.append((record, folder))

    dims: list[dict] = []
    days_rows: list[dict] = []
    alarms: list[dict] = []
    programs: list[dict] = []
    progress: list[dict] = []
    spindles: list[dict] = []
    boots: list[dict] = []
    rejected: list[dict] = []
    company_ids: set[str] = set()

    for record, folder in complete:
        result = process_folder(folder, record.get("EquipTypeCode"), dq)
        if result is None:
            continue
        dims.append(result["dim"])
        days_rows.extend(result["days"])
        alarms.extend(result["alarms"])
        programs.extend(result["programs"])
        progress.extend(result["progress"])
        if result["spindle"]:
            spindles.append(result["spindle"])
        boots.extend(result["boot"])
        rejected.extend(result["rejected"])
        if result["dim"].get("company_id"):
            company_ids.add(result["dim"]["company_id"])

    seen_boot: set[tuple] = set()
    unique_boot: list[dict] = []
    for row in boots:
        key = (row.get("company_id"), row.get("start_time"), row.get("end_time"))
        if key in seen_boot:
            continue
        seen_boot.add(key)
        unique_boot.append(row)

    customer_payload = {}
    customer_path = root / "_global" / "GetCustomerList.json"
    if customer_path.exists():
        customer_payload = load_json(customer_path)
    customers = process_customers(
        customer_payload,
        company_ids,
        as_str(customer_payload.get("fetched_at")),
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    write_table(out_dir / "device_dim.parquet", dims, DEVICE_DIM_COLS)
    write_table(out_dir / "device_day.parquet", days_rows, DEVICE_DAY_COLS)
    write_table(out_dir / "alarm_event.parquet", alarms, ALARM_COLS)
    write_table(out_dir / "program_cycle.parquet", programs, PROGRAM_COLS)
    write_table(out_dir / "progress_day.parquet", progress, PROGRESS_COLS)
    write_table(out_dir / "spindle_asof.parquet", spindles, SPINDLE_COLS)
    write_table(out_dir / "customer_asof.parquet", customers, CUSTOMER_ASOF_COLS)
    write_table(out_dir / "customer_boot_window.parquet", unique_boot, BOOT_COLS)
    write_jsonl(out_dir / "rejected" / "identity_mismatch.jsonl", rejected)
    report = dq.to_dict(complete=len(dims))
    write_json(out_dir / "dq_report.json", report)
    if write_catalog:
        SEMANTIC_CATALOG.parent.mkdir(parents=True, exist_ok=True)
        write_json(
            SEMANTIC_CATALOG,
            metric_catalog(len(dims), [row["out_factory_code"] for row in dq.excluded_incomplete]),
        )
    print(
        f"Wrote {out_dir} complete={len(dims)} days={len(days_rows)} "
        f"alarms={len(alarms)} programs={len(programs)} progress={len(progress)} "
        f"excluded={len(dq.excluded_incomplete)} rejected={len(rejected)}",
        flush=True,
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean complete IoT device JSON into parquet")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--master", type=Path, default=DEFAULT_MASTER)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    parser.add_argument("--no-catalog", action="store_true")
    args = parser.parse_args()
    run(
        root=args.root,
        master_path=args.master,
        out_dir=args.out,
        days=args.days,
        write_catalog=not args.no_catalog,
    )


if __name__ == "__main__":
    main()
