"""Fixture tests for IoT timeseries cleaning. No live OpenAPI."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "datasets"))

import process_iot_timeseries as proc  # noqa: E402

GOOD = "GOOD001"
IDLE = "IDLE002"
BAD = "BAD003"
COMPANY_GOOD = "co-good"
COMPANY_IDLE = "co-idle"


def dump(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def info_payload(code: str, equip_code: str, etype: str, ename: str, company: str, rows=None) -> dict:
    if rows is None:
        rows = [
            {
                "Id": f"info-{code}",
                "OutFactoryCode": code,
                "EquipCode": equip_code,
                "EquipName": f"name-{code}",
                "EquipTypeId": "tid",
                "EquipTypeCode": etype,
                "EquipTypeName": ename,
                "GateId": "gid",
                "GwCode": "GW1",
                "Ip": "10.0.0.1",
                "SIMNo": "8986",
                "CompanyId": company,
                "CompanyName": f"客户{code}",
                "AreaName": "华南区",
                "OutFactoryDate": None,
                "CreateDate": "2026-01-01 00:00:00",
            }
        ]
    return {"rows": rows, "record_count": len(rows), "IsSuccess": True}


def run_day(code: str, equip_code: str, etype: str, day: str, run_sec: int, stop_sec: int = 0) -> dict:
    total = run_sec + stop_sec
    return {
        "date": day,
        "ok": True,
        "OutFactoryCode": code,
        "EquipCode": equip_code,
        "EquipName": f"name-{code}",
        "EquipTypeCode": etype,
        "EquipTypeName": "钻攻机" if etype == "T-600" else "立式加工中心",
        "TotalTime": f"{total}秒",
        "RunTime": f"{run_sec}秒",
        "StandbyTime": "0秒",
        "StopTime": f"{stop_sec}秒",
        "BreakDownTime": "0秒",
        "RunTimeSec": run_sec,
        "StandbyTimeSec": 0,
        "StopTimeSec": stop_sec,
        "BreakDownTimeSec": 0,
        "TotalTimeSec": total,
        "RunTimeRate": "10%",
        "StandbyTimeRate": "0%",
        "StopTimeRate": "90%",
        "BreakDownTimeRate": "0%",
        "RunTimeRatePct": 10.0 if run_sec else 0.0,
        "StandbyTimeRatePct": 0.0,
        "StopTimeRatePct": 90.0 if stop_sec else 100.0,
        "BreakDownTimeRatePct": 0.0,
    }


def write_device(
    root: Path,
    code: str,
    *,
    equip_code: str,
    etype: str,
    company: str,
    run_rows: list[dict],
    alarms: list[dict],
    programs: list[dict],
    progress: list[dict],
    info_rows=None,
) -> None:
    folder = root / code
    ename = "钻攻机" if etype == "T-600" else "立式加工中心"
    dump(folder / "GetEquipInfoPageList.json", info_payload(code, equip_code, etype, ename, company, info_rows))
    dump(
        folder / "GetEquipRunStatusList.json",
        {"rows": run_rows, "ok_days": len(run_rows), "record_count": len(run_rows)},
    )
    dump(folder / "GetEquipAbnorPageList.json", {"rows": alarms, "record_count": len(alarms)})
    dump(folder / "GetEquipProgramPageList.json", {"rows": programs, "record_count": len(programs)})
    dump(
        folder / "GetEquipProductionProgressPageList.json",
        {"rows": progress, "record_count": len(progress)},
    )
    dump(
        folder / "GetEquipSpindleWithFeedData.json",
        {
            "IsSuccess": True,
            "Timestamp": "2026-09-16 12:00:00",
            "ResultData": {
                "EquipCode": equip_code,
                "Load": "3",
                "Feed": "100",
                "Speed": "2000",
                "KnifePosition": "4",
                "XLoad": "1",
                "YLoad": "2",
                "ZLoad": "3",
                "Electricity": "0",
            },
        },
    )
    dump(
        folder / "GetEquipBootOrRunningTimeList.json",
        {
            "query": {"StartTime": "2026-03-01", "EndTime": "2026-08-31"},
            "fetched_at": "2026-09-16T12:00:00",
            "rows": [
                {
                    "CustomerId": company,
                    "CustomerName": f"客户{code}",
                    "EquipCount": 2,
                    "TotalRunningTime": 1000,
                    "TotalBootTime": 2000,
                }
            ],
        },
    )
    dump(folder / "trend_summary.json", {"monthly": {}})
    dump(folder / "meta.json", {"OutFactoryCode": code, "identity": {"EquipCode": equip_code}})


@pytest.fixture
def fixture_root(tmp_path: Path) -> Path:
    root = tmp_path / "iot"
    write_device(
        root,
        GOOD,
        equip_code="GOOD001_sk",
        etype="T-600",
        company=COMPANY_GOOD,
        run_rows=[
            run_day(GOOD, "GOOD001_sk", "T-600", "2026-03-31", 100, 0),
            run_day(GOOD, "GOOD001_sk", "T-600", "2026-04-01", 3600, 82800),
            run_day(GOOD, "GOOD001_sk", "T-600", "2026-04-02", 0, 86400),
            run_day(GOOD, "GOOD001_sk", "T-600", "2026-05-01", 1800, 84600),
        ],
        alarms=[
            {
                "Id": "a-mar",
                "OutFactoryCode": GOOD,
                "EquipCode": "GOOD001_sk",
                "AbnoCode": "M01",
                "CreateTime": "2026-03-15 10:00:00",
                "Duration": 0,
                "DurationDetail": "10秒",
                "IsShutdown": 1,
            },
            {
                "Id": "a-ok",
                "OutFactoryCode": GOOD,
                "EquipCode": "GOOD001_sk",
                "AbnoCode": "O0005",
                "CreateTime": "2026-04-01 10:00:00",
                "Duration": 0,
                "DurationDetail": "40秒",
                "IsShutdown": 1,
            },
            {
                "Id": "a-conflict",
                "OutFactoryCode": GOOD,
                "EquipCode": "GOOD001_sk",
                "AbnoCode": "O0006",
                "CreateTime": "2026-04-01 11:00:00",
                "Duration": 120,
                "DurationDetail": "40秒",
                "IsShutdown": 0,
            },
            {
                "Id": "a-leak",
                "OutFactoryCode": GOOD,
                "EquipCode": "OTHER_sk",
                "AbnoCode": "EMG",
                "CreateTime": "2026-04-01 12:00:00",
                "Duration": 0,
                "DurationDetail": "1秒",
                "IsShutdown": 1,
            },
        ],
        programs=[
            {
                "Id": "p-ok",
                "EquipCode": "GOOD001_sk",
                "ProgramCode": "O1.NC",
                "Output": 3,
                "OutputSumSecond": 90,
                "StartTime": "2026-04-01 08:00:00",
                "EndTime": "2026-04-01 09:00:00",
            },
            {
                "Id": "p-back",
                "EquipCode": "GOOD001_sk",
                "ProgramCode": "O2.NC",
                "Output": 1,
                "OutputSumSecond": 10,
                "StartTime": "2026-04-01 10:00:00",
                "EndTime": "2026-04-01 09:00:00",
            },
            {
                "Id": "p-mar",
                "EquipCode": "GOOD001_sk",
                "ProgramCode": "O3.NC",
                "Output": 9,
                "StartTime": "2026-03-10 08:00:00",
                "EndTime": "2026-03-10 09:00:00",
            },
            {
                "Id": "p-leak",
                "EquipCode": "OTHER_sk",
                "ProgramCode": "OX.NC",
                "Output": 99,
                "StartTime": "2026-04-01 08:00:00",
                "EndTime": "2026-04-01 09:00:00",
            },
        ],
        progress=[
            {
                "EquipProgramOutPutInDayId": "g-ok",
                "OutFactoryCode": GOOD,
                "EquipCode": "GOOD001_sk",
                "ProgramCode": "O1.NC",
                "StatisticalDateStr": "2026-04-01",
                "CreateTime": "2026-09-16 18:00:00",
                "Output": 8,
                "PlanOutput": 10,
                "ShiftStartTime": "2026-04-01 08:00:00",
                "ShiftEndTime": "2026-04-02 08:00:00",
                "ProcessingTimeSum": "1小时",
            },
            {
                "EquipProgramOutPutInDayId": "g-zero-plan",
                "OutFactoryCode": GOOD,
                "EquipCode": "GOOD001_sk",
                "ProgramCode": "O2.NC",
                "StatisticalDateStr": "2026-04-01",
                "CreateTime": "2026-09-16 18:00:00",
                "Output": 2,
                "PlanOutput": 0,
            },
            {
                "EquipProgramOutPutInDayId": "g-mar",
                "OutFactoryCode": GOOD,
                "EquipCode": "GOOD001_sk",
                "StatisticalDateStr": "2026-03-20",
                "Output": 5,
            },
            {
                "EquipProgramOutPutInDayId": "g-leak",
                "OutFactoryCode": GOOD,
                "EquipCode": "OTHER_sk",
                "StatisticalDateStr": "2026-04-01",
                "Output": 50,
            },
        ],
    )
    write_device(
        root,
        IDLE,
        equip_code="IDLE002_sk",
        etype="T-V856S",
        company=COMPANY_IDLE,
        run_rows=[
            run_day(IDLE, "IDLE002_sk", "T-V856S", "2026-03-31", 0, 86400),
            run_day(IDLE, "IDLE002_sk", "T-V856S", "2026-04-01", 0, 86400),
            run_day(IDLE, "IDLE002_sk", "T-V856S", "2026-04-02", 0, 86400),
            run_day(IDLE, "IDLE002_sk", "T-V856S", "2026-05-01", 100, 86300),
        ],
        alarms=[
            {
                "Id": "idle-apr",
                "OutFactoryCode": IDLE,
                "EquipCode": "IDLE002_sk",
                "AbnoCode": "M01",
                "CreateTime": "2026-04-01 09:00:00",
                "Duration": 0,
                "DurationDetail": "5秒",
                "IsShutdown": 1,
            }
        ],
        programs=[],
        progress=[],
    )
    write_device(
        root,
        BAD,
        equip_code="BAD003_sk",
        etype="T-600",
        company="co-bad",
        run_rows=[run_day(BAD, "BAD003_sk", "T-600", "2026-04-01", 1, 0)],
        alarms=[],
        programs=[],
        progress=[],
        info_rows=[],
    )
    dump(
        root / "_global" / "GetCustomerList.json",
        {
            "fetched_at": "2026-09-16T12:00:00",
            "rows": [
                {
                    "CustomerId": COMPANY_GOOD,
                    "CustomerName": "客户GOOD001",
                    "EnCode": "C1",
                    "AreaName": "华南区",
                    "FaultCount": 0,
                    "ProcessingCount": 1,
                    "IdleCount": 0,
                    "StandbyCount": 0,
                    "BoxDisconnectCount": 0,
                    "TotalEquipCount": 1,
                    "IsSummary": False,
                    "BootRate": 0.1,
                    "UtilRate": 0.2,
                },
                {
                    "CustomerId": "sum",
                    "CustomerName": "合计",
                    "IsSummary": True,
                    "TotalEquipCount": 99,
                },
                {
                    "CustomerId": "other",
                    "CustomerName": "外人",
                    "IsSummary": False,
                    "TotalEquipCount": 5,
                },
            ],
        },
    )
    master = {
        "records": [
            {"OutFactoryCode": GOOD, "EquipTypeCode": "T-600"},
            {"OutFactoryCode": IDLE, "EquipTypeCode": "T-600"},
            {"OutFactoryCode": BAD, "EquipTypeCode": "T-600"},
        ]
    }
    dump(tmp_path / "master.json", master)
    return tmp_path


def test_clean_fixture_pipeline(fixture_root: Path, tmp_path: Path):
    out = tmp_path / "processed"
    report = proc.run(
        root=fixture_root / "iot",
        master_path=fixture_root / "master.json",
        out_dir=out,
        days=4,
        write_catalog=False,
    )
    dim = pd.read_parquet(out / "device_dim.parquet")
    day = pd.read_parquet(out / "device_day.parquet")
    alarms = pd.read_parquet(out / "alarm_event.parquet")
    programs = pd.read_parquet(out / "program_cycle.parquet")
    progress = pd.read_parquet(out / "progress_day.parquet")
    spindle = pd.read_parquet(out / "spindle_asof.parquet")
    customers = pd.read_parquet(out / "customer_asof.parquet")
    rejected = [
        json.loads(line)
        for line in (out / "rejected" / "identity_mismatch.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]

    assert set(dim["out_factory_code"]) == {GOOD, IDLE}
    assert BAD not in set(dim["out_factory_code"])
    assert report["excluded_incomplete"][0]["out_factory_code"] == BAD
    assert "Ip" not in dim.columns and "SIMNo" not in dim.columns

    assert not day["date"].astype(str).str.startswith("2026-03").any()
    good_days = set(day.loc[day["out_factory_code"] == GOOD, "date"].astype(str))
    assert good_days == {"2026-04-01", "2026-04-02", "2026-05-01"}
    idle_days = set(day.loc[day["out_factory_code"] == IDLE, "date"].astype(str))
    assert idle_days == {"2026-05-01"}
    assert "2026-04-01" not in idle_days

    assert set(day["equip_type_code"]) == {"T-600", "T-V856S"}
    assert day["equip_type_code"].notna().all()
    assert "stop_time_sec" in day.columns
    assert not any("idle" in c.lower() or "停机" in c for c in day.columns)
    for col in ("label", "y", "is_fault", "split"):
        assert col not in day.columns
    assert "company_id" in day.columns
    april1 = day[(day["out_factory_code"] == GOOD) & (day["date"].astype(str) == "2026-04-01")].iloc[0]
    assert int(april1["is_run_day"]) == 1
    assert april1["run_hours"] == pytest.approx(1.0)
    assert int(april1["alarm_count"]) == 2
    assert int(april1["alarm_shutdown_count"]) == 1
    assert int(april1["program_cycle_count"]) == 4
    assert int(april1["progress_output"]) == 10

    assert set(alarms["alarm_id"]) == {"a-ok", "a-conflict", "idle-apr"}
    ok_alarm = alarms.loc[alarms["alarm_id"] == "a-ok"].iloc[0]
    assert int(ok_alarm["duration_sec"]) == 40
    conflict = alarms.loc[alarms["alarm_id"] == "a-conflict"].iloc[0]
    assert pd.isna(conflict["duration_sec"])
    assert "idle-apr" in set(alarms["alarm_id"])

    assert set(programs["program_id"]) == {"p-ok", "p-back"}
    assert (programs["out_factory_code"] == GOOD).all()

    assert set(progress["progress_id"]) == {"g-ok", "g-zero-plan"}
    planned = progress.loc[progress["progress_id"] == "g-ok"].iloc[0]
    assert planned["stat_date"] == "2026-04-01"
    assert planned["plan_achievement_pct"] == pytest.approx(80.0)
    zero_plan = progress.loc[progress["progress_id"] == "g-zero-plan"].iloc[0]
    assert pd.isna(zero_plan["plan_achievement_pct"])

    assert (spindle["as_of"].notna()).all()
    assert "as_of" in spindle.columns
    assert "date" not in spindle.columns

    assert set(customers["company_id"]) == {COMPANY_GOOD}
    assert "合计" not in set(customers["company_name"].astype(str))

    reasons = {row["reason"] for row in rejected}
    assert reasons == {"equip_code_mismatch"}
    assert {row["source_id"] for row in rejected} >= {"a-leak", "p-leak", "g-leak"}

    rule_ids = {row["rule_id"] for row in report["rules"]}
    assert "dropped_march" in rule_ids
    assert "dropped_idle_device_month" in rule_ids
    assert "duration_conflict" in rule_ids
    assert "equip_code_mismatch" in rule_ids
    assert "program_end_before_start" in rule_ids
    assert "excel_type_mismatch" in rule_ids
    assert set(report["uncovered_signals"]) >= {
        "跟随误差",
        "轴温",
        "冷却液",
        "液压",
        "振动",
        "保养台账",
        "换刀事件",
    }

    idle_excel = dim.loc[dim["out_factory_code"] == IDLE].iloc[0]
    assert idle_excel["excel_equip_type_code"] == "T-600"
    assert idle_excel["equip_type_code"] == "T-V856S"


def test_duration_zero_uses_detail():
    sec, conflict = proc.resolve_alarm_duration(0, "40秒")
    assert sec == 40 and conflict is False


def test_duration_conflict_clears_field():
    sec, conflict = proc.resolve_alarm_duration(120, "40秒")
    assert sec is None and conflict is True
