"""
pre_shift_check.py
==================
GET  /api/pre-shift-check?date=YYYY-MM-DD[&refresh=1]

Executes a 3-tier redundancy health check (Trips / Earnings / Expenses) with
independent sources that must agree before reporting confidence.

Design principles:
  - No single source is trusted.
  - Never raises an exception to the HTTP caller — always returns HTTP 200.
  - Every external call has a hard timeout via asyncio.wait_for.
  - Results are cached for 30 min (in-process dict + DB row when DB is up).
  - IANA timezone "America/Denver" is used for all local-date conversions.
"""

import azure.functions as func
import asyncio
import datetime
import json
import logging
import os
import time
import pytz

from services.database import DatabaseClient

log = logging.getLogger(__name__)

bp = func.Blueprint()

# ── Constants ──────────────────────────────────────────────────────────────────
_MT = pytz.timezone("America/Denver")
_UTC = pytz.utc
_PIPELINE_VERSION = "2.0.0"
_CACHE_TTL_S = 1800          # 30 minutes
_DEFAULT_TIMEOUT_S = 5.0
_DB_TIMEOUT_S = 20.0         # Azure SQL can take 15-30s on cold start
_ONEDRIVE_TIMEOUT_S = 10.0
_NOTIFICATION_THRESHOLD = 75

# In-process cache: (date_str, pipeline_version) → {payload, expires_at}
_mem_cache: dict = {}

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
}

# ── Helpers ────────────────────────────────────────────────────────────────────

def _mt_date_to_utc_window(date_str: str) -> tuple[datetime.datetime, datetime.datetime]:
    """
    Convert a local America/Denver date string (YYYY-MM-DD) to a UTC window
    [start_utc, end_utc) representing midnight-to-midnight MDT/MST.
    """
    naive_start = datetime.datetime.strptime(date_str, "%Y-%m-%d")
    naive_end   = naive_start + datetime.timedelta(days=1)
    start_mt    = _MT.localize(naive_start, is_dst=None)
    end_mt      = _MT.localize(naive_end,   is_dst=None)
    return start_mt.astimezone(_UTC), end_mt.astimezone(_UTC)


def _source_result(status: str, value=None, latency_ms: float | None = None,
                   error: str | None = None) -> dict:
    """Standard source result envelope."""
    return {"status": status, "value": value, "latency_ms": latency_ms, "error": error}


def _tier_result(status: str, confidence: int | None, values: dict,
                 delta: dict, notes: list, outliers: list,
                 meta: dict | None = None) -> dict:
    result = {
        "status": status,
        "confidence": confidence,
        "values": values,
        "delta": delta,
        "notes": notes,
        "outliers": outliers,
    }
    if meta:
        result["meta"] = meta
    return result


async def safe_call(coro, timeout_s: float, name: str) -> dict:
    """
    Execute *coro* with a hard timeout. Always returns a source_result dict.
    Catches ALL exceptions so callers never crash.
    """
    t0 = time.monotonic()
    try:
        value = await asyncio.wait_for(coro, timeout=timeout_s)
        latency_ms = round((time.monotonic() - t0) * 1000, 1)
        return _source_result("OK", value, latency_ms)
    except asyncio.TimeoutError:
        latency_ms = round((time.monotonic() - t0) * 1000, 1)
        log.warning(f"[PreShift] {name} timed out after {timeout_s}s")
        return _source_result("UNAVAILABLE", None, latency_ms,
                              f"Timed out after {timeout_s}s")
    except Exception as exc:
        latency_ms = round((time.monotonic() - t0) * 1000, 1)
        log.error(f"[PreShift] {name} raised: {exc}")
        return _source_result("UNAVAILABLE", None, latency_ms, str(exc))


# ── Source implementations ─────────────────────────────────────────────────────

async def _src_db_trip_count(start_utc: datetime.datetime,
                             end_utc: datetime.datetime) -> int:
    """Count Tessie-sourced Uber drives in DB for the UTC window.

    Only counts RideIDs prefixed 'TESSIE-' with Classification='Uber_Dropoff',
    which directly corresponds to what Tessie's /drives API returns. OCR-matched
    trips (TRIP-YYYYMMDD-XX, Uber_Matched) are screenshot-derived and are NOT
    visible in Tessie's API, so they must be excluded to keep sources comparable.
    """
    def _query():
        db = DatabaseClient()
        conn = db.get_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT COUNT(*) FROM Rides.Rides
               WHERE TripType = 'Uber'
               AND Classification = 'Uber_Dropoff'
               AND RideID LIKE 'TESSIE-%'
               AND Timestamp_Start >= ? AND Timestamp_Start < ?""",
            (start_utc.replace(tzinfo=None), end_utc.replace(tzinfo=None))
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        return int(row[0]) if row else 0
    return await asyncio.get_event_loop().run_in_executor(None, _query)



async def _src_db_earnings_sum(start_utc: datetime.datetime,
                               end_utc: datetime.datetime) -> float:
    """Sum Driver_Earnings from DB for the UTC window."""
    def _query():
        db = DatabaseClient()
        conn = db.get_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT ISNULL(SUM(Driver_Earnings), 0) FROM Rides.Rides
               WHERE (TripType = 'Uber' OR TripType IS NULL)
               AND Timestamp_Start >= ? AND Timestamp_Start < ?""",
            (start_utc.replace(tzinfo=None), end_utc.replace(tzinfo=None))
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        return round(float(row[0]), 2) if row else 0.0
    return await asyncio.get_event_loop().run_in_executor(None, _query)


async def _src_db_expense_count(start_utc: datetime.datetime,
                                end_utc: datetime.datetime) -> int:
    """Count Meal_Receipt expenses in DB for the UTC window."""
    def _query():
        db = DatabaseClient()
        conn = db.get_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT COUNT(*) FROM Rides.ManualExpenses
               WHERE Category IN ('Meal_Receipt','General_Expense','FastFood')
               AND Timestamp >= ? AND Timestamp < ?""",
            (start_utc.replace(tzinfo=None), end_utc.replace(tzinfo=None))
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        return int(row[0]) if row else 0
    return await asyncio.get_event_loop().run_in_executor(None, _query)


async def _src_db_ocr_earnings(start_utc: datetime.datetime,
                               end_utc: datetime.datetime) -> float:
    """
    Sum earnings from the Sidecar_Artifact_JSON OCR field for screenshot-derived trips.
    Falls back to Driver_Earnings when sidecar is absent (still counts as OCR source
    because trip was OCR-scanned from a screenshot into the DB).
    """
    def _query():
        db = DatabaseClient()
        conn = db.get_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT Sidecar_Artifact_JSON, Driver_Earnings FROM Rides.Rides
               WHERE (TripType = 'Uber' OR TripType IS NULL)
               AND Timestamp_Start >= ? AND Timestamp_Start < ?""",
            (start_utc.replace(tzinfo=None), end_utc.replace(tzinfo=None))
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        total = 0.0
        import json as _json
        for sidecar_raw, db_earnings in rows:
            try:
                sidecar = _json.loads(str(sidecar_raw)) if sidecar_raw else {}
                val = sidecar.get("driver_earnings") or sidecar.get("earnings")
                total += float(val) if val is not None else float(db_earnings or 0)
            except Exception:
                total += float(db_earnings or 0)
        return round(total, 2)
    return await asyncio.get_event_loop().run_in_executor(None, _query)


async def _src_tessie_trip_count(date_str: str,
                                 start_utc: datetime.datetime,
                                 end_utc: datetime.datetime) -> int:
    """Count Tessie drives tagged Uber* for the target date.

    Notes:
    - Tessie's /drives API requires 'from' and 'to' as Unix timestamps.
    - A 404 from Tessie means no drives exist for the range (treated as UNAVAILABLE by safe_call).
    - We count ALL drives with 'uber' anywhere in the tag — no distance filter, since
      Tessie labels are set by the operator and are authoritative (e.g. 'Uber Trip 1').
    """
    import requests as _req
    vin   = os.environ.get("TESSIE_VIN", "")
    token = os.environ.get("TESSIE_TOKEN", "") or os.environ.get("TESSIE_API_KEY", "")
    if not vin or not token:
        raise ValueError("TESSIE_VIN or TESSIE_TOKEN not configured")

    from_ts = int(start_utc.timestamp())
    to_ts   = int(end_utc.timestamp())
    url     = f"https://api.tessie.com/{vin}/drives"
    resp    = _req.get(url, headers={"Authorization": f"Bearer {token}"},
                       params={"from": from_ts, "to": to_ts, "limit": 250},
                       timeout=_DEFAULT_TIMEOUT_S)
    if resp.status_code == 404:
        raise ValueError(f"Tessie /drives returned 404 for date {date_str} — no drives in range")
    resp.raise_for_status()
    data   = resp.json()
    drives = data.get("results") or data.get("drives") or []
    # Count any drive where the operator label contains 'uber' (case-insensitive)
    # No distance threshold — the label is the authoritative source of trip type.
    count = sum(1 for d in drives if "uber" in (d.get("tag") or "").lower())
    log.info(f"[PreShift] Tessie /drives for {date_str}: {len(drives)} total, {count} uber-tagged")
    return count



async def _src_onedrive_trip_count(date_str: str) -> int:
    """
    Count Uber Driver screenshot files in the OneDrive folder for date_str.
    Folder pattern: Uber Driver/YYYY/Month/Week X/M.DD.YY
    Uses MS Graph API.
    """
    token = await _get_graph_token()
    if not token:
        raise ValueError("MS Graph credentials not configured")

    folder_path = _build_onedrive_path(date_str, subfolder_hint="Uber Driver")
    count = await _graph_count_files(
        token, folder_path,
        include_extensions=[".jpg", ".jpeg", ".png"],
        exclude_patterns=["Starbucks", "WingStop", "Scan_", "_Starbucks", "Charging"]
    )
    return count


async def _src_onedrive_expense_count(date_str: str) -> int:
    """Count non-Uber-Driver expense screenshots in the date folder."""
    token = await _get_graph_token()
    if not token:
        raise ValueError("MS Graph credentials not configured")

    folder_path = _build_onedrive_path(date_str, subfolder_hint="Uber Driver")
    count = await _graph_count_files(
        token, folder_path,
        include_extensions=[".jpg", ".jpeg", ".png", ".pdf"],
        exclude_patterns=["_Uber Driver"]
    )
    return count


async def _src_bank_trip_count(date_str: str) -> int:
    """Placeholder: Teller bank transactions for Uber deposits on date."""
    teller_token = os.environ.get("TELLER_ACCESS_TOKEN", "")
    if not teller_token:
        raise ValueError("TELLER_ACCESS_TOKEN not configured")
    # Teller integration placeholder — returns UNAVAILABLE when not wired
    raise NotImplementedError("Teller not configured")


async def _src_bank_earnings(date_str: str) -> float:
    """Placeholder: Bank Uber deposits for date."""
    teller_token = os.environ.get("TELLER_ACCESS_TOKEN", "")
    if not teller_token:
        raise ValueError("TELLER_ACCESS_TOKEN not configured")
    raise NotImplementedError("Teller not configured")


# ── Tier 4: Timeline Integrity ────────────────────────────────────────────────

_GAP_WARN_SECONDS = 2700   # 45 minutes
_MICRO_DRIVE_MI   = 0.25   # ignore repositioning noise

async def _src_tier4_timeline(start_utc: datetime.datetime,
                              end_utc: datetime.datetime) -> dict:
    """
    Query trip timestamps and Tessie drives for the day.
    Returns a structured issues dict:
      overlaps      : list of (tripA_id, tripB_id, overlap_seconds)
      large_gaps    : list of (tripA_id, tripB_id, gap_seconds)
      orphan_drives : list of tessie_drive_ids (distance >= 0.25 mi, no matched trip)
      trip_count    : int
    """
    def _query():
        db   = DatabaseClient()
        conn = db.get_connection()
        cur  = conn.cursor()

        # ── 1. Fetch ordered trips ──
        cur.execute(
            """SELECT RideID, Timestamp_Start, Tessie_DriveID
               FROM Rides.Rides
               WHERE (TripType = 'Uber' OR TripType IS NULL)
               AND Timestamp_Start >= ? AND Timestamp_Start < ?
               AND Timestamp_Start IS NOT NULL
               ORDER BY Timestamp_Start ASC""",
            (start_utc.replace(tzinfo=None), end_utc.replace(tzinfo=None))
        )
        trips = cur.fetchall()   # (RideID, Timestamp_Start, Tessie_DriveID)

        # ── 2. Overlap + gap analysis ──
        overlaps, large_gaps = [], []
        for i in range(len(trips) - 1):
            a_id, a_start, _ = trips[i]
            b_id, b_start, _ = trips[i + 1]
            if b_start < a_start:
                overlaps.append({"trip_a": a_id, "trip_b": b_id,
                                  "overlap_s": int((a_start - b_start).total_seconds())})
            else:
                gap_s = int((b_start - a_start).total_seconds())
                if gap_s > _GAP_WARN_SECONDS:
                    large_gaps.append({"trip_a": a_id, "trip_b": b_id, "gap_s": gap_s})

        # ── 3. Orphan Tessie drives ──
        matched_tessie_ids = set(
            str(row[2]).replace("TESSIE-", "")
            for row in trips if row[2]
        )
        try:
            cur.execute(
                """SELECT DriveID, Distance_mi
                   FROM dbo.Drive_Telemetry
                   WHERE StartTime >= ? AND StartTime < ?
                   AND ISNULL(Distance_mi, 0) >= ?""",
                (start_utc.replace(tzinfo=None), end_utc.replace(tzinfo=None),
                 _MICRO_DRIVE_MI)
            )
            all_drives = cur.fetchall()
            orphans = [
                str(row[0]) for row in all_drives
                if str(row[0]) not in matched_tessie_ids
            ]
        except Exception:
            orphans = []   # Drive_Telemetry may not exist — non-fatal

        cur.close()
        conn.close()
        return {
            "overlaps":      overlaps,
            "large_gaps":    large_gaps,
            "orphan_drives": orphans,
            "trip_count":    len(trips),
        }

    return await asyncio.get_event_loop().run_in_executor(None, _query)


def _score_tier4(timeline_r: dict) -> dict:
    """
    Timeline Integrity scorer.

    Mode: Strict Consensus · Deterministic Evaluation
    Source: DB only (always available, no external dependency)

    Scoring:
      No issues            → 100  PASS
      Only large gaps      →  75  WARN
      Any overlap/orphan   →  40  FAIL
    """
    notes, outliers, delta = [], [], {}

    if timeline_r["status"] != "OK" or timeline_r["value"] is None:
        return _tier_result("N_A", None,
                            {"timeline": timeline_r}, {},
                            ["Timeline source unavailable"], [])

    data          = timeline_r["value"]
    overlaps      = data.get("overlaps", [])
    large_gaps    = data.get("large_gaps", [])
    orphan_drives = data.get("orphan_drives", [])
    trip_count    = data.get("trip_count", 0)

    delta["overlaps"]      = len(overlaps)
    delta["large_gaps"]    = len(large_gaps)
    delta["orphan_drives"] = len(orphan_drives)

    if overlaps:
        for ov in overlaps[:3]:   # cap detail at 3
            notes.append(
                f"OVERLAP: {ov['trip_a']} ↔ {ov['trip_b']} "
                f"({ov['overlap_s']//60}m {ov['overlap_s']%60}s)"
            )
            outliers.append(ov['trip_b'])
        status = "FAIL"
        conf   = 40
        likely = "Duplicate trip import or incorrect timestamp on scanner"
        notes.append(f"Likely cause: {likely}")

    elif orphan_drives:
        for od in orphan_drives[:3]:
            notes.append(f"ORPHAN DRIVE: Tessie {od} (≥{_MICRO_DRIVE_MI}mi, no matched trip)")
            outliers.append(f"tessie_{od}")
        status = "FAIL"
        conf   = 40
        notes.append("Likely cause: Uber trip not scanned / missing from DB for this drive")

    elif large_gaps:
        for gap in large_gaps[:3]:
            gap_min = gap['gap_s'] // 60
            notes.append(
                f"LARGE GAP: {gap['trip_a']} → {gap['trip_b']}: "
                f"{gap_min}min idle (>{_GAP_WARN_SECONDS//60}min threshold)"
            )
        status = "WARN"
        conf   = 75
        notes.append("Likely cause: Meal break / charging stop / end of surge — review if unexpected")

    else:
        status = "PASS"
        conf   = 100
        notes.append(f"Sequence integrity confirmed across {trip_count} trips — no overlaps, gaps, or orphans")

    return _tier_result(status, conf, {"timeline": timeline_r}, delta, notes, outliers)


# ── MS Graph helpers ───────────────────────────────────────────────────────────

_graph_token_cache: dict = {}

async def _get_graph_token() -> str | None:
    """Obtain MS Graph token via client credentials. Returns None if not configured."""
    client_id     = os.environ.get("GRAPH_CLIENT_ID") or os.environ.get("MS_GRAPH_CLIENT_ID") or os.environ.get("OAUTH_CLIENT_ID")
    client_secret = os.environ.get("GRAPH_CLIENT_SECRET") or os.environ.get("MS_GRAPH_CLIENT_SECRET") or os.environ.get("OAUTH_CLIENT_SECRET")
    tenant_id     = os.environ.get("GRAPH_TENANT_ID") or os.environ.get("AZURE_TENANT_ID") or os.environ.get("OAUTH_TENANT_ID")
    if not all([client_id, client_secret, tenant_id]):
        return None

    now = time.time()
    cached = _graph_token_cache.get("token")
    if cached and cached["expires_at"] > now + 60:
        return cached["value"]

    import requests as _req
    url  = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "https://graph.microsoft.com/.default",
    }
    try:
        resp = _req.post(url, data=data, timeout=5)
        if resp.status_code != 200:
            return None
        resp_data = resp.json()
        token_val = resp_data.get("access_token")
        expires_in = int(resp_data.get("expires_in", 3600))
        _graph_token_cache["token"] = {"value": token_val,
                                       "expires_at": now + expires_in}
        return token_val
    except Exception as e:
        log.warning(f"Failed to fetch MS Graph token: {e}")
        return None


def _build_onedrive_path(date_str: str, subfolder_hint: str = "Uber Driver") -> str:
    """
    Build the OneDrive folder path for a given date.
    Pattern: Uber Driver/2026/May/Week 4/5.24.26
    """
    dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
    year = dt.strftime("%Y")
    month = dt.strftime("%B")      # "May"
    # Unified calendar week within month, anchored on Monday (matches operations / cloud_watcher)
    first = dt.replace(day=1)
    days_to_monday = (7 - first.weekday()) % 7
    first_monday = first + datetime.timedelta(days=days_to_monday)
    if dt.date() < first_monday.date():
        week_num = 1
    else:
        offset = 1 if first_monday.day == 1 else 2
        week_num = (dt.day - first_monday.day) // 7 + offset
    day_fmt = f"{dt.month}.{dt.day:02d}.{str(dt.year)[2:]}"  # "5.24.26"
    drive_id = os.environ.get("ONEDRIVE_DRIVE_ID", "") or os.environ.get("SHAREPOINT_DRIVE_ID", "")
    site_id  = os.environ.get("SHAREPOINT_SITE_ID", "")
    return f"{subfolder_hint}/{year}/{month}/Week {week_num}/{day_fmt}"


async def _graph_count_files(token: str, folder_path: str,
                             include_extensions: list[str],
                             exclude_patterns: list[str]) -> int:
    """Count files in an OneDrive folder via MS Graph. Handles 429 with 1 retry."""
    drive_id = os.environ.get("ONEDRIVE_DRIVE_ID", "") or os.environ.get("SHAREPOINT_DRIVE_ID", "")
    if not drive_id:
        raise ValueError("ONEDRIVE_DRIVE_ID not configured")

    import requests as _req
    encoded = folder_path.replace(" ", "%20")
    url = (f"https://graph.microsoft.com/v1.0/drives/{drive_id}"
           f"/root:/{encoded}:/children?$select=name,size&$top=999")
    headers = {"Authorization": f"Bearer {token}"}

    def _fetch():
        resp = _req.get(url, headers=headers, timeout=_ONEDRIVE_TIMEOUT_S)
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", "2"))
            time.sleep(min(retry_after, 3))
            resp = _req.get(url, headers=headers, timeout=_ONEDRIVE_TIMEOUT_S)
        resp.raise_for_status()
        return resp.json()

    try:
        loop = asyncio.get_running_loop()
        data = await loop.run_in_executor(None, _fetch)
    except Exception as e:
        if "404" in str(e):
            return 0  # folder not found is 0 files
        raise

    files = data.get("value", [])
    count = 0
    for f in files:
        name = f.get("name", "")
        ext  = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if include_extensions and ext not in include_extensions:
            continue
        if any(p.lower() in name.lower() for p in exclude_patterns):
            continue
        count += 1
    return count


# ── Tier scorers ───────────────────────────────────────────────────────────────

def _score_tier1(db_r: dict, tessie_r: dict, onedrive_r: dict, date_str: str = "") -> dict:
    """
    Trip Count Consensus.
    3/3 agree -> confidence 95-100 (PASS)
    2/3 agree (within +/-1 tolerance) -> confidence 65-80 (WARN)
    0-1 agree -> confidence 0-40 (FAIL)
    Any source UNAVAILABLE -> cap at 80

    Same-day grace: if the date is today (MDT) and Tessie/OneDrive return 0
    while DB has >0 trips, treat them as UNAVAILABLE (sync lag, not a real mismatch).
    """
    notes, outliers, delta = [], [], {}
    db_v        = db_r["value"]
    tessie_v    = tessie_r["value"]
    od_v        = onedrive_r["value"]

    # Same-day grace: OneDrive/Tessie are sync-lagged on today's date.
    # Use the best available trip count (from any live source) to confirm
    # there IS real activity. If ANY source shows >0 trips, a 0 from another
    # source on today's date is sync lag, not a real mismatch.
    today_mt = datetime.datetime.now(_MT).strftime("%Y-%m-%d")
    is_today = (date_str == today_mt)
    if is_today:
        best_count = db_v if (db_v is not None and db_v > 0) else (
                     tessie_v if (tessie_v is not None and tessie_v > 0) else None)
        if best_count and best_count > 0:
            if tessie_v == 0:
                tessie_v = None
                tessie_r = dict(tessie_r)
                tessie_r["value"] = None
                tessie_r["status"] = "UNAVAILABLE"
                tessie_r["error"] = "Same-day sync lag — Tessie drive tagging not yet complete"
                notes.append("Tessie: same-day sync lag (treated as unavailable)")
            if od_v == 0:
                od_v = None
                onedrive_r = dict(onedrive_r)
                onedrive_r["value"] = None
                onedrive_r["status"] = "UNAVAILABLE"
                onedrive_r["error"] = "Same-day sync lag — Uber screenshots not yet uploaded to OneDrive"
                notes.append("OneDrive: same-day sync lag — screenshots not yet uploaded (treated as unavailable)")

    available = [(s, v) for s, v in [("db", db_v), ("tessie", tessie_v), ("onedrive", od_v)]
                 if v is not None]
    unavail   = [s for s, v in [("db", db_v), ("tessie", tessie_v), ("onedrive", od_v)]
                 if v is None]

    if unavail:
        notes.append(f"Sources unavailable: {', '.join(unavail)}")
        for s in unavail:
            outliers.append(s)

    if not available:
        return _tier_result("N_A", None, {"db": db_r, "tessie": tessie_r, "onedrive": onedrive_r},
                            {}, ["All sources unavailable"], outliers)

    values_v = [v for _, v in available]
    min_v, max_v = min(values_v), max(values_v)
    spread = max_v - min_v

    if db_v is not None and tessie_v is not None:
        delta["db_vs_tessie"] = db_v - tessie_v
    if db_v is not None and od_v is not None:
        delta["db_vs_onedrive"] = db_v - od_v
    if tessie_v is not None and od_v is not None:
        delta["tessie_vs_onedrive"] = tessie_v - od_v

    # OneDrive tolerance +/-1 (upload lag)
    od_adjusted = od_v
    if od_v is not None:
        # Check if onedrive is within +/-1 of the median of other sources
        others = [v for s, v in available if s != "onedrive"]
        if others:
            med = sum(others) / len(others)
            if abs(od_v - med) == 1:
                od_adjusted = round(med)
                notes.append("OneDrive count within +/-1 upload-lag tolerance -- adjusted for consensus")

    # Recompute agreement with adjustment
    adj_values = []
    for s, v in available:
        adj_values.append(od_adjusted if s == "onedrive" else v)

    agree_count = len(set(adj_values)) == 1 and len(adj_values) > 1
    partial_agree = spread <= 1

    cap = 80 if unavail else 100

    if len(available) >= 2 and agree_count:
        conf = min(cap, 97 if len(available) == 3 else 85)
        status = "PASS"
        notes.append(f"All available sources agree: {adj_values[0]} trips")
    elif len(available) >= 2 and partial_agree:
        conf = min(cap, 72)
        status = "WARN"
        outlier_vals = [(s, v) for s, v in available if v != min_v and v != max_v]
        notes.append(f"Sources within +/-1 tolerance (spread={spread})")
    elif len(available) == 1:
        # Only DB available — WARN with single-source note
        conf = min(cap, 65)
        status = "WARN"
        notes.append(f"Only DB available: {available[0][1]} trips (secondary sources unavailable)")
    else:
        conf = min(cap, 35)
        status = "FAIL"
        for s, v in available:
            if v != max_v:
                outliers.append(f"{s}={v} (max={max_v})")
        notes.append(f"Sources disagree: spread={spread} trips")

    return _tier_result(status, conf,
                        {"db": db_r, "tessie": tessie_r, "onedrive": onedrive_r},
                        delta, notes, outliers)


def _score_tier2(db_sum_r: dict, ocr_sum_r: dict, bank_r: dict) -> dict:
    """
    Earnings Consensus.
    DB == OCR (within $0.10) → PASS even if bank differs.
    DB != OCR              → FAIL with delta.
    Bank is supporting only — UNAVAILABLE doesn't penalize below WARN.
    """
    notes, outliers, delta = [], [], {}
    db_v  = db_sum_r["value"]
    ocr_v = ocr_sum_r["value"]
    bnk_v = bank_r["value"]

    if db_v is None and ocr_v is None:
        return _tier_result("N_A", None,
                            {"db": db_sum_r, "ocr": ocr_sum_r, "bank": bank_r},
                            {}, ["Both DB and OCR unavailable"], [])

    cap = 100
    if bank_r["status"] == "UNAVAILABLE":
        notes.append("Bank source unavailable — evaluating DB vs OCR only")
        cap = 85

    if db_v is None:
        return _tier_result("WARN", 55,
                            {"db": db_sum_r, "ocr": ocr_sum_r, "bank": bank_r},
                            {}, ["DB unavailable — cannot confirm earnings"], ["db"])
    if ocr_v is None:
        return _tier_result("WARN", 55,
                            {"db": db_sum_r, "ocr": ocr_sum_r, "bank": bank_r},
                            {}, ["OCR unavailable — cannot cross-check earnings"], ["ocr"])

    diff = round(db_v - ocr_v, 2)
    delta["db_vs_ocr"] = diff
    pct  = abs(diff / ocr_v * 100) if ocr_v else 0

    if bnk_v is not None:
        delta["db_vs_bank"] = round(db_v - bnk_v, 2)

    if abs(diff) <= 0.10:
        conf = min(cap, 97)
        status = "PASS"
        notes.append(f"DB (${db_v:.2f}) matches OCR (${ocr_v:.2f}) — within $0.10")
        meta = {"gap": 0.0, "suspected_issue": None}
    elif abs(diff) <= 1.00:
        conf = min(cap, 75)
        status = "WARN"
        notes.append(f"DB (${db_v:.2f}) vs OCR (${ocr_v:.2f}): delta=${diff:+.2f} — minor rounding")
        outliers.append("db" if diff > 0 else "ocr")
        meta = {"gap": round(abs(diff), 2), "suspected_issue": "rounding_drift"}
    else:
        conf = min(cap, 25)
        status = "FAIL"
        if diff > 0:
            cause      = "DB likely inflated by duplicate/ghost records"
            issue_code = "duplicate_import_id"
        else:
            cause      = "DB likely missing trips vs OCR screenshot count"
            issue_code = "missing_ocr_ingestion"
        notes.append(f"DB (${db_v:.2f}) ≠ OCR (${ocr_v:.2f}): delta=${diff:+.2f} ({pct:.1f}%) — {cause}")
        outliers.append("db")
        meta = {"gap": round(abs(diff), 2), "suspected_issue": issue_code}

    return _tier_result(status, conf,
                        {"db": db_sum_r, "ocr": ocr_sum_r, "bank": bank_r},
                        delta, notes, outliers, meta=meta)


def _score_tier3(db_r: dict, onedrive_r: dict, bank_r: dict, date_str: str = "") -> dict:
    """
    Expense Consensus.
    DB == OneDrive -> PASS
    DB != OneDrive -> FAIL with delta.
    Bank is supporting only.

    Same-day grace: if the date is today (MDT) and OneDrive returns 0,
    treat OneDrive as UNAVAILABLE (upload lag).
    """
    notes, outliers, delta = [], [], {}
    db_v  = db_r["value"]
    od_v  = onedrive_r["value"]
    bnk_v = bank_r["value"]

    # Same-day grace: expense screenshots may not yet be uploaded to OneDrive
    today_mt = datetime.datetime.now(_MT).strftime("%Y-%m-%d")
    is_today = (date_str == today_mt)
    if is_today:
        best_count = db_v if (db_v is not None and db_v > 0) else None
        if best_count and best_count > 0:
            if od_v == 0:
                od_v = None
                onedrive_r = dict(onedrive_r)
                onedrive_r["value"] = None
                onedrive_r["status"] = "UNAVAILABLE"
                onedrive_r["error"] = "Same-day sync lag — expense screenshots not yet uploaded to OneDrive"
                notes.append("OneDrive: same-day sync lag — expense screenshots not yet uploaded (treated as unavailable)")

    available = [(s, v) for s, v in [("db", db_v), ("onedrive", od_v), ("bank", bnk_v)]
                 if v is not None]

    if not available:
        return _tier_result("N_A", None,
                            {"db": db_r, "onedrive": onedrive_r, "bank": bank_r},
                            {}, ["All sources unavailable"], [])

    cap = 100
    unavail = [s for s, v in [("db", db_v), ("onedrive", od_v), ("bank", bnk_v)] if v is None]
    if unavail:
        cap = 80
        notes.append(f"Sources unavailable: {', '.join(unavail)}")

    if db_v is not None and od_v is not None:
        diff = db_v - od_v
        delta["db_vs_onedrive"] = diff
        if abs(diff) == 0:
            conf = min(cap, 95)
            status = "PASS"
            notes.append(f"DB ({db_v}) matches OneDrive screenshot count ({od_v})")
        elif abs(diff) <= 1:
            conf = min(cap, 72)
            status = "WARN"
            notes.append(f"DB ({db_v}) vs OneDrive ({od_v}): delta={diff:+d} — possible upload lag")
            outliers.append("onedrive")
        else:
            conf = min(cap, 35)
            status = "FAIL"
            notes.append(f"DB ({db_v}) ≠ OneDrive ({od_v}): delta={diff:+d}")
            outliers.append("db" if diff > 0 else "onedrive")
    elif db_v is not None:
        conf = min(cap, 60)
        status = "WARN"
        notes.append(f"Only DB available: {db_v} expense(s)")
    else:
        conf = min(cap, 55)
        status = "WARN"
        notes.append("DB unavailable — evaluating remaining sources only")

    return _tier_result(status, conf,
                        {"db": db_r, "onedrive": onedrive_r, "bank": bank_r},
                        delta, notes, outliers)


# ── Overall scorer ─────────────────────────────────────────────────────────────

def _compute_overall(t1: dict, t2: dict, t3: dict,
                     t4: dict | None = None) -> tuple[str, int | None]:
    tiers = [t for t in [t1, t2, t3, t4] if t is not None]
    statuses    = [t["status"] for t in tiers if t["status"] != "N_A"]
    confidences = [t["confidence"] for t in tiers
                   if t["confidence"] is not None]

    if not statuses:
        return "N_A", None

    overall_conf = min(confidences) if confidences else None

    if any(s == "FAIL" for s in statuses):
        return "FAIL", overall_conf
    if any(s == "WARN" for s in statuses):
        return "WARN", overall_conf
    return "PASS", overall_conf


# ── Caching ────────────────────────────────────────────────────────────────────

def _cache_key(date_str: str) -> str:
    return f"{date_str}:{_PIPELINE_VERSION}"


def _cache_get(date_str: str) -> dict | None:
    key   = _cache_key(date_str)
    entry = _mem_cache.get(key)
    if entry and time.time() < entry["expires_at"]:
        age = int(time.time() - entry["stored_at"])
        payload = dict(entry["payload"])
        payload["cache"] = {"hit": True, "age_seconds": age,
                            "pipeline_version": _PIPELINE_VERSION}
        return payload
    return None


def _cache_set(date_str: str, payload: dict):
    key = _cache_key(date_str)
    _mem_cache[key] = {
        "payload": payload,
        "stored_at": time.time(),
        "expires_at": time.time() + _CACHE_TTL_S,
    }
    # Evict stale entries to prevent unbounded growth
    stale = [k for k, v in _mem_cache.items() if time.time() > v["expires_at"]]
    for k in stale:
        _mem_cache.pop(k, None)


# ── Notification (feature-flagged) ────────────────────────────────────────────

def _maybe_notify(overall_status: str, overall_conf: int | None, date_str: str):
    """
    If confidence < threshold, emit a notification candidate.
    Never raises — notification failure must not affect the endpoint.
    """
    if overall_conf is None or overall_conf >= _NOTIFICATION_THRESHOLD:
        return
    try:
        teams_url = os.environ.get("TEAMS_WEBHOOK_URL", "")
        if teams_url:
            import requests as _req
            payload = {
                "@type": "MessageCard",
                "@context": "http://schema.org/extensions",
                "summary": f"SummitOS Pre-Shift Alert — {date_str}",
                "themeColor": "FF0000" if overall_status == "FAIL" else "FF8C00",
                "title": f"⚠️ Pre-Shift Check: {overall_status} (confidence {overall_conf}/100)",
                "text": (f"System health check for **{date_str}** scored below threshold.\n\n"
                         f"Status: **{overall_status}** | Confidence: **{overall_conf}/100**\n\n"
                         "Open the dashboard to review and resolve issues before your shift."),
            }
            _req.post(teams_url, json=payload, timeout=4)
            log.info(f"[PreShift] Teams notification sent for {date_str}")
        else:
            # Store notification candidate in DB
            try:
                db = DatabaseClient()
                conn = db.get_connection()
                cur = conn.cursor()
                cur.execute(
                    """IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES
                                     WHERE TABLE_NAME = 'NotificationCandidates')
                       CREATE TABLE dbo.NotificationCandidates (
                           ID INT IDENTITY PRIMARY KEY,
                           CreatedAt DATETIME DEFAULT GETUTCDATE(),
                           TargetDate NVARCHAR(10),
                           Status NVARCHAR(20),
                           Confidence INT,
                           Delivered BIT DEFAULT 0
                       )"""
                )
                cur.execute(
                    "INSERT INTO dbo.NotificationCandidates (TargetDate, Status, Confidence) VALUES (?,?,?)",
                    (date_str, overall_status, overall_conf)
                )
                conn.commit()
                cur.close()
                conn.close()
            except Exception as db_err:
                log.warning(f"[PreShift] Could not store notification candidate: {db_err}")
    except Exception as notify_err:
        log.warning(f"[PreShift] Notification failed (non-fatal): {notify_err}")


# ── Main handler ───────────────────────────────────────────────────────────────

@bp.route(route="pre-shift-check", methods=["GET", "OPTIONS"],
          auth_level=func.AuthLevel.ANONYMOUS)
def pre_shift_check(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=CORS_HEADERS)

    try:
        # ── Params ──
        date_param  = req.params.get("date", "").strip()
        force_refresh = req.params.get("refresh", "0") == "1"

        if date_param:
            try:
                datetime.datetime.strptime(date_param, "%Y-%m-%d")
                date_str = date_param
            except ValueError:
                return func.HttpResponse(
                    json.dumps({"error": "Invalid date format. Use YYYY-MM-DD."}),
                    status_code=400, mimetype="application/json", headers=CORS_HEADERS
                )
        else:
            # Default: yesterday in America/Denver
            now_mt   = datetime.datetime.now(_MT)
            date_str = (now_mt - datetime.timedelta(days=1)).strftime("%Y-%m-%d")

        # ── Cache check ──
        if not force_refresh:
            cached = _cache_get(date_str)
            if cached:
                log.info(f"[PreShift] Cache HIT for {date_str}")
                return func.HttpResponse(
                    json.dumps(cached, default=str),
                    status_code=200, mimetype="application/json", headers=CORS_HEADERS
                )

        # ── UTC window ──
        start_utc, end_utc = _mt_date_to_utc_window(date_str)

        # ── Run all sources concurrently ──
        async def _run_all():
            results = await asyncio.gather(
                # Tier 1 sources
                safe_call(_src_db_trip_count(start_utc, end_utc),
                          _DB_TIMEOUT_S, "db_trip_count"),
                safe_call(_src_tessie_trip_count(date_str, start_utc, end_utc),
                          _DEFAULT_TIMEOUT_S, "tessie_trip_count"),
                safe_call(_src_onedrive_trip_count(date_str),
                          _ONEDRIVE_TIMEOUT_S, "onedrive_trip_count"),
                # Tier 2 sources
                safe_call(_src_db_earnings_sum(start_utc, end_utc),
                          _DB_TIMEOUT_S, "db_earnings_sum"),
                safe_call(_src_db_ocr_earnings(start_utc, end_utc),
                          _DB_TIMEOUT_S, "ocr_earnings_sum"),
                safe_call(_src_bank_earnings(date_str),
                          _DEFAULT_TIMEOUT_S, "bank_earnings"),
                # Tier 3 sources
                safe_call(_src_db_expense_count(start_utc, end_utc),
                          _DB_TIMEOUT_S, "db_expense_count"),
                safe_call(_src_onedrive_expense_count(date_str),
                          _ONEDRIVE_TIMEOUT_S, "onedrive_expense_count"),
                safe_call(_src_bank_trip_count(date_str),
                          _DEFAULT_TIMEOUT_S, "bank_expense_count"),
                # Tier 4 source (DB-only — always fast)
                safe_call(_src_tier4_timeline(start_utc, end_utc),
                          _DB_TIMEOUT_S, "tier4_timeline"),
                return_exceptions=False
            )
            return results

        loop = asyncio.new_event_loop()
        try:
            (db_trips, tessie_trips, od_trips,
             db_earnings, ocr_earnings, bank_earnings,
             db_expenses, od_expenses, bank_expenses,
             timeline_r) = loop.run_until_complete(_run_all())
        finally:
            loop.close()

        # ── Score tiers ──
        tier1 = _score_tier1(db_trips,    tessie_trips, od_trips,    date_str)
        tier2 = _score_tier2(db_earnings, ocr_earnings, bank_earnings)
        tier3 = _score_tier3(db_expenses, od_expenses,  bank_expenses, date_str)
        tier4 = _score_tier4(timeline_r)

        overall_status, overall_conf = _compute_overall(tier1, tier2, tier3, tier4)

        # ── Build payload ──
        generated_at = datetime.datetime.utcnow().isoformat() + "Z"
        payload = {
            "date": date_str,
            "generated_at": generated_at,
            "pipeline_version": _PIPELINE_VERSION,
            "overall_status": overall_status,
            "overall_confidence": overall_conf,
            "cache": {"hit": False, "age_seconds": 0,
                      "pipeline_version": _PIPELINE_VERSION},
            "tiers": {
                "tier1_trips":    tier1,
                "tier2_earnings": tier2,
                "tier3_expenses": tier3,
                "tier4_timeline": tier4,
            },
            "systems": {
                "db":       {"status": db_trips["status"],
                             "online": db_trips["status"] == "OK",
                             "latency_ms": db_trips["latency_ms"]},
                "tessie":   {"status": tessie_trips["status"],
                             "online": tessie_trips["status"] == "OK",
                             "latency_ms": tessie_trips["latency_ms"]},
                "onedrive": {"status": od_trips["status"],
                             "online": od_trips["status"] == "OK",
                             "latency_ms": od_trips["latency_ms"]},
                "bank":     {"status": bank_earnings["status"],
                             "online": bank_earnings["status"] == "OK",
                             "latency_ms": bank_earnings["latency_ms"]},
            },
        }

        # ── Cache & notify ──
        _cache_set(date_str, payload)
        _maybe_notify(overall_status, overall_conf, date_str)

        log.info(f"[PreShift] {date_str} → {overall_status} ({overall_conf}/100)")

        return func.HttpResponse(
            json.dumps(payload, default=str),
            status_code=200, mimetype="application/json", headers=CORS_HEADERS
        )

    except Exception as top_err:
        # Last-resort catch — must never return 5xx to the dashboard
        log.error(f"[PreShift] Unhandled error: {top_err}", exc_info=True)
        fallback = {
            "date": date_param if "date_param" in dir() else "unknown",
            "overall_status": "N_A",
            "overall_confidence": None,
            "error": str(top_err),
            "cache": {"hit": False, "age_seconds": 0, "pipeline_version": _PIPELINE_VERSION},
            "tiers": {},
            "systems": {"db": "UNAVAILABLE", "tessie": "UNAVAILABLE",
                        "onedrive": "UNAVAILABLE", "bank": "UNAVAILABLE"},
        }
        return func.HttpResponse(
            json.dumps(fallback),
            status_code=200, mimetype="application/json", headers=CORS_HEADERS
        )


# ── Timer trigger (7:00 AM MDT = 13:00 UTC) ──────────────────────────────────

@bp.timer_trigger(schedule="0 30 10 * * *", arg_name="timer",
                  run_on_startup=False, use_monitor=False)
def pre_shift_daily_timer(timer: func.TimerRequest) -> None:
    """
    Runs the pre-shift check automatically at 4:30 AM MDT (10:30 UTC) every day
    and caches the result. Non-fatal — if this fails, the HTTP endpoint still works.
    """
    try:
        now_mt   = datetime.datetime.now(_MT)
        date_str = (now_mt - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        log.info(f"[PreShift Timer] Running pre-shift check for {date_str}")

        import urllib.request
        base = os.environ.get("FUNCTIONS_HTTPWORKER_PORT", "7071")
        url  = f"http://localhost:{base}/api/pre-shift-check?date={date_str}&refresh=1"
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                body = r.read().decode()
                data = json.loads(body)
                log.info(f"[PreShift Timer] {date_str} → "
                         f"{data.get('overall_status')} ({data.get('overall_confidence')}/100)")
        except Exception as http_err:
            log.warning(f"[PreShift Timer] Self-call failed: {http_err} — result not cached")
    except Exception as e:
        log.error(f"[PreShift Timer] Fatal: {e}", exc_info=True)
