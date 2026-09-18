"""Compose additive IoT measures into derived ratios without inventing OEE labels.

Reads cleaned parquet under datasets/processed/iot_mar_aug_2026/.
Division by zero is null. Plan achievement is never fleet-averaged.
run_time_share is a four-bucket time structure ratio, not 客户近30天稼动率.
"""

from __future__ import annotations

import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
PROCESSED = REPO / "datasets" / "processed" / "iot_mar_aug_2026"
WINDOW = {"StartTime": "2026-04-01", "EndTime": "2026-08-31"}
_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,40}$")
_FORBIDDEN_ID = re.compile(r"(oee|is_fault|utilization_rate|稼动)", re.IGNORECASE)

OPS = ("div", "mul", "add", "sub", "share")

DEVICE_DAY_BASES: dict[str, tuple[str, str, str]] = {
    "run_hours": ("run_hours", "sum", "运行小时"),
    "run_days": ("is_run_day", "sum", "有运行日"),
    "devices": ("out_factory_code", "nunique", "设备台数"),
    "alarm_count": ("alarm_count", "sum", "报警条数"),
    "alarm_shutdown_count": ("alarm_shutdown_count", "sum", "停机报警条数"),
    "program_cycles": ("program_cycle_count", "sum", "循环次数"),
    "program_seconds": ("program_seconds", "sum", "循环秒"),
    "progress_output": ("progress_output", "sum", "日产量循环"),
    "run_time_sec": ("run_time_sec", "sum", "运行秒"),
    "standby_time_sec": ("standby_time_sec", "sum", "待机秒"),
    "stop_time_sec": ("stop_time_sec", "sum", "关机秒"),
    "breakdown_time_sec": ("breakdown_time_sec", "sum", "故障秒"),
    "total_time_sec": ("total_time_sec", "sum", "总秒"),
}

ALARM_BASES: dict[str, tuple[str, str, str]] = {
    "alarm_count": ("_one", "sum", "报警条数"),
    "alarm_shutdown_count": ("is_shutdown", "sum", "停机报警条数"),
    "alarm_duration_sec": ("duration_sec", "sum", "报警持续秒"),
    "devices": ("out_factory_code", "nunique", "设备台数"),
}

PROGRAM_BASES: dict[str, tuple[str, str, str]] = {
    "program_cycles": ("output", "sum", "循环次数"),
    "program_seconds": ("output_sum_second", "sum", "循环秒"),
    "devices": ("out_factory_code", "nunique", "设备台数"),
}

GRAINS: dict[str, dict[str, Any]] = {
    "type_month": {
        "label_zh": "机型 × 月",
        "source": "device_day",
        "keys": ["equip_type_code", "month"],
        "features": "机型在自然月的运行强度、报警密度、四桶时间结构",
    },
    "month": {
        "label_zh": "自然月",
        "source": "device_day",
        "keys": ["month"],
        "features": "窗口内月趋势；4 月冷启动，8 月运行抬升",
    },
    "equip_type": {
        "label_zh": "机型",
        "source": "device_day",
        "keys": ["equip_type_code"],
        "features": "T-V856S 立加 vs T-600 钻攻的结构差，不是故障标签",
    },
    "equip": {
        "label_zh": "设备",
        "source": "device_day",
        "keys": ["out_factory_code", "equip_type_code", "company_id"],
        "features": "单台加总；运行小时可分高/中/低运行带",
    },
    "customer": {
        "label_zh": "客户",
        "source": "device_day",
        "keys": ["company_id"],
        "features": "切分键 company_id；同厂多机对比，禁止舰队平均计划达成率",
    },
    "area": {
        "label_zh": "区域",
        "source": "device_day",
        "keys": ["area_name"],
        "features": "华南/华东等；空区域单独成组，不是仓库维度",
    },
    "alarm_code": {
        "label_zh": "报警号 × 机型",
        "source": "alarm_event",
        "keys": ["abno_code", "equip_type_code"],
        "features": "O0005 是否只打在立加；停机报警条数不是故障秒",
    },
    "program_code": {
        "label_zh": "程序号 × 机型",
        "source": "program_cycle",
        "keys": ["program_code", "equip_type_code"],
        "features": "换产/重复加工；单次循环秒 = 循环秒 / 循环次数",
    },
}

DEVICE_DAY_NAMED = {key: (col, how) for key, (col, how, _zh) in DEVICE_DAY_BASES.items()}

PRESETS: list[dict[str, Any]] = [
    {
        "id": "alarm_per_run_hour",
        "op": "div",
        "a": "alarm_count",
        "b": "run_hours",
        "name_zh": "每运行小时报警",
        "not": "故障率 / OEE",
        "domain": "alarm",
    },
    {
        "id": "shutdown_alarm_rate",
        "op": "div",
        "a": "alarm_shutdown_count",
        "b": "alarm_count",
        "name_zh": "停机报警占比",
        "not": "故障时长占比",
        "domain": "alarm",
    },
    {
        "id": "run_hours_per_run_day",
        "op": "div",
        "a": "run_hours",
        "b": "run_days",
        "name_zh": "有运行日均运行小时",
        "not": "开机率",
        "domain": "cnc_run",
    },
    {
        "id": "run_hours_per_device",
        "op": "div",
        "a": "run_hours",
        "b": "devices",
        "name_zh": "单台运行小时",
        "not": "客户近30天稼动率",
        "domain": "cnc_run",
    },
    {
        "id": "cycles_per_run_hour",
        "op": "div",
        "a": "program_cycles",
        "b": "run_hours",
        "name_zh": "每运行小时循环",
        "not": "计划达成率",
        "domain": "program",
    },
    {
        "id": "seconds_per_cycle",
        "op": "div",
        "a": "program_seconds",
        "b": "program_cycles",
        "name_zh": "单次循环秒",
        "domain": "program",
    },
    {
        "id": "alarm_per_device",
        "op": "div",
        "a": "alarm_count",
        "b": "devices",
        "name_zh": "单台报警条数",
        "domain": "alarm",
    },
    {
        "id": "run_time_share",
        "op": "div",
        "a": "run_time_sec",
        "b": "total_time_sec",
        "name_zh": "运行时间结构占比",
        "not": "客户近30天稼动率",
        "domain": "cnc_run",
    },
    {
        "id": "standby_time_share",
        "op": "div",
        "a": "standby_time_sec",
        "b": "total_time_sec",
        "name_zh": "待机时间结构占比",
        "not": "停机",
        "domain": "cnc_run",
    },
    {
        "id": "stop_time_share",
        "op": "div",
        "a": "stop_time_sec",
        "b": "total_time_sec",
        "name_zh": "关机时间结构占比",
        "not": "停机",
        "domain": "cnc_run",
    },
    {
        "id": "breakdown_time_share",
        "op": "div",
        "a": "breakdown_time_sec",
        "b": "total_time_sec",
        "name_zh": "故障时间结构占比",
        "not": "停机报警占比",
        "domain": "cnc_run",
    },
    {
        "id": "run_hours_share",
        "op": "share",
        "a": "run_hours",
        "b": None,
        "name_zh": "运行小时舰队份额",
        "not": "稼动率",
        "domain": "cnc_run",
    },
    {
        "id": "alarm_duration_per_event",
        "op": "div",
        "a": "alarm_duration_sec",
        "b": "alarm_count",
        "name_zh": "单条报警持续秒",
        "domain": "alarm",
    },
    {
        "id": "alarm_count_share",
        "op": "share",
        "a": "alarm_count",
        "b": None,
        "name_zh": "报警条数份额",
        "domain": "alarm",
    },
    {
        "id": "cycles_share",
        "op": "share",
        "a": "program_cycles",
        "b": None,
        "name_zh": "循环次数份额",
        "domain": "program",
    },
]

INT_KEYS = {
    "alarm_count",
    "alarm_shutdown_count",
    "program_cycles",
    "run_days",
    "devices",
    "progress_output",
    "run_time_sec",
    "standby_time_sec",
    "stop_time_sec",
    "breakdown_time_sec",
    "total_time_sec",
    "program_seconds",
    "alarm_duration_sec",
}
HOUR_KEYS = {"run_hours"}
NOTES = [
    "B1 clean_only：派生度量，不是监督标签，不叫 OEE，不造 is_fault",
    "关机时间 ≠ 停机；停机只来自 IsShutdown / IdleCount",
    "运行时间结构占比 ≠ 客户列表近30天稼动率",
    "计划达成率只在 plan_output 非空非 0 的进度行计算，禁止舰队平均",
]


def catalog() -> dict[str, Any]:
    bases_by_source = {
        "device_day": [_base_entry(k, v) for k, v in DEVICE_DAY_BASES.items()],
        "alarm_event": [_base_entry(k, v) for k, v in ALARM_BASES.items()],
        "program_cycle": [_base_entry(k, v) for k, v in PROGRAM_BASES.items()],
    }
    grains = []
    for gid, spec in GRAINS.items():
        grains.append(
            {
                "id": gid,
                "label_zh": spec["label_zh"],
                "source": spec["source"],
                "keys": list(spec["keys"]),
                "features": spec["features"],
                "bases": [row["id"] for row in bases_by_source[spec["source"]]],
            }
        )
    return {
        "window": WINDOW,
        "grains": grains,
        "bases_by_source": bases_by_source,
        "presets": PRESETS,
        "ops": list(OPS),
        "notes": NOTES,
    }


def stamp_metrics(bases: Mapping[str, Any], *, extra: Sequence[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Round additive totals and attach ratio presets. Skip share (needs a cohort)."""
    payload = {key: _finite(value) for key, value in bases.items()}
    frame = pd.DataFrame([payload])
    recipes = [item for item in PRESETS if item["op"] != "share"] + list(extra or [])
    apply_derived(frame, recipes)
    row = frame.iloc[0].to_dict()
    return {key: _json_num(key, value) for key, value in row.items() if _finite(value) is not None}


def compose(
    *,
    grain: str,
    bases: Sequence[str] | None = None,
    derived: Sequence[Mapping[str, Any]] | None = None,
    apply_presets: bool = True,
    limit: int = 200,
    frames: dict[str, pd.DataFrame] | None = None,
) -> dict[str, Any]:
    spec = GRAINS.get(grain)
    if spec is None:
        raise ValueError(f"unknown grain: {grain}")
    if limit < 1 or limit > 500:
        raise ValueError("limit must be 1..500")

    source = spec["source"]
    available = _bases_for(source)
    requested = list(bases) if bases is not None else list(available)
    selected = [item for item in requested if item in available]
    if not selected:
        selected = list(available)

    usable_derived = []
    for item in derived or []:
        left = str(item.get("a") or "").strip()
        op = str(item.get("op") or "").strip()
        right = item.get("b")
        right_s = str(right).strip() if right not in (None, "") else None
        if left not in selected:
            continue
        if op != "share" and (not right_s or right_s not in selected):
            continue
        usable_derived.append(item)
    recipes = _validated_derived(usable_derived, selected)
    if apply_presets:
        recipes = _merge_recipes(recipes, [item for item in PRESETS if item["a"] in selected and (item["op"] == "share" or item.get("b") in selected)])

    table = (frames or load_tables())[source]
    keys = list(spec["keys"])
    grouped = _aggregate(table, keys, selected, available)
    apply_derived(grouped, recipes)
    if grain == "month" and "run_hours" in grouped.columns:
        grouped = grouped.sort_values("month")
        prev = grouped["run_hours"].shift(1)
        grouped["run_hours_mom"] = _ratio(grouped["run_hours"] - prev, prev)
    if grain == "type_month" and "run_hours" in grouped.columns:
        month_total = grouped.groupby("month")["run_hours"].transform("sum")
        grouped["run_hours_share_of_month"] = _ratio(grouped["run_hours"], month_total)

    if grain != "month":
        sort_col = _sort_column(grouped, recipes, selected)
        if sort_col:
            grouped = grouped.sort_values(sort_col, ascending=False, na_position="last")
    grouped = grouped.head(limit)

    columns = keys + selected + [item["id"] for item in recipes]
    if "company_name" in grouped.columns:
        columns = keys + ["company_name"] + selected + [item["id"] for item in recipes]
    if grain == "month" and "run_hours_mom" in grouped.columns:
        columns.append("run_hours_mom")
    if grain == "type_month" and "run_hours_share_of_month" in grouped.columns:
        columns.append("run_hours_share_of_month")
    columns = list(dict.fromkeys(col for col in columns if col in grouped.columns))

    rows = []
    for record in grouped[columns].to_dict(orient="records"):
        rows.append({key: _json_num(key, value) for key, value in record.items()})
    return {
        "grain": grain,
        "label_zh": spec["label_zh"],
        "features": spec["features"],
        "keys": keys,
        "bases": selected,
        "derived": recipes,
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "notes": NOTES,
    }


@lru_cache(maxsize=1)
def load_tables() -> dict[str, pd.DataFrame]:
    if not (PROCESSED / "device_day.parquet").is_file():
        raise FileNotFoundError(str(PROCESSED))
    dim = pd.read_parquet(PROCESSED / "device_dim.parquet")
    day = pd.read_parquet(PROCESSED / "device_day.parquet")
    extra = dim[["out_factory_code", "area_name", "company_name"]].drop_duplicates("out_factory_code")
    day = day.merge(extra, on="out_factory_code", how="left")
    day["area_name"] = day["area_name"].fillna("空").replace("", "空")
    day["company_id"] = day["company_id"].fillna("未知客户")
    alarms = pd.read_parquet(PROCESSED / "alarm_event.parquet").assign(_one=1)
    alarms["abno_code"] = alarms["abno_code"].fillna("未知").replace("", "未知")
    programs = pd.read_parquet(PROCESSED / "program_cycle.parquet")
    programs["program_code"] = programs["program_code"].fillna("未知程序").replace("", "未知程序")
    return {"device_day": day, "alarm_event": alarms, "program_cycle": programs, "device_dim": dim}


def apply_derived(frame: pd.DataFrame, recipes: Iterable[Mapping[str, Any]]) -> pd.DataFrame:
    for recipe in recipes:
        op = recipe["op"]
        name = recipe["id"]
        left = recipe["a"]
        right = recipe.get("b")
        if left not in frame.columns:
            continue
        if op == "share":
            frame[name] = _ratio(frame[left], frame[left].sum())
            continue
        if not right or right not in frame.columns:
            continue
        if op == "div":
            frame[name] = _ratio(frame[left], frame[right])
        elif op == "mul":
            frame[name] = frame[left] * frame[right]
        elif op == "add":
            frame[name] = frame[left] + frame[right]
        elif op == "sub":
            frame[name] = frame[left] - frame[right]
    return frame


def _aggregate(
    table: pd.DataFrame,
    keys: list[str],
    selected: Sequence[str],
    available: dict[str, tuple[str, str, str]],
) -> pd.DataFrame:
    named: dict[str, tuple[str, str]] = {}
    work = table
    if any(available[item][0] == "_one" for item in selected):
        work = table.assign(_one=1) if "_one" not in table.columns else table
    for measure in selected:
        column, how, _label = available[measure]
        named[measure] = (column, how)
    grouped = work.groupby(keys, dropna=False, as_index=False).agg(**named)
    if "company_id" in keys and "company_name" in work.columns and "company_name" not in grouped.columns:
        names = work.groupby("company_id", dropna=False)["company_name"].agg(
            lambda values: next((str(v) for v in values if pd.notna(v) and str(v).strip()), "未知客户")
        )
        grouped = grouped.merge(names.rename("company_name"), on="company_id", how="left")
    return grouped


def _bases_for(source: str) -> dict[str, tuple[str, str, str]]:
    if source == "device_day":
        return DEVICE_DAY_BASES
    if source == "alarm_event":
        return ALARM_BASES
    if source == "program_cycle":
        return PROGRAM_BASES
    raise ValueError(f"unknown source: {source}")


def _base_entry(measure_id: str, spec: tuple[str, str, str]) -> dict[str, str]:
    _column, how, name_zh = spec
    return {"id": measure_id, "name_zh": name_zh, "agg": how}


def _validated_derived(raw: Sequence[Mapping[str, Any]], selected: Sequence[str]) -> list[dict[str, Any]]:
    recipes: list[dict[str, Any]] = []
    seen = set(selected)
    for item in raw:
        recipe_id = str(item.get("id") or "").strip()
        op = str(item.get("op") or "").strip()
        left = str(item.get("a") or "").strip()
        right = item.get("b")
        right_s = str(right).strip() if right not in (None, "") else None
        if not _ID_RE.match(recipe_id) or _FORBIDDEN_ID.search(recipe_id):
            raise ValueError(f"invalid derived id: {recipe_id}")
        if recipe_id in seen:
            raise ValueError(f"derived id collides: {recipe_id}")
        if op not in OPS:
            raise ValueError(f"invalid op: {op}")
        if left not in selected:
            raise ValueError(f"derived operand not in bases: {left}")
        if op != "share" and (not right_s or right_s not in selected):
            raise ValueError(f"derived operand not in bases: {right_s}")
        seen.add(recipe_id)
        recipes.append(
            {
                "id": recipe_id,
                "op": op,
                "a": left,
                "b": right_s,
                "name_zh": str(item.get("name_zh") or recipe_id),
                "not": item.get("not"),
                "domain": item.get("domain"),
            }
        )
    return recipes


def _merge_recipes(custom: list[dict[str, Any]], presets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = {item["id"] for item in custom}
    merged = list(custom)
    for item in presets:
        if item["id"] in seen:
            continue
        merged.append(item)
        seen.add(item["id"])
    return merged


def _sort_column(frame: pd.DataFrame, recipes: Sequence[Mapping[str, Any]], selected: Sequence[str]) -> str | None:
    for recipe in recipes:
        if recipe["id"] in frame.columns:
            return recipe["id"]
    for measure in selected:
        if measure in frame.columns:
            return measure
    return None


def _ratio(numerator: pd.Series, denominator: Any) -> pd.Series:
    num = pd.to_numeric(numerator, errors="coerce")
    if isinstance(denominator, pd.Series):
        den = pd.to_numeric(denominator, errors="coerce")
        return num / den.replace(0, pd.NA)
    try:
        den_v = float(denominator)
    except (TypeError, ValueError):
        return pd.Series([pd.NA] * len(num), index=num.index)
    if den_v == 0 or not math.isfinite(den_v):
        return pd.Series([pd.NA] * len(num), index=num.index)
    return num / den_v


def _finite(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _json_num(key: str, value: Any) -> Any:
    value = _finite(value)
    if value is None:
        return None
    if isinstance(value, str):
        return value
    number = float(value)
    if key in INT_KEYS:
        return int(round(number))
    if key in HOUR_KEYS:
        return round(number, 1)
    if abs(number - round(number)) < 1e-9 and abs(number) >= 1:
        return int(round(number))
    return round(number, 4)
