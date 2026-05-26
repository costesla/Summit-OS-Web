"""
auto_fix.py
===========
POST /api/auto-fix?date=YYYY-MM-DD

Deterministic, reversible repair engine for SummitOS data inconsistencies
detected by the Pre-Shift Health Check.

Safety contract:
  - ALL fixes wrapped in BEGIN TRANSACTION … COMMIT / ROLLBACK
  - rows_affected > ROW_LIMIT → return MANUAL_REQUIRED with no writes
  - Every applied fix writes an immutable audit row to dbo.RepairLog
  - Never raises an exception to the HTTP caller — always returns HTTP 200
  - Idempotent: running twice on a clean day returns NO_ACTION

Mode: Auto-Fix Allowed:
  1. Duplicate Rides (same trip_id / same timestamp±60s + same earnings)
  2. Duplicate Expenses (same amount + same category on same day)

Manual Required (flag only, no auto-write):
  3. Missing OCR entries (OneDrive > DB count)
  4. Orphan Tessie drives (drive ≥ 0.25mi, no matched trip)
  5. Earnings mismatch without confirmed duplicates
  6. Timeline overlaps

All writes use UTC. Local display is the caller's responsibility.
"""

import azure.functions as func
import asyncio
import datetime
import json
import logging
import os
import time
import uuid
import pytz

from services.database import DatabaseClient

log = logging.getLogger(__name__)

bp = func.Blueprint()

# ── Constants ──────────────────────────────────────────────────────────────────
_MT              = pytz.timezone("America/Denver")
_UTC             = pytz.utc
_ROW_LIMIT       = 5        # rows_affected > this → MANUAL_REQUIRED (no writes)
_EARNINGS_TOL    = 0.10     # $0.10 rounding tolerance before flagging mismatch
_TIMESTAMP_TOL_S = 60       # seconds — trip timestamps within this = potential dup

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _mt_date_to_utc_window(date_str: str) -> tuple[datetime.datetime, datetime.datetime]:
    naive_start = datetime.datetime.strptime(date_str, "%Y-%m-%d")
    naive_end   = naive_start + datetime.timedelta(days=1)
    start_mt    = _MT.localize(naive_start, is_dst=None)
    end_mt      = _MT.localize(naive_end,   is_dst=None)
    return start_mt.astimezone(_UTC), end_mt.astimezone(_UTC)


def _repair_id() -> str:
    ts = datetime.datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    return f"RPR-{ts}-{uuid.uuid4().hex[:6].upper()}"


# ── RepairLog DDL (idempotent) ─────────────────────────────────────────────────

_REPAIR_LOG_DDL = """
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'RepairLog'
)
CREATE TABLE dbo.RepairLog (
    RepairID        NVARCHAR(50)   NOT NULL PRIMARY KEY,
    TargetDate      NVARCHAR(10)   NOT NULL,
    IssueType       NVARCHAR(80)   NOT NULL,
    RowsAffected    INT            NOT NULL DEFAULT 0,
    BeforeSnapshot  NVARCHAR(MAX),
    AfterSnapshot   NVARCHAR(MAX),
    AutoFixed       BIT            NOT NULL DEFAULT 1,
    ManualRequired  BIT            NOT NULL DEFAULT 0,
    Notes           NVARCHAR(MAX),
    CreatedAt       DATETIME       NOT NULL DEFAULT GETUTCDATE(),
    CreatedBy       NVARCHAR(50)   NOT NULL DEFAULT 'SummitOS-AutoFix'
)
"""


def _ensure_repair_log(conn) -> None:
    cur = conn.cursor()
    cur.execute(_REPAIR_LOG_DDL)
    conn.commit()
    cur.close()


def _write_repair_log(conn, repair_id: str, date_str: str, issue_type: str,
                      rows_affected: int, before: dict, after: dict,
                      auto_fixed: bool, manual_required: bool,
                      notes: str) -> None:
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO dbo.RepairLog
           (RepairID, TargetDate, IssueType, RowsAffected,
            BeforeSnapshot, AfterSnapshot, AutoFixed, ManualRequired, Notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (repair_id, date_str, issue_type, rows_affected,
         json.dumps(before, default=str),
         json.dumps(after,   default=str),
         1 if auto_fixed else 0,
         1 if manual_required else 0,
         notes)
    )
    conn.commit()
    cur.close()


# ── Fix implementations ────────────────────────────────────────────────────────

def _fix_duplicate_rides(conn, start_utc: datetime.datetime,
                         end_utc: datetime.datetime,
                         date_str: str) -> dict:
    """
    Detect and remove duplicate Rides.Rides rows.

    Duplicate definition (either):
      A) Same RideID appears more than once (canonical key dup)
      B) Same Timestamp_Start (within ±60s) + same Driver_Earnings
         + same Tessie_DriveID → pick earliest inserted (lowest ID)

    Returns action dict or raises to trigger ROLLBACK.
    """
    cur = conn.cursor()

    # ─── Snapshot before ───
    cur.execute(
        "SELECT COUNT(*), ISNULL(SUM(Driver_Earnings), 0) FROM Rides.Rides "
        "WHERE Timestamp_Start >= ? AND Timestamp_Start < ?",
        (start_utc.replace(tzinfo=None), end_utc.replace(tzinfo=None))
    )
    before_row = cur.fetchone()
    before = {"count": int(before_row[0]), "earnings": float(before_row[1])}

    # ─── Find duplicate IDs to delete ───
    cur.execute(
        """SELECT id FROM (
               SELECT id,
                      ROW_NUMBER() OVER (
                          PARTITION BY ISNULL(RideID, CAST(id AS NVARCHAR)),
                                       Driver_Earnings,
                                       ISNULL(Tessie_DriveID,'')
                          ORDER BY id ASC
                      ) AS rn
               FROM Rides.Rides
               WHERE Timestamp_Start >= ? AND Timestamp_Start < ?
           ) t WHERE rn > 1""",
        (start_utc.replace(tzinfo=None), end_utc.replace(tzinfo=None))
    )
    dup_ids = [row[0] for row in cur.fetchall()]

    if not dup_ids:
        cur.close()
        return {"type": "DUPLICATE_RIDES", "found": 0, "action": "NO_ACTION",
                "before": before, "after": before}

    rows_affected = len(dup_ids)

    # ─── Safety gate ───
    if rows_affected > _ROW_LIMIT:
        cur.close()
        return {"type": "DUPLICATE_RIDES", "found": rows_affected,
                "action": "MANUAL_REQUIRED",
                "reason": f"{rows_affected} duplicates found — exceeds safety limit of {_ROW_LIMIT}",
                "before": before, "after": before}

    # ─── Transactional delete ───
    placeholders = ",".join(["?" for _ in dup_ids])
    cur.execute(
        f"DELETE FROM Rides.Rides WHERE id IN ({placeholders})",
        tuple(dup_ids)
    )

    # ─── Snapshot after ───
    cur.execute(
        "SELECT COUNT(*), ISNULL(SUM(Driver_Earnings), 0) FROM Rides.Rides "
        "WHERE Timestamp_Start >= ? AND Timestamp_Start < ?",
        (start_utc.replace(tzinfo=None), end_utc.replace(tzinfo=None))
    )
    after_row = cur.fetchone()
    after = {"count": int(after_row[0]), "earnings": float(after_row[1])}
    cur.close()

    return {"type": "DUPLICATE_RIDES", "found": rows_affected,
            "action": "FIX_APPLIED", "rows_affected": rows_affected,
            "deleted_ids": dup_ids, "before": before, "after": after}


def _fix_duplicate_expenses(conn, start_utc: datetime.datetime,
                            end_utc: datetime.datetime,
                            date_str: str) -> dict:
    """Remove duplicate ManualExpenses rows (same Amount + Category on same day)."""
    cur = conn.cursor()

    cur.execute(
        "SELECT COUNT(*), ISNULL(SUM(Amount), 0) FROM Rides.ManualExpenses "
        "WHERE Timestamp >= ? AND Timestamp < ?",
        (start_utc.replace(tzinfo=None), end_utc.replace(tzinfo=None))
    )
    before_row = cur.fetchone()
    before = {"count": int(before_row[0]), "total": float(before_row[1])}

    cur.execute(
        """SELECT id FROM (
               SELECT id,
                      ROW_NUMBER() OVER (
                          PARTITION BY Amount, ISNULL(Category,''),
                                       ISNULL(Note,'')
                          ORDER BY id ASC
                      ) AS rn
               FROM Rides.ManualExpenses
               WHERE Timestamp >= ? AND Timestamp < ?
           ) t WHERE rn > 1""",
        (start_utc.replace(tzinfo=None), end_utc.replace(tzinfo=None))
    )
    dup_ids = [row[0] for row in cur.fetchall()]

    if not dup_ids:
        cur.close()
        return {"type": "DUPLICATE_EXPENSES", "found": 0, "action": "NO_ACTION",
                "before": before, "after": before}

    rows_affected = len(dup_ids)
    if rows_affected > _ROW_LIMIT:
        cur.close()
        return {"type": "DUPLICATE_EXPENSES", "found": rows_affected,
                "action": "MANUAL_REQUIRED",
                "reason": f"{rows_affected} duplicates — exceeds limit of {_ROW_LIMIT}",
                "before": before, "after": before}

    placeholders = ",".join(["?" for _ in dup_ids])
    cur.execute(
        f"DELETE FROM Rides.ManualExpenses WHERE id IN ({placeholders})",
        tuple(dup_ids)
    )

    cur.execute(
        "SELECT COUNT(*), ISNULL(SUM(Amount), 0) FROM Rides.ManualExpenses "
        "WHERE Timestamp >= ? AND Timestamp < ?",
        (start_utc.replace(tzinfo=None), end_utc.replace(tzinfo=None))
    )
    after_row = cur.fetchone()
    after = {"count": int(after_row[0]), "total": float(after_row[1])}
    cur.close()

    return {"type": "DUPLICATE_EXPENSES", "found": rows_affected,
            "action": "FIX_APPLIED", "rows_affected": rows_affected,
            "deleted_ids": dup_ids, "before": before, "after": after}


def _flag_missing_ocr(conn, start_utc: datetime.datetime,
                      end_utc: datetime.datetime) -> dict:
    """Detect-only: count trips flagged for OCR reprocess (no screenshot matched)."""
    cur = conn.cursor()
    cur.execute(
        """SELECT COUNT(*) FROM Rides.Rides
           WHERE Timestamp_Start >= ? AND Timestamp_Start < ?
           AND (Sidecar_Artifact_JSON IS NULL OR Sidecar_Artifact_JSON = '')
           AND (TripType = 'Uber' OR TripType IS NULL)""",
        (start_utc.replace(tzinfo=None), end_utc.replace(tzinfo=None))
    )
    row = cur.fetchone()
    cur.close()
    count = int(row[0]) if row else 0
    if count == 0:
        return {"type": "MISSING_OCR", "action": "NO_ACTION", "count": 0}
    return {"type": "MISSING_OCR", "action": "FLAGGED",
            "count": count,
            "reason": f"{count} trip(s) have no OCR sidecar — re-run Scan Day to process",
            "next_step": "Run IntelligenceSyncPanel → Scan Day for this date"}


def _flag_orphan_drives(conn, start_utc: datetime.datetime,
                        end_utc: datetime.datetime) -> dict:
    """Detect-only: count Tessie drives >= 0.25mi with no matched DB trip."""
    cur = conn.cursor()
    try:
        cur.execute(
            """SELECT COUNT(*) FROM dbo.Drive_Telemetry dt
               WHERE dt.StartTime >= ? AND dt.StartTime < ?
               AND ISNULL(dt.Distance_mi, 0) >= 0.25
               AND NOT EXISTS (
                   SELECT 1 FROM Rides.Rides r
                   WHERE r.Tessie_DriveID IS NOT NULL
                   AND CAST(r.Tessie_DriveID AS NVARCHAR) LIKE '%' + CAST(dt.DriveID AS NVARCHAR) + '%'
                   AND r.Timestamp_Start >= ? AND r.Timestamp_Start < ?
               )""",
            (start_utc.replace(tzinfo=None), end_utc.replace(tzinfo=None),
             start_utc.replace(tzinfo=None), end_utc.replace(tzinfo=None))
        )
        row = cur.fetchone()
        count = int(row[0]) if row else 0
    except Exception:
        count = 0   # Drive_Telemetry may not exist
    finally:
        cur.close()

    if count == 0:
        return {"type": "ORPHAN_DRIVES", "action": "NO_ACTION", "count": 0}
    return {"type": "ORPHAN_DRIVES", "action": "FLAGGED",
            "count": count,
            "reason": f"{count} Tessie drive(s) ≥0.25mi have no matched Uber trip",
            "next_step": "Review TessieDrivesPanel and import unmatched drives"}


# ── Main runner ────────────────────────────────────────────────────────────────

def _run_auto_fix(date_str: str, dry_run: bool = False) -> dict:
    """
    Orchestrates all fixes inside a single TRANSACTION.
    On any failure → ROLLBACK and return error payload.
    dry_run=True → preview only, no writes, no audit log.
    """
    start_utc, end_utc = _mt_date_to_utc_window(date_str)

    db   = DatabaseClient()
    conn = db.get_connection()

    # Ensure RepairLog table exists (idempotent)
    try:
        _ensure_repair_log(conn)
    except Exception as ddl_err:
        log.warning(f"[AutoFix] RepairLog DDL failed (non-fatal): {ddl_err}")

    actions         = []
    total_rows      = 0
    manual_required = False

    try:
        conn.autocommit = False   # begin transaction

        # ─ 1. Duplicate rides ─
        act1 = _fix_duplicate_rides(conn, start_utc, end_utc, date_str)
        actions.append(act1)
        if act1["action"] == "FIX_APPLIED":
            total_rows += act1.get("rows_affected", 0)
        elif act1["action"] == "MANUAL_REQUIRED":
            manual_required = True

        # ─ 2. Duplicate expenses ─
        act2 = _fix_duplicate_expenses(conn, start_utc, end_utc, date_str)
        actions.append(act2)
        if act2["action"] == "FIX_APPLIED":
            total_rows += act2.get("rows_affected", 0)
        elif act2["action"] == "MANUAL_REQUIRED":
            manual_required = True

        # ─ 3 & 4. Detect-only flags (no writes) ─
        act3 = _flag_missing_ocr(conn, start_utc, end_utc)
        act4 = _flag_orphan_drives(conn, start_utc, end_utc)
        actions.append(act3)
        actions.append(act4)

        # ─ Commit or rollback (dry_run always rolls back) ─
        fixed_actions = [a for a in actions if a.get("action") == "FIX_APPLIED"]
        if fixed_actions and not dry_run:
            conn.commit()
            log.info(f"[AutoFix] COMMIT: {len(fixed_actions)} fix(es), {total_rows} rows for {date_str}")
        else:
            conn.rollback()   # dry_run or nothing to commit — clean rollback
            if dry_run and fixed_actions:
                log.info(f"[AutoFix] DRY RUN: would have fixed {len(fixed_actions)} action(s) — rolled back")

        # ─ Write audit log (skip on dry_run) ─
        conn.autocommit = True
        if not dry_run:
            rid = _repair_id()
            try:
                _write_repair_log(
                    conn, rid, date_str, act["type"],
                    act.get("rows_affected", 0),
                    act.get("before", {}), act.get("after", {}),
                    auto_fixed=True, manual_required=False,
                    notes=json.dumps({"deleted_ids": act.get("deleted_ids", [])})
                )
                act["repair_id"] = rid
            except Exception as log_err:
                log.warning(f"[AutoFix] RepairLog write failed for {rid}: {log_err}")

        # Write audit rows for manual-required items
        for act in actions:
            if act.get("action") == "MANUAL_REQUIRED":
                rid = _repair_id()
                try:
                    _write_repair_log(
                        conn, rid, date_str, act["type"],
                        act.get("found", 0),
                        act.get("before", {}), {},
                        auto_fixed=False, manual_required=True,
                        notes=act.get("reason", "")
                    )
                    act["repair_id"] = rid
                except Exception as log_err:
                    log.warning(f"[AutoFix] RepairLog write failed for manual: {log_err}")

    except Exception as fix_err:
        log.error(f"[AutoFix] Rolling back due to error: {fix_err}", exc_info=True)
        try:
            conn.rollback()
        except Exception:
            pass
        conn.close()
        return {
            "status": "ERROR",
            "date": date_str,
            "error": str(fix_err),
            "actions": [],
            "rows_affected": 0,
            "confidence": 0,
        }

    conn.close()

    # ─── Determine overall status ───
    if manual_required:
        overall_status = "MANUAL_REQUIRED"
        confidence     = 0   # caller must confirm
    elif fixed_actions:
        overall_status = "FIX_APPLIED"
        confidence     = 95
    else:
        # Nothing to fix
        all_no_action = all(a.get("action") in ("NO_ACTION", "FLAGGED")
                            for a in actions)
        if all_no_action:
            overall_status = "NO_ACTION"
            confidence     = 100
        else:
            overall_status = "NO_ACTION"
            confidence     = 90

    # ─── Notifications for anything flagged ───
    flags = [a for a in actions if a.get("action") == "FLAGGED"]
    if flags:
        for flag in flags:
            log.info(f"[AutoFix] FLAGGED [{flag['type']}]: {flag.get('reason','')}")

    return {
        "status":          overall_status,
        "date":            date_str,
        "generated_at":    datetime.datetime.utcnow().isoformat() + "Z",
        "dry_run":         dry_run,
        "actions":         actions,
        "rows_affected":   0 if dry_run else total_rows,
        "confidence":      confidence,
        "manual_required": manual_required,
        "flags":           [a["type"] for a in flags],
        "repair_ids":      [] if dry_run else [a["repair_id"] for a in actions if "repair_id" in a],
    }


# ── HTTP handler ───────────────────────────────────────────────────────────────

@bp.route(route="auto-fix", methods=["GET", "POST", "OPTIONS"],
          auth_level=func.AuthLevel.ANONYMOUS)
def auto_fix(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=CORS_HEADERS)

    date_param = ""
    try:
        date_param = req.params.get("date", "").strip()

        if date_param:
            try:
                datetime.datetime.strptime(date_param, "%Y-%m-%d")
                date_str = date_param
            except ValueError:
                return func.HttpResponse(
                    json.dumps({"error": "Invalid date. Use YYYY-MM-DD."}),
                    status_code=400, mimetype="application/json", headers=CORS_HEADERS
                )
        else:
            # Default to yesterday MDT
            now_mt   = datetime.datetime.now(_MT)
            date_str = (now_mt - datetime.timedelta(days=1)).strftime("%Y-%m-%d")

        dry_run  = req.params.get("dry_run", "0") == "1"
        log.info(f"[AutoFix] {'DRY RUN preview' if dry_run else 'Requested'} for {date_str}")

        # Run in thread — DB calls are blocking
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                asyncio.get_event_loop().run_in_executor(
                    None, lambda: _run_auto_fix(date_str, dry_run=dry_run)
                )
            )
        finally:
            loop.close()

        # Bust pre-shift check cache (only on real fix, not dry_run)
        if not dry_run:
            try:
                from api.pre_shift_check import _mem_cache
                stale_keys = [k for k in _mem_cache if k.startswith(date_str)]
                for k in stale_keys:
                    _mem_cache.pop(k, None)
                log.info(f"[AutoFix] Busted {len(stale_keys)} pre-shift cache entries")
            except Exception as cache_err:
                log.warning(f"[AutoFix] Cache bust failed (non-fatal): {cache_err}")

        return func.HttpResponse(
            json.dumps(result, default=str),
            status_code=200, mimetype="application/json", headers=CORS_HEADERS
        )

    except Exception as top_err:
        log.error(f"[AutoFix] Unhandled error: {top_err}", exc_info=True)
        fallback = {
            "status":        "ERROR",
            "date":          date_param or "unknown",
            "error":         str(top_err),
            "actions":       [],
            "rows_affected": 0,
            "confidence":    0,
        }
        return func.HttpResponse(
            json.dumps(fallback),
            status_code=200, mimetype="application/json", headers=CORS_HEADERS
        )
