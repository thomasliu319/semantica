"""Compose additive IoT measures into derived ratios. No parquet required."""

from __future__ import annotations

import pandas as pd
import pytest

from semantica.explorer.iot_metrics import compose, stamp_metrics


def _day_frames() -> dict[str, pd.DataFrame]:
    day = pd.DataFrame(
        [
            {
                "out_factory_code": "A",
                "equip_type_code": "T-V856S",
                "company_id": "c1",
                "company_name": "客户一",
                "area_name": "华南区",
                "month": "2026-07",
                "run_hours": 10.0,
                "is_run_day": 1,
                "alarm_count": 20,
                "alarm_shutdown_count": 10,
                "program_cycle_count": 5,
                "program_seconds": 50,
                "progress_output": 5,
                "run_time_sec": 36000,
                "standby_time_sec": 0,
                "stop_time_sec": 0,
                "breakdown_time_sec": 0,
                "total_time_sec": 36000,
            },
            {
                "out_factory_code": "B",
                "equip_type_code": "T-600",
                "company_id": "c2",
                "company_name": "客户二",
                "area_name": "华东区",
                "month": "2026-07",
                "run_hours": 5.0,
                "is_run_day": 1,
                "alarm_count": 0,
                "alarm_shutdown_count": 0,
                "program_cycle_count": 2,
                "program_seconds": 20,
                "progress_output": 2,
                "run_time_sec": 18000,
                "standby_time_sec": 0,
                "stop_time_sec": 18000,
                "breakdown_time_sec": 0,
                "total_time_sec": 36000,
            },
            {
                "out_factory_code": "A",
                "equip_type_code": "T-V856S",
                "company_id": "c1",
                "company_name": "客户一",
                "area_name": "华南区",
                "month": "2026-08",
                "run_hours": 20.0,
                "is_run_day": 1,
                "alarm_count": 4,
                "alarm_shutdown_count": 4,
                "program_cycle_count": 10,
                "program_seconds": 100,
                "progress_output": 10,
                "run_time_sec": 72000,
                "standby_time_sec": 0,
                "stop_time_sec": 0,
                "breakdown_time_sec": 0,
                "total_time_sec": 72000,
            },
        ]
    )
    alarms = pd.DataFrame(
        [
            {"abno_code": "O0005", "equip_type_code": "T-V856S", "out_factory_code": "A", "is_shutdown": 1, "duration_sec": 30, "_one": 1},
            {"abno_code": "O0005", "equip_type_code": "T-V856S", "out_factory_code": "A", "is_shutdown": 0, "duration_sec": 10, "_one": 1},
            {"abno_code": "M01", "equip_type_code": "T-600", "out_factory_code": "B", "is_shutdown": 1, "duration_sec": 5, "_one": 1},
        ]
    )
    programs = pd.DataFrame(
        [
            {"program_code": "O100", "equip_type_code": "T-V856S", "out_factory_code": "A", "output": 8, "output_sum_second": 80},
            {"program_code": "O200", "equip_type_code": "T-600", "out_factory_code": "B", "output": 2, "output_sum_second": 40},
        ]
    )
    return {"device_day": day, "alarm_event": alarms, "program_cycle": programs}


def test_type_month_alarm_intensity_and_zero_div():
    result = compose(
        grain="type_month",
        bases=["run_hours", "alarm_count", "devices"],
        derived=[{"id": "alarm_per_run_hour", "op": "div", "a": "alarm_count", "b": "run_hours"}],
        apply_presets=False,
        frames=_day_frames(),
    )
    by_key = {(row["equip_type_code"], row["month"]): row for row in result["rows"]}
    assert by_key[("T-V856S", "2026-07")]["alarm_per_run_hour"] == 2.0
    assert by_key[("T-600", "2026-07")]["alarm_per_run_hour"] == 0
    assert by_key[("T-V856S", "2026-08")]["run_hours_share_of_month"] == 1.0


def test_custom_mul_and_share():
    result = compose(
        grain="equip_type",
        bases=["run_hours", "alarm_count"],
        derived=[
            {"id": "hours_times_alarms", "op": "mul", "a": "run_hours", "b": "alarm_count", "name_zh": "交叉"},
            {"id": "hours_share", "op": "share", "a": "run_hours"},
        ],
        apply_presets=False,
        frames=_day_frames(),
    )
    assert result["row_count"] == 2
    vmc = next(row for row in result["rows"] if row["equip_type_code"] == "T-V856S")
    drill = next(row for row in result["rows"] if row["equip_type_code"] == "T-600")
    assert vmc["hours_times_alarms"] == 720
    assert vmc["hours_share"] == 0.8571
    assert drill["hours_share"] == 0.1429


def test_rejects_oee_alias_and_unknown_grain():
    with pytest.raises(ValueError, match="invalid derived id"):
        compose(
            grain="month",
            bases=["run_hours", "alarm_count"],
            derived=[{"id": "fake_oee", "op": "div", "a": "run_hours", "b": "alarm_count"}],
            apply_presets=False,
            frames=_day_frames(),
        )
    with pytest.raises(ValueError, match="unknown grain"):
        compose(grain="fleet_kpi", apply_presets=False, frames=_day_frames())


def test_alarm_grain_ignores_device_day_bases():
    result = compose(
        grain="alarm_code",
        bases=[
            "run_hours",
            "run_days",
            "program_cycles",
            "alarm_count",
            "alarm_shutdown_count",
            "devices",
        ],
        derived=[{"id": "alarm_per_run_hour", "op": "div", "a": "alarm_count", "b": "run_hours"}],
        apply_presets=False,
        frames=_day_frames(),
    )
    assert "run_hours" not in result["bases"]
    assert result["bases"] == ["alarm_count", "alarm_shutdown_count", "devices"]
    assert result["derived"] == []
    assert result["row_count"] >= 1


def test_alarm_and_program_grains():
    frames = _day_frames()
    alarms = compose(grain="alarm_code", apply_presets=True, frames=frames, limit=10)
    o0005 = next(row for row in alarms["rows"] if row["abno_code"] == "O0005")
    assert o0005["alarm_count"] == 2
    assert o0005["shutdown_alarm_rate"] == 0.5
    assert o0005["alarm_duration_per_event"] == 20
    programs = compose(grain="program_code", apply_presets=True, frames=frames)
    o100 = next(row for row in programs["rows"] if row["program_code"] == "O100")
    assert o100["seconds_per_cycle"] == 10


def test_stamp_metrics_skips_share_and_null_div():
    stamped = stamp_metrics({"run_hours": 10, "alarm_count": 5, "run_days": 0, "devices": 2})
    assert stamped["alarm_per_run_hour"] == 0.5
    assert stamped.get("run_hours_per_run_day") is None
    assert "run_hours_share" not in stamped
