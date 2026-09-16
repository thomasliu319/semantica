"""Fetch MES/PdM OpenAPI rows for each Excel device, Mar–Aug 2026.

Writes one folder per OutFactoryCode under datasets/json/iot_timeseries/.
Resumable: existing complete JSON files are skipped.
"""

from __future__ import annotations

import argparse
import json
import re
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


def fetch_info(out_factory: str) -> dict:
    envelope = post(
        "/OpenApi/GetEquipInfoPageList",
        {
            "page": 1,
            "rows": 20,
            "CustomerId": DEFAULT_CUSTOMER_ID,
            "OutFactoryCode": out_factory,
            "EquipCode": "",
            "CompanyName": "",
            "EquipName": "",
            "GwCode": "",
            "SIMNo": "",
            "EquipTypeName": "",
            "AreaName": "",
        },
    )
    rows = result_rows(envelope)
    return {
        "api": "/OpenApi/GetEquipInfoPageList",
        "query": {"OutFactoryCode": out_factory, "CustomerId": DEFAULT_CUSTOMER_ID},
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "IsSuccess": envelope.get("IsSuccess"),
        "Message": envelope.get("Message"),
        "record_count": len(rows),
        "rows": rows,
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

    info_path = folder / "GetEquipInfoPageList.json"
    if info_path.exists():
        info = load_json(info_path)
    else:
        info = fetch_info(code)
        write_json(info_path, info)
    ident = identity_from_info(info, str(record.get("EquipTypeCode") or ""))
    company_id = ident["CompanyId"] or DEFAULT_CUSTOMER_ID
    equip_code = ident["EquipCode"]
    errors: list[str] = []

    def load_or_fetch(path: Path, fetcher):
        if path.exists():
            return load_json(path)
        try:
            payload = fetcher()
            write_json(path, payload)
            return payload
        except Exception as exc:
            errors.append(f"{path.name}: {exc}")
            log(f"  {code} defer {path.name}: {exc}")
            return {"rows": [], "record_count": 0, "error": str(exc)}

    spindle = load_or_fetch(
        folder / "GetEquipSpindleWithFeedData.json",
        lambda: fetch_spindle(code, company_id, equip_code),
    )

    alarms = load_or_fetch(
        folder / "GetEquipAbnorPageList.json",
        lambda: paginate(
            "/OpenApi/GetEquipAbnorPageList",
            {
                "companyId": DEFAULT_CUSTOMER_ID,
                "OutFactoryCode": code,
                "EquipName": ident["EquipName"],
                "StartTime": start.isoformat(),
                "EndTime": end.isoformat(),
            },
        ),
    )

    def fetch_program():
        program = paginate(
            "/OpenApi/GetEquipProgramPageList",
            {
                "companyId": company_id,
                "StartTime": start.isoformat(),
                "EndTime": end.isoformat(),
                "EquipName": ident["EquipName"],
                "OutFactoryCode": code,
                "EquipCode": equip_code,
            },
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

    program = load_or_fetch(folder / "GetEquipProgramPageList.json", fetch_program)
    progress = load_or_fetch(
        folder / "GetEquipProductionProgressPageList.json",
        lambda: paginate(
            "/OpenApi/GetEquipProductionProgressPageList",
            {
                "companyId": company_id,
                "StartTime": start.isoformat(),
                "EndTime": end.isoformat(),
                "EquipName": ident["EquipName"],
                "OutFactoryCode": code,
                "EquipCode": equip_code,
            },
        ),
    )
    boot = load_or_fetch(
        folder / "GetEquipBootOrRunningTimeList.json",
        lambda: fetch_boot(company_id, start, end),
    )

    run_path = folder / "GetEquipRunStatusList.json"
    if skip_run_status:
        run_status = load_json(run_path) if run_path.exists() else {"rows": [], "skipped": True}
    elif run_path.exists() and not load_json(run_path).get("partial"):
        run_status = load_json(run_path)
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0, help="Only fetch the first N devices")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--start", default=START.isoformat())
    parser.add_argument("--end", default=END.isoformat())
    parser.add_argument("--skip-run-status", action="store_true")
    parser.add_argument("--codes", default="", help="Comma-separated OutFactoryCode subset")
    args = parser.parse_args()
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    days = daterange(start, end)

    master = json.loads(MASTER_PATH.read_text(encoding="utf-8"))
    records = list(master["records"])
    if args.codes:
        wanted = {c.strip() for c in args.codes.split(",") if c.strip()}
        records = [r for r in records if str(r["OutFactoryCode"]) in wanted]
    if args.limit:
        records = records[: args.limit]

    ROOT.mkdir(parents=True, exist_ok=True)
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


if __name__ == "__main__":
    main()
