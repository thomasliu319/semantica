"""Fetch MES/PdM OpenAPI rows for each Excel device, Mar–Aug 2026.

Writes one folder per OutFactoryCode under datasets/json/iot_timeseries/.
Resumable: existing complete JSON files are skipped.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import ssl
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from http.client import IncompleteRead, RemoteDisconnected
from pathlib import Path
from threading import Lock, Semaphore

BASE_URL = "https://iotdev.szccm.com:9991"
DEFAULT_CUSTOMER_ID = "21e224c9-2bb7-4c40-9815-8250916a4831"
START = date(2026, 3, 1)
END = date(2026, 8, 31)
PAGE_SIZE = 500
MAX_PAGES = 80
RETRIES = 8
SECRET_KEYS = {"secretKey", "SecretKey", "secret_key"}

ROOT = Path(__file__).resolve().parent / "json" / "iot_timeseries"
MASTER_PATH = Path(__file__).resolve().parent / "json" / "source" / "equip_master_200.json"

SSL_CTX = ssl.create_default_context()
PRINT_LOCK = Lock()
BOOT_CACHE: dict[str, dict] = {}
BOOT_LOCK = Lock()
PAGE_GATE = Semaphore(8)
TRANSIENT = (
    urllib.error.URLError,
    TimeoutError,
    json.JSONDecodeError,
    ConnectionResetError,
    ConnectionError,
    RemoteDisconnected,
    IncompleteRead,
    ssl.SSLError,
)
REQUIRED_FILES = (
    "GetEquipInfoPageList.json",
    "GetEquipSpindleWithFeedData.json",
    "GetEquipRunStatusList.json",
    "GetEquipAbnorPageList.json",
    "GetEquipProgramPageList.json",
    "GetEquipProductionProgressPageList.json",
    "GetEquipBootOrRunningTimeList.json",
    "trend_summary.json",
    "meta.json",
)


def log(msg: str) -> None:
    with PRINT_LOCK:
        print(msg, flush=True)


def daterange(start: date, end: date) -> list[date]:
    days = []
    cur = start
    while cur <= end:
        days.append(cur)
        cur += timedelta(days=1)
    return days


def duration_to_seconds(text: object) -> int | None:
    if text is None:
        return None
    raw = str(text).strip()
    if raw in {"", "-", "null"}:
        return None
    if raw in {"0", "0秒"}:
        return 0
    days = hours = minutes = seconds = 0
    found = False
    for pattern, dest in (
        (r"(\d+)\s*天", "days"),
        (r"(\d+)\s*小时", "hours"),
        (r"(\d+)\s*分钟", "minutes"),
        (r"(\d+)\s*秒", "seconds"),
    ):
        match = re.search(pattern, raw)
        if match:
            found = True
            value = int(match.group(1))
            if dest == "days":
                days = value
            elif dest == "hours":
                hours = value
            elif dest == "minutes":
                minutes = value
            else:
                seconds = value
    if found:
        return days * 86400 + hours * 3600 + minutes * 60 + seconds
    try:
        return int(float(raw))
    except ValueError:
        return None


def parse_pct(text: object) -> float | None:
    if text is None:
        return None
    raw = str(text).strip().replace("%", "")
    if raw in {"", "-"}:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def strip_secrets(obj):
    if isinstance(obj, dict):
        return {k: strip_secrets(v) for k, v in obj.items() if k not in SECRET_KEYS}
    if isinstance(obj, list):
        return [strip_secrets(v) for v in obj]
    return obj


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def post(path: str, body: dict, timeout: int = 90) -> dict:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    last_error = None
    for attempt in range(1, RETRIES + 1):
        req = urllib.request.Request(
            BASE_URL + path,
            data=data,
            method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            obj = json.loads(raw)
            return strip_secrets(obj)
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = " ".join(exc.read().decode("utf-8", errors="replace").split())[:120]
            except Exception:
                detail = str(exc)
            last_error = RuntimeError(f"{path} HTTP {exc.code} {detail}".strip()[:180])
            if exc.code >= 500 and attempt < 3:
                time.sleep(min(2 ** attempt, 8))
                continue
            raise last_error
        except TRANSIENT as exc:
            last_error = exc
            time.sleep(min(2 ** attempt, 20))
    raise RuntimeError(f"{path} failed after {RETRIES} retries: {last_error}")


def result_rows(envelope: dict) -> list:
    rd = envelope.get("ResultData")
    if isinstance(rd, dict) and isinstance(rd.get("rows"), list):
        return rd["rows"]
    return []


def paginate(path: str, body: dict, *, page_size: int = PAGE_SIZE) -> dict:
    with PAGE_GATE:
        return _paginate(path, body, page_size=page_size)


def _paginate(path: str, body: dict, *, page_size: int = PAGE_SIZE) -> dict:
    rows: list = []
    page = 1
    records = None
    pages_meta = []
    while page <= MAX_PAGES:
        payload = dict(body)
        payload["page"] = page
        payload["rows"] = page_size
        envelope = post(path, payload)
        chunk = result_rows(envelope)
        rd = envelope.get("ResultData") if isinstance(envelope.get("ResultData"), dict) else {}
        records = rd.get("records", records)
        pages_meta.append(
            {
                "page": page,
                "returned": len(chunk),
                "records": rd.get("records"),
                "total": rd.get("total"),
                "IsSuccess": envelope.get("IsSuccess"),
                "Message": envelope.get("Message"),
            }
        )
        rows.extend(chunk)
        if not chunk or len(chunk) < page_size:
            break
        if isinstance(records, int) and len(rows) >= records:
            break
        page += 1
    return {
        "api": path,
        "query": {k: v for k, v in body.items() if k not in {"page", "rows"}},
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "record_count": len(rows),
        "declared_records": records,
        "pages": pages_meta,
        "rows": rows,
    }


def month_windows(start: date, end: date) -> list[tuple[date, date]]:
    windows = []
    cur = date(start.year, start.month, 1)
    while cur <= end:
        if cur.month == 12:
            nxt = date(cur.year + 1, 1, 1)
        else:
            nxt = date(cur.year, cur.month + 1, 1)
        win_start = max(cur, start)
        win_end = min(end, nxt - timedelta(days=1))
        windows.append((win_start, win_end))
        cur = nxt
    return windows


def week_windows(start: date, end: date) -> list[tuple[date, date]]:
    windows = []
    cur = start
    while cur <= end:
        win_end = min(end, cur + timedelta(days=6))
        windows.append((cur, win_end))
        cur = win_end + timedelta(days=1)
    return windows


def paginate_range(path: str, body: dict, start: date, end: date, *, dest: Path | None = None, page_size: int = 20) -> dict:
    rows: list = []
    pages_meta: list = []
    chunks: list = []
    done: set[tuple[str, str]] = set()
    if dest and dest.exists():
        try:
            prev = load_json(dest)
        except Exception:
            prev = {}
        if prev.get("api") == path:
            rows = list(prev.get("rows") or [])
            pages_meta = list(prev.get("pages") or [])
            chunks = list(prev.get("chunks") or [])
            done = {
                (str(chunk.get("StartTime")), str(chunk.get("EndTime")))
                for chunk in chunks
                if chunk.get("ok")
            }

    def persist(partial: bool) -> dict:
        payload = {
            "api": path,
            "query": {k: v for k, v in body.items() if k not in {"page", "rows", "StartTime", "EndTime"}},
            "range": {"StartTime": start.isoformat(), "EndTime": end.isoformat()},
            "chunked": "adaptive",
            "partial": partial,
            "chunks": chunks,
            "fetched_at": datetime.now().isoformat(timespec="seconds"),
            "record_count": len(rows),
            "pages": pages_meta,
            "rows": rows,
        }
        if dest:
            write_json(dest, payload)
        return payload

    def fetch_window(win_start: date, win_end: date, sizes: tuple[int, ...] = (20, 10, 5)) -> bool:
        key = (win_start.isoformat(), win_end.isoformat())
        if key in done:
            return True
        payload = dict(body)
        payload["StartTime"] = win_start.isoformat()
        payload["EndTime"] = win_end.isoformat()
        last_exc = None
        tried: list[int] = []
        for size in sizes:
            if size in tried:
                continue
            tried.append(size)
            try:
                part = paginate(path, payload, page_size=size)
                rows.extend(part.get("rows") or [])
                pages_meta.extend(part.get("pages") or [])
                chunks.append(
                    {
                        "StartTime": win_start.isoformat(),
                        "EndTime": win_end.isoformat(),
                        "record_count": part.get("record_count"),
                        "page_size": size,
                        "ok": True,
                    }
                )
                done.add(key)
                persist(True)
                return True
            except Exception as exc:
                last_exc = exc
                log(f"    retry {path} {win_start}..{win_end} page_size={size}: {exc}")
        chunks.append(
            {
                "StartTime": win_start.isoformat(),
                "EndTime": win_end.isoformat(),
                "ok": False,
                "error": str(last_exc)[:200] if last_exc else "failed",
            }
        )
        persist(True)
        return False

    failed_months: list[tuple[date, date]] = []
    for win_start, win_end in month_windows(start, end):
        if fetch_window(win_start, win_end, (page_size,)):
            continue
        failed_months.append((win_start, win_end))

    leftover: list[tuple[date, date]] = []
    for win_start, win_end in failed_months:
        week_ok = True
        for week_start, week_end in week_windows(win_start, win_end):
            if not fetch_window(week_start, week_end, (page_size, 10)):
                week_ok = False
                leftover.append((week_start, week_end))
        if week_ok:
            log(f"    recovered {path} {win_start} by week windows")

    still_failed: list[str] = []
    for win_start, win_end in leftover:
        day_ok = True
        for day in daterange(win_start, win_end):
            if not fetch_window(day, day, (page_size, 10, 5)):
                day_ok = False
                still_failed.append(day.isoformat())
        if day_ok:
            log(f"    recovered {path} {win_start}..{win_end} by day windows")

    payload = persist(bool(still_failed))
    if still_failed:
        raise RuntimeError(f"{path} failed days={still_failed[:8]}{'...' if len(still_failed) > 8 else ''}")
    payload["partial"] = False
    if dest:
        write_json(dest, payload)
    return payload


def paginate_months(path: str, body: dict, start: date, end: date, *, page_size: int = 100) -> dict:
    return paginate_range(path, body, start, end, page_size=page_size)


def fetch_info(out_factory: str) -> dict:
    queries = [
        {"CustomerId": DEFAULT_CUSTOMER_ID, "OutFactoryCode": out_factory, "EquipCode": ""},
        {"CustomerId": "", "OutFactoryCode": out_factory, "EquipCode": ""},
        {"CustomerId": DEFAULT_CUSTOMER_ID, "OutFactoryCode": "", "EquipCode": out_factory},
        {"CustomerId": "", "OutFactoryCode": "", "EquipCode": out_factory},
    ]
    last: dict | None = None
    for query in queries:
        envelope = post(
            "/OpenApi/GetEquipInfoPageList",
            {
                "page": 1,
                "rows": 20,
                "CompanyName": "",
                "EquipName": "",
                "GwCode": "",
                "SIMNo": "",
                "EquipTypeName": "",
                "AreaName": "",
                **query,
            },
        )
        rows = result_rows(envelope)
        last = {
            "api": "/OpenApi/GetEquipInfoPageList",
            "query": query,
            "fetched_at": datetime.now().isoformat(timespec="seconds"),
            "IsSuccess": envelope.get("IsSuccess"),
            "Message": envelope.get("Message"),
            "record_count": len(rows),
            "rows": rows,
        }
        if rows:
            return last
    return last or {
        "api": "/OpenApi/GetEquipInfoPageList",
        "query": {"OutFactoryCode": out_factory},
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "record_count": 0,
        "rows": [],
    }


def fetch_spindle(out_factory: str, company_id: str, equip_code: str) -> dict:
    envelope = post(
        "/OpenApi/GetEquipSpindleWithFeedData",
        {
            "OutFactoryCode": out_factory,
            "EquipName": "",
            "GwCode": "",
            "CompanyId": company_id or DEFAULT_CUSTOMER_ID,
            "EquipCode": equip_code or "",
        },
    )
    return {
        "api": "/OpenApi/GetEquipSpindleWithFeedData",
        "query": {"OutFactoryCode": out_factory, "EquipCode": equip_code, "CompanyId": company_id},
        "note": "API is a live snapshot; historical telemetry is not queryable by date.",
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "IsSuccess": envelope.get("IsSuccess"),
        "Message": envelope.get("Message"),
        "Timestamp": envelope.get("Timestamp"),
        "ResultData": envelope.get("ResultData"),
    }


def fetch_run_status(out_factory: str, company_id: str, days: list[date], dest: Path) -> dict:
    existing = {}
    if dest.exists():
        prev = load_json(dest)
        for row in prev.get("rows") or []:
            day = row.get("date")
            if day:
                existing[day] = row
    rows = []
    errors = []
    for day in days:
        key = day.isoformat()
        if key in existing and existing[key].get("ok"):
            rows.append(existing[key])
            continue
        try:
            envelope = post(
                "/OpenApi/GetEquipRunStatusList",
                {
                    "page": 1,
                    "rows": 10,
                    "currentDate": key,
                    "companyId": company_id or DEFAULT_CUSTOMER_ID,
                    "outFactoryCode": out_factory,
                    "equipName": "",
                },
                timeout=45,
            )
            day_rows = result_rows(envelope)
            item = day_rows[0] if day_rows else {}
            rows.append(
                {
                    "date": key,
                    "ok": True,
                    "IsSuccess": envelope.get("IsSuccess"),
                    "Message": envelope.get("Message"),
                    **item,
                    "RunTimeSec": duration_to_seconds(item.get("RunTime")),
                    "StandbyTimeSec": duration_to_seconds(item.get("StandbyTime")),
                    "StopTimeSec": duration_to_seconds(item.get("StopTime")),
                    "BreakDownTimeSec": duration_to_seconds(item.get("BreakDownTime")),
                    "TotalTimeSec": duration_to_seconds(item.get("TotalTime")),
                    "RunTimeRatePct": parse_pct(item.get("RunTimeRate")),
                    "StandbyTimeRatePct": parse_pct(item.get("StandbyTimeRate")),
                    "StopTimeRatePct": parse_pct(item.get("StopTimeRate")),
                    "BreakDownTimeRatePct": parse_pct(item.get("BreakDownTimeRate")),
                }
            )
        except Exception as exc:
            errors.append({"date": key, "error": str(exc)})
            rows.append({"date": key, "ok": False, "error": str(exc)})
        if len(rows) % 31 == 0:
            write_json(
                dest,
                {
                    "api": "/OpenApi/GetEquipRunStatusList",
                    "query": {"outFactoryCode": out_factory, "companyId": company_id},
                    "partial": True,
                    "rows": rows,
                },
            )
    payload = {
        "api": "/OpenApi/GetEquipRunStatusList",
        "query": {
            "outFactoryCode": out_factory,
            "companyId": company_id,
            "StartTime": days[0].isoformat(),
            "EndTime": days[-1].isoformat(),
        },
        "note": "API is daily; StartTime/EndTime are not honored. Fetched one currentDate per day.",
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "record_count": len(rows),
        "ok_days": sum(1 for r in rows if r.get("ok")),
        "errors": errors,
        "rows": rows,
    }
    write_json(dest, payload)
    return payload


def fetch_boot(company_id: str, start: date, end: date) -> dict:
    key = company_id or DEFAULT_CUSTOMER_ID
    with BOOT_LOCK:
        cached = BOOT_CACHE.get(key)
        if cached is not None:
            return cached
    payload = paginate(
        "/OpenApi/GetEquipBootOrRunningTimeList",
        {
            "customerIdList": [key] if key else [],
            "equipTypeId": "",
            "areaName": "",
            "province": "",
            "city": "",
            "StartTime": start.isoformat(),
            "EndTime": end.isoformat(),
            "IsReverseOrder": 1,
            "CustomerId": DEFAULT_CUSTOMER_ID,
        },
        page_size=20,
    )
    payload["note"] = "Customer-level aggregate for the device's CompanyId, not a per-machine series."
    with BOOT_LOCK:
        BOOT_CACHE[key] = payload
    return payload


def monthly_bucket(stamp: str | None) -> str | None:
    if not stamp:
        return None
    return str(stamp)[:7]


def build_trend(out_factory: str, start: date, end: date, files: dict[str, dict]) -> dict:
    months = []
    cur = date(start.year, start.month, 1)
    while cur <= end:
        months.append(f"{cur.year:04d}-{cur.month:02d}")
        if cur.month == 12:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = date(cur.year, cur.month + 1, 1)

    monthly = {
        m: {
            "alarm_count": 0,
            "shutdown_alarm_count": 0,
            "program_cycles": 0,
            "program_seconds": 0,
            "progress_output": 0,
            "progress_seconds": 0,
            "run_ok_days": 0,
            "run_seconds": 0,
            "standby_seconds": 0,
            "stop_seconds": 0,
            "breakdown_seconds": 0,
            "avg_run_rate_pct": None,
        }
        for m in months
    }

    for row in (files.get("alarms") or {}).get("rows") or []:
        month = monthly_bucket(row.get("CreateTime"))
        if month not in monthly:
            continue
        monthly[month]["alarm_count"] += 1
        if row.get("IsShutdown") == 1:
            monthly[month]["shutdown_alarm_count"] += 1

    for row in (files.get("program") or {}).get("rows") or []:
        month = monthly_bucket(row.get("StartTime"))
        if month not in monthly:
            continue
        monthly[month]["program_cycles"] += int(row.get("Output") or 0)
        monthly[month]["program_seconds"] += int(row.get("OutputSumSecond") or 0)

    daily_progress = []
    for row in (files.get("progress") or {}).get("rows") or []:
        day = row.get("StatisticalDateStr") or str(row.get("StatisticalDate") or "")[:10]
        month = monthly_bucket(day)
        output = int(row.get("Output") or 0)
        seconds = int(row.get("OutputSumSecond") or 0)
        daily_progress.append(
            {
                "date": day,
                "ProgramCode": row.get("ProgramCode"),
                "Output": output,
                "OutputSumSecond": seconds,
                "PlanOutput": row.get("PlanOutput"),
            }
        )
        if month in monthly:
            monthly[month]["progress_output"] += output
            monthly[month]["progress_seconds"] += seconds

    daily_run = []
    rate_acc: dict[str, list[float]] = {m: [] for m in months}
    for row in (files.get("run_status") or {}).get("rows") or []:
        day = row.get("date")
        month = monthly_bucket(day)
        compact = {
            "date": day,
            "ok": row.get("ok"),
            "RunTimeSec": row.get("RunTimeSec"),
            "StandbyTimeSec": row.get("StandbyTimeSec"),
            "StopTimeSec": row.get("StopTimeSec"),
            "BreakDownTimeSec": row.get("BreakDownTimeSec"),
            "RunTimeRatePct": row.get("RunTimeRatePct"),
        }
        daily_run.append(compact)
        if month not in monthly or not row.get("ok"):
            continue
        monthly[month]["run_ok_days"] += 1
        monthly[month]["run_seconds"] += int(row.get("RunTimeSec") or 0)
        monthly[month]["standby_seconds"] += int(row.get("StandbyTimeSec") or 0)
        monthly[month]["stop_seconds"] += int(row.get("StopTimeSec") or 0)
        monthly[month]["breakdown_seconds"] += int(row.get("BreakDownTimeSec") or 0)
        if row.get("RunTimeRatePct") is not None:
            rate_acc[month].append(float(row["RunTimeRatePct"]))
    for month, values in rate_acc.items():
        if values:
            monthly[month]["avg_run_rate_pct"] = round(sum(values) / len(values), 2)

    spindle = (files.get("spindle") or {}).get("ResultData") or {}
    return {
        "OutFactoryCode": out_factory,
        "range": {"StartTime": start.isoformat(), "EndTime": end.isoformat()},
        "built_at": datetime.now().isoformat(timespec="seconds"),
        "monthly": monthly,
        "daily_run_status": daily_run,
        "daily_progress": sorted(daily_progress, key=lambda r: r.get("date") or ""),
        "spindle_snapshot": {
            "fetched_at": (files.get("spindle") or {}).get("Timestamp"),
            "Speed": spindle.get("Speed"),
            "Load": spindle.get("Load"),
            "Feed": spindle.get("Feed"),
            "XLoad": spindle.get("XLoad"),
            "YLoad": spindle.get("YLoad"),
            "ZLoad": spindle.get("ZLoad"),
            "ProgramCode": spindle.get("ProgramCode"),
            "KnifePosition": spindle.get("KnifePosition"),
        },
    }


def identity_from_info(info: dict, fallback_type: str) -> dict:
    row = (info.get("rows") or [None])[0] or {}
    return {
        "OutFactoryCode": row.get("OutFactoryCode"),
        "EquipCode": row.get("EquipCode") or "",
        "EquipName": row.get("EquipName") or "",
        "EquipTypeCode": row.get("EquipTypeCode") or fallback_type,
        "EquipTypeName": row.get("EquipTypeName") or "",
        "CompanyId": row.get("CompanyId") or "",
        "CompanyName": row.get("CompanyName") or "",
        "GwCode": row.get("GwCode") or "",
        "AreaName": row.get("AreaName") or "",
    }


def process_device(
    record: dict,
    *,
    start: date,
    end: date,
    days: list[date],
    skip_run_status: bool,
) -> dict:
    code = str(record["OutFactoryCode"])
    folder = ROOT / code
    folder.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    errors: list[str] = []

    def load_or_fetch(path: Path, fetcher, *, reusable=None):
        if path.exists():
            try:
                payload = load_json(path)
            except Exception:
                payload = {"error": "unreadable"}
            if not payload.get("error") and (reusable is None or reusable(payload)):
                return payload
        try:
            payload = fetcher()
            write_json(path, payload)
            return payload
        except Exception as exc:
            errors.append(f"{path.name}: {exc}")
            log(f"  {code} defer {path.name}: {exc}")
            return {"rows": [], "record_count": 0, "error": str(exc)}

    info_path = folder / "GetEquipInfoPageList.json"
    info = load_or_fetch(info_path, lambda: fetch_info(code), reusable=lambda p: bool(p.get("rows")))
    ident = identity_from_info(info, str(record.get("EquipTypeCode") or ""))
    company_id = ident["CompanyId"] or DEFAULT_CUSTOMER_ID
    equip_code = ident["EquipCode"]

    spindle = load_or_fetch(
        folder / "GetEquipSpindleWithFeedData.json",
        lambda: fetch_spindle(code, company_id, equip_code),
        reusable=lambda p: bool(p.get("ResultData")),
    )

    alarm_path = folder / "GetEquipAbnorPageList.json"
    alarms = load_or_fetch(
        alarm_path,
        lambda: paginate_range(
            "/OpenApi/GetEquipAbnorPageList",
            {
                "companyId": DEFAULT_CUSTOMER_ID,
                "OutFactoryCode": code,
                "EquipName": ident["EquipName"],
            },
            start,
            end,
            dest=alarm_path,
            page_size=20,
        ),
        reusable=lambda p: not p.get("partial") and not p.get("error"),
    )

    program_path = folder / "GetEquipProgramPageList.json"

    def fetch_program():
        if not ident.get("CompanyId") and not ident.get("EquipCode"):
            return {
                "api": "/OpenApi/GetEquipProgramPageList",
                "query": {"OutFactoryCode": code},
                "note": "GetEquipInfoPageList returned no identity; program list skipped",
                "record_count": 0,
                "rows": [],
            }
        program = paginate_range(
            "/OpenApi/GetEquipProgramPageList",
            {
                "companyId": company_id,
                "EquipName": ident["EquipName"],
                "OutFactoryCode": code,
                "EquipCode": equip_code,
            },
            start,
            end,
            dest=program_path,
            page_size=20,
        )
        if equip_code:
            mixed = program.get("rows") or []
            kept = [row for row in mixed if (row.get("EquipCode") or "") == equip_code]
            if kept or mixed:
                program["rows_before_filter"] = len(mixed)
                program["filtered_by"] = {"EquipCode": equip_code}
                program["rows"] = kept
                program["record_count"] = len(kept)
        return program

    program = load_or_fetch(
        program_path,
        fetch_program,
        reusable=lambda p: not p.get("partial") and not p.get("error"),
    )
    progress = load_or_fetch(
        folder / "GetEquipProductionProgressPageList.json",
        lambda: paginate_months(
            "/OpenApi/GetEquipProductionProgressPageList",
            {
                "companyId": company_id,
                "EquipName": ident["EquipName"],
                "OutFactoryCode": code,
                "EquipCode": equip_code,
            },
            start,
            end,
            page_size=100,
        ),
    )
    boot = load_or_fetch(
        folder / "GetEquipBootOrRunningTimeList.json",
        lambda: fetch_boot(company_id, start, end),
    )

    run_path = folder / "GetEquipRunStatusList.json"
    if skip_run_status:
        run_status = load_json(run_path) if run_path.exists() else {"rows": [], "skipped": True}
    elif run_path.exists():
        run_status = load_json(run_path)
        if run_status.get("partial") or run_ok_days(run_status) < len(days):
            run_status = fetch_run_status(code, company_id, days, run_path)
    else:
        run_status = fetch_run_status(code, company_id, days, run_path)

    files = {
        "alarms": alarms,
        "program": program,
        "progress": progress,
        "run_status": run_status,
        "spindle": spindle,
    }
    trend = build_trend(code, start, end, files)
    write_json(folder / "trend_summary.json", trend)
    meta = {
        "OutFactoryCode": code,
        "excel_EquipTypeCode": record.get("EquipTypeCode"),
        "identity": ident,
        "range": {"StartTime": start.isoformat(), "EndTime": end.isoformat()},
        "files": {
            "GetEquipInfoPageList.json": info.get("record_count"),
            "GetEquipSpindleWithFeedData.json": 1 if spindle.get("ResultData") else 0,
            "GetEquipRunStatusList.json": run_status.get("ok_days", len(run_status.get("rows") or [])),
            "GetEquipAbnorPageList.json": alarms.get("record_count"),
            "GetEquipProgramPageList.json": program.get("record_count"),
            "GetEquipProductionProgressPageList.json": progress.get("record_count"),
            "GetEquipBootOrRunningTimeList.json": boot.get("record_count"),
            "trend_summary.json": True,
        },
        "elapsed_sec": round(time.time() - t0, 1),
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "errors": errors or None,
    }
    core_ready = all(
        (folder / name).exists()
        for name in (
            "GetEquipAbnorPageList.json",
            "GetEquipProgramPageList.json",
            "GetEquipProductionProgressPageList.json",
            "GetEquipRunStatusList.json",
        )
    )
    if core_ready:
        write_json(folder / "meta.json", meta)
    log(
        f"  {code} info={ident.get('CompanyName') or '-'} "
        f"alarms={alarms.get('record_count')} program={program.get('record_count')} "
        f"progress={progress.get('record_count')} run={run_status.get('ok_days', 0)} "
        f"{meta['elapsed_sec']}s"
        + (f" deferred={len(errors)}" if errors else "")
    )
    if errors:
        raise RuntimeError("; ".join(errors))
    return meta


def fetch_global_customer_list(start: date, end: date) -> dict:
    dest = ROOT / "_global" / "GetCustomerList.json"
    if dest.exists():
        return load_json(dest)
    payload = paginate(
        "/OpenApi/GetCustomerList",
        {
            "CustomerId": DEFAULT_CUSTOMER_ID,
            "AreaName": "",
            "StartTime": start.isoformat(),
            "EndTime": end.isoformat(),
        },
        page_size=200,
    )
    write_json(dest, payload)
    return payload


def run_ok_days(payload: dict) -> int:
    if isinstance(payload.get("ok_days"), int):
        return payload["ok_days"]
    return sum(1 for row in payload.get("rows") or [] if row.get("ok"))


def device_gaps(folder: Path, *, days: int) -> list[str]:
    missing: list[str] = []
    for name in REQUIRED_FILES:
        path = folder / name
        if not path.exists():
            missing.append(name)
            continue
        try:
            payload = load_json(path)
        except Exception:
            missing.append(name)
            continue
        if payload.get("error") or payload.get("partial"):
            missing.append(name)
            continue
        if name == "GetEquipInfoPageList.json" and not (payload.get("rows") or []):
            missing.append("identity")
        if name == "GetEquipSpindleWithFeedData.json" and not (
            payload.get("ResultData") or payload.get("IsSuccess")
        ):
            missing.append("spindle")
        if name == "GetEquipRunStatusList.json":
            ok = run_ok_days(payload)
            if payload.get("partial") or ok < days:
                missing.append(f"run_status:{ok}/{days}")
    return missing


def activity_from_trend(trend: dict) -> dict:
    monthly = trend.get("monthly") or {}
    alarm = program = progress = run_seconds = 0
    rates: list[float] = []
    for stats in monthly.values():
        alarm += int(stats.get("alarm_count") or 0)
        program += int(stats.get("program_cycles") or 0)
        progress += int(stats.get("progress_output") or 0)
        run_seconds += int(stats.get("run_seconds") or 0)
        if stats.get("avg_run_rate_pct") is not None:
            rates.append(float(stats["avg_run_rate_pct"]))
    return {
        "alarm_count": alarm,
        "program_cycles": program,
        "progress_output": progress,
        "run_hours": round(run_seconds / 3600, 1),
        "avg_run_rate_pct": round(sum(rates) / len(rates), 2) if rates else 0.0,
    }


def publish_complete_dump(records: list[dict], *, start: date, end: date) -> dict:
    complete_root = ROOT / "_complete"
    complete_root.mkdir(parents=True, exist_ok=True)
    days = len(daterange(start, end))
    complete_rows: list[dict] = []
    incomplete_rows: list[dict] = []
    by_type: dict[str, int] = {}
    by_area: dict[str, int] = {}
    fleet_monthly: dict[str, dict] = {}

    for record in records:
        code = str(record["OutFactoryCode"])
        folder = ROOT / code
        gaps = device_gaps(folder, days=days)
        if gaps:
            incomplete_rows.append({"OutFactoryCode": code, "missing": gaps})
            continue
        meta = load_json(folder / "meta.json")
        trend = load_json(folder / "trend_summary.json")
        ident = meta.get("identity") or {}
        activity = activity_from_trend(trend)
        dest = complete_root / code
        dest.mkdir(parents=True, exist_ok=True)
        write_json(dest / "meta.json", meta)
        write_json(dest / "trend_summary.json", trend)
        info_src = folder / "GetEquipInfoPageList.json"
        if info_src.exists():
            shutil.copy2(info_src, dest / "GetEquipInfoPageList.json")
        write_json(
            dest / "history.json",
            {
                "OutFactoryCode": code,
                "identity": ident,
                "range": meta.get("range") or {"StartTime": start.isoformat(), "EndTime": end.isoformat()},
                "activity": activity,
                "monthly": trend.get("monthly") or {},
                "daily_run_status": [
                    {
                        "date": row.get("date"),
                        "RunTimeRatePct": row.get("RunTimeRatePct"),
                        "RunTimeSec": row.get("RunTimeSec"),
                        "BreakDownTimeSec": row.get("BreakDownTimeSec"),
                    }
                    for row in trend.get("daily_run_status") or []
                ],
                "daily_progress": trend.get("daily_progress") or [],
                "spindle_snapshot": trend.get("spindle_snapshot") or {},
                "full_api_dir": f"datasets/json/iot_timeseries/{code}",
            },
        )
        type_code = ident.get("EquipTypeCode") or record.get("EquipTypeCode") or ""
        area = ident.get("AreaName") or ""
        by_type[type_code] = by_type.get(type_code, 0) + 1
        by_area[area] = by_area.get(area, 0) + 1
        complete_rows.append(
            {
                "OutFactoryCode": code,
                "identity": ident,
                "excel_EquipTypeCode": record.get("EquipTypeCode"),
                "files": meta.get("files") or {},
                "activity": activity,
                "monthly": trend.get("monthly") or {},
                "source_dir": f"datasets/json/iot_timeseries/{code}",
                "complete_dir": f"datasets/json/iot_timeseries/_complete/{code}",
            }
        )
        for month, stats in (trend.get("monthly") or {}).items():
            bucket = fleet_monthly.setdefault(
                month,
                {
                    "device_count": 0,
                    "alarm_count": 0,
                    "shutdown_alarm_count": 0,
                    "program_cycles": 0,
                    "progress_output": 0,
                    "run_hours": 0.0,
                    "_rate_acc": [],
                },
            )
            bucket["device_count"] += 1
            bucket["alarm_count"] += int(stats.get("alarm_count") or 0)
            bucket["shutdown_alarm_count"] += int(stats.get("shutdown_alarm_count") or 0)
            bucket["program_cycles"] += int(stats.get("program_cycles") or 0)
            bucket["progress_output"] += int(stats.get("progress_output") or 0)
            bucket["run_hours"] += int(stats.get("run_seconds") or 0) / 3600
            if stats.get("avg_run_rate_pct") is not None:
                bucket["_rate_acc"].append(float(stats["avg_run_rate_pct"]))

    complete_rows.sort(key=lambda row: -float((row["activity"] or {}).get("run_hours") or 0))
    index = [
        {
            "OutFactoryCode": row["OutFactoryCode"],
            "CompanyName": (row.get("identity") or {}).get("CompanyName"),
            "EquipTypeCode": (row.get("identity") or {}).get("EquipTypeCode"),
            "AreaName": (row.get("identity") or {}).get("AreaName"),
            **row["activity"],
            "path": row["complete_dir"],
        }
        for row in complete_rows
    ]
    fleet_out = {}
    for month, bucket in fleet_monthly.items():
        rates = bucket.pop("_rate_acc")
        fleet_out[month] = {
            "device_count": bucket["device_count"],
            "alarm_count": bucket["alarm_count"],
            "shutdown_alarm_count": bucket["shutdown_alarm_count"],
            "program_cycles": bucket["program_cycles"],
            "progress_output": bucket["progress_output"],
            "run_hours": round(bucket["run_hours"], 1),
            "avg_run_rate_pct": round(sum(rates) / len(rates), 2) if rates else 0.0,
        }
    catalog = {
        "title": "Mar–Aug 2026 complete-device dump",
        "criteria": {
            "required_files": list(REQUIRED_FILES),
            "run_ok_days": days,
            "resolved_identity": True,
            "spindle_snapshot": True,
        },
        "range": {"StartTime": start.isoformat(), "EndTime": end.isoformat()},
        "complete_count": len(complete_rows),
        "incomplete_count": len(incomplete_rows),
        "by_type": by_type,
        "by_area": by_area,
        "devices": complete_rows,
        "incomplete": incomplete_rows,
    }
    write_json(complete_root / "catalog.json", catalog)
    write_json(complete_root / "index.json", index)
    write_json(
        complete_root / "fleet_trend.json",
        {
            "range": {"StartTime": start.isoformat(), "EndTime": end.isoformat()},
            "monthly": fleet_out,
            "device_count": len(complete_rows),
        },
    )
    log(f"Published _complete complete={len(complete_rows)} incomplete={len(incomplete_rows)}")
    return catalog


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0, help="Only fetch the first N devices")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--start", default=START.isoformat())
    parser.add_argument("--end", default=END.isoformat())
    parser.add_argument("--skip-run-status", action="store_true")
    parser.add_argument("--codes", default="", help="Comma-separated OutFactoryCode subset")
    parser.add_argument("--only-incomplete", action="store_true", help="Skip devices already complete on disk")
    parser.add_argument("--publish-only", action="store_true", help="Only refresh iot_timeseries/_complete")
    args = parser.parse_args()
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    days = daterange(start, end)

    master = json.loads(MASTER_PATH.read_text(encoding="utf-8"))
    records = list(master["records"])
    if args.codes:
        wanted = {c.strip() for c in args.codes.split(",") if c.strip()}
        records = [r for r in records if str(r["OutFactoryCode"]) in wanted]
    if args.only_incomplete:
        records = [r for r in records if device_gaps(ROOT / str(r["OutFactoryCode"]), days=len(days))]
    if args.limit:
        records = records[: args.limit]

    ROOT.mkdir(parents=True, exist_ok=True)
    if args.publish_only:
        publish_complete_dump(list(master["records"]), start=start, end=end)
        return

    log(f"Fetching {len(records)} devices {start} → {end} workers={args.workers}")
    try:
        global_customers = fetch_global_customer_list(start, end)
        log(f"  _global/GetCustomerList.json records={global_customers.get('record_count')}")
    except Exception as exc:
        log(f"  GetCustomerList skipped: {exc}")

    metas = []
    errors = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futs = {
            pool.submit(
                process_device,
                rec,
                start=start,
                end=end,
                days=days,
                skip_run_status=args.skip_run_status,
            ): rec
            for rec in records
        }
        for fut in as_completed(futs):
            rec = futs[fut]
            try:
                metas.append(fut.result())
            except Exception as exc:
                code = rec.get("OutFactoryCode")
                errors.append({"OutFactoryCode": code, "error": str(exc)})
                log(f"  FAIL {code}: {exc}")

    manifest = {
        "title": "IoT OpenAPI Mar–Aug 2026 per-device dump",
        "base_url": BASE_URL,
        "range": {"StartTime": start.isoformat(), "EndTime": end.isoformat()},
        "device_count": len(records),
        "ok": len(metas),
        "failed": errors,
        "devices": sorted(metas, key=lambda m: str(m.get("OutFactoryCode"))),
        "written_at": datetime.now().isoformat(timespec="seconds"),
    }
    write_json(ROOT / "manifest.json", manifest)
    log(f"Wrote {ROOT} ok={len(metas)} failed={len(errors)}")
    publish_complete_dump(list(master["records"]), start=start, end=end)


if __name__ == "__main__":
    main()
