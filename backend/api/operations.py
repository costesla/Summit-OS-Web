import logging
import azure.functions as func
import json
import os
import threading
from datetime import datetime, timedelta
from services.graph import GraphClient
from services.auth_guard import cors_headers as _get_cors
from services.tessie_sync import TessieSyncService
from services.cloud_watcher import CloudWatcherService
from services.job_tracker import JobTracker

def calendar_week_of_month(dt: datetime) -> int:
    """
    Returns the calendar week number within the month, anchored on Monday.
    Week 1 = the Mon-Sun span that contains the 1st of the month.
    Any days before the first Monday are also Week 1.
    Example: May 2026 (May 1=Fri) → first Monday=May 4
      May 1-10 = Week 1, May 11-17 = Week 2, etc.
    """
    first = dt.replace(day=1)
    # Days until the first Monday (0 if Monday)
    days_to_monday = (7 - first.weekday()) % 7
    first_monday = first + timedelta(days=days_to_monday)
    
    if dt.date() < first_monday.date():
        return 1  # partial week before the first Monday
        
    # If the month starts on a Monday, the first week is Week 1.
    # Otherwise, the first full week (starting on Monday) is Week 2.
    offset = 1 if first_monday.day == 1 else 2
    return (dt.day - first_monday.day) // 7 + offset

bp = func.Blueprint()

def _cors(req: func.HttpRequest) -> dict:
    return _get_cors(req)

def run_async_job(tool_name: str, task_func, *args, **kwargs) -> dict:
    tracker = JobTracker()
    
    # Extract target_path safely for B4 logging and SQLite job tracking
    target_path = None
    if "explicit_path" in kwargs and kwargs["explicit_path"]:
        target_path = kwargs["explicit_path"]
    elif "path" in kwargs and kwargs["path"]:
        target_path = kwargs["path"]
    elif "process_date_str" in kwargs and kwargs["process_date_str"]:
        target_path = kwargs["process_date_str"]
    elif "target_date" in kwargs and kwargs["target_date"]:
        target_path = kwargs["target_date"]
    elif "date_str" in kwargs and kwargs["date_str"]:
        target_path = kwargs["date_str"]
    elif "target_date_str" in kwargs and kwargs["target_date_str"]:
        target_path = kwargs["target_date_str"]
    elif len(args) > 0 and isinstance(args[0], str):
        target_path = args[0]
        
    job_id = tracker.create_job(tool_name, target_path)
    
    def worker():
        try:
            # B1/B4: Transition queued -> running (starts job logs + emits job_started event)
            tracker.start_job(job_id)
            
            # Call the synchronous task function
            result = task_func(*args, **kwargs)
            
            # Update job as completed with results and logs
            logs = []
            if isinstance(result, dict):
                logs = result.get("logs", [])
                
            tracker.update_job_progress(job_id, "completed", logs, result=result)
            
        except Exception as e:
            logging.error(f"Error in background job {job_id} ({tool_name}): {e}")
            tracker.update_job_progress(
                job_id, 
                "failed", 
                [f"> [CRITICAL] Background job failed: {str(e)}"], 
                error=str(e)
            )
            
    thread = threading.Thread(target=worker)
    thread.daemon = True
    thread.start()
    
    # C1 Standard Async Response Schema
    return {
        "status": "accepted",
        "execution": "async",
        "jobId": job_id,
        "errorType": None
    }

@bp.route(route="job-status/{job_id}", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def get_job_status(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_cors(req))
        
    job_id = req.route_params.get("job_id")
    tracker = JobTracker()
    job_data = tracker.get_job(job_id)
    
    if not job_data:
        return func.HttpResponse(
            json.dumps({
                "status": "error",
                "execution": "sync",
                "errorType": "NotFoundError",
                "message": "Job not found"
            }),
            status_code=404,
            headers=_cors(req),
            mimetype="application/json"
        )
        
    return func.HttpResponse(
        json.dumps(job_data),
        status_code=200,
        headers=_cors(req),
        mimetype="application/json"
    )

def _execute_sync_folders(process_date_str: str = None, dry_run: bool = False) -> dict:
    logs = []
    dt = datetime.strptime(process_date_str, "%Y-%m-%d") if process_date_str else datetime.now()
    year = dt.strftime("%Y")
    month = dt.strftime("%B")
    day = dt.strftime("%d")
    
    # Calendar week: Mon-Sun, Week 1 anchored on first Monday of month
    week_num = calendar_week_of_month(dt)
    week_folder = f"Week {week_num}"

    # Standardized folder name: M.DD.YY (e.g. 5.01.26)
    short_year = dt.strftime("%y")
    month_num = dt.month
    day_padded = dt.strftime("%d")
    folder_name = f"{month_num}.{day_padded}.{short_year}"

    full_path = f"Uber Driver/{year}/{month}/{week_folder}/{folder_name}"
    
    if dry_run:
        logs.append(f"[INFO] MODE: Dry Run")
        logs.append(f"[INFO] Target Path: {full_path}")
        logs.append(f"[SUCCESS] Would create directory if missing.")
        return {"success": True, "logs": logs}
    else:
        logs.append(f"[INFO] MODE: Live Sync")
        logs.append(f"[INFO] Target user: peter.teehan@costesla.com")
        logs.append(f"[INFO] Ensuring OneDrive path exists: {full_path}")
        graph = GraphClient()
        segment_logs = []
        import logging as _logging
        class _ListHandler(_logging.Handler):
            def emit(self, record):
                msg = self.format(record)
                if "[FOUND]" in msg or "[CREATED]" in msg or "ensure_path" in msg:
                    segment_logs.append(msg)
        _handler = _ListHandler()
        _logging.getLogger().addHandler(_handler)
        try:
            folder_id = graph.ensure_path_exists(full_path)
        finally:
            _logging.getLogger().removeHandler(_handler)
        logs.extend(segment_logs)
        logs.append(f"[SUCCESS] OneDrive folder ready \u2192 {folder_id}")

        return {"success": True, "logs": logs}

@bp.route(route="operations/sync-folders", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def sync_folders(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_cors(req))

    try:
        data = req.get_json()
        process_date_str = data.get("processDate")
        dry_run = data.get("dryRun", False)
        
        # Async-First Wrapper
        result = run_async_job(
            "OneDrive Folder Sync",
            _execute_sync_folders,
            process_date_str=process_date_str,
            dry_run=dry_run
        )
        
        return func.HttpResponse(
            json.dumps(result),
            status_code=202,
            headers=_cors(req),
            mimetype="application/json"
        )
    except Exception as e:
        logging.error(f"Sync Folders Error: {e}")
        return func.HttpResponse(
            json.dumps({
                "status": "error",
                "execution": "sync",
                "errorType": "SetupError",
                "message": str(e)
            }),
            status_code=500,
            headers=_cors(req),
            mimetype="application/json"
        )

@bp.route(route="operations/trigger-cloud-scan", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def trigger_cloud_scan(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_cors(req))

    try:
        data = req.get_json() if req.get_body() else {}
        target_date = data.get("date")
        explicit_path = data.get("path")
        
        service = CloudWatcherService()
        
        # Async-First Wrapper
        result = run_async_job(
            "Unified Cloud Scan",
            service.scan_and_route,
            target_date=target_date,
            explicit_path=explicit_path
        )
        
        return func.HttpResponse(
            json.dumps(result),
            status_code=202,
            headers=_cors(req),
            mimetype="application/json"
        )
    except Exception as e:
        logging.error(f"Trigger Cloud Scan Error: {e}")
        return func.HttpResponse(
            json.dumps({
                "status": "error",
                "execution": "sync",
                "errorType": "SetupError",
                "message": str(e)
            }),
            status_code=500,
            headers=_cors(req),
            mimetype="application/json"
        )

@bp.route(route="operations/scan-day-trips", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def scan_day_trips(req: func.HttpRequest) -> func.HttpResponse:
    """OCRs all screenshots in a day's OneDrive folder, sorts by trip time,
    and saves numbered TRIP-{YYYYMMDD}-{N} records to Rides.Rides."""
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_cors(req))
    try:
        data = req.get_json() if req.get_body() else {}
        date_str = data.get("date")
        explicit_path = data.get("path")
        if not date_str:
            return func.HttpResponse(
                json.dumps({"success": False, "error": "date is required (YYYY-MM-DD)"}),
                status_code=400, headers=_cors(req), mimetype="application/json"
            )
        service = CloudWatcherService()
        
        # Async-First Wrapper
        result = run_async_job(
            "OCR Trip Ingestion",
            service.scan_and_number_trips,
            date_str,
            explicit_path=explicit_path
        )
        
        return func.HttpResponse(
            json.dumps(result),
            status_code=202, headers=_cors(req), mimetype="application/json"
        )
    except Exception as e:
        logging.error(f"Scan Day Trips Error: {e}")
        return func.HttpResponse(
            json.dumps({
                "status": "error",
                "execution": "sync",
                "errorType": "SetupError",
                "message": str(e)
            }),
            status_code=500, headers=_cors(req), mimetype="application/json"
        )

@bp.route(route="operations/get-day-trips", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def get_day_trips(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_cors(req))
    try:
        date_str = req.params.get("date")
        if not date_str:
            return func.HttpResponse(json.dumps({"success": False, "error": "date is required"}), status_code=400, headers=_cors(req), mimetype="application/json")
        
        service = CloudWatcherService()
        trips = service.get_trips_for_date(date_str)
        
        return func.HttpResponse(
            json.dumps({"success": True, "trips": trips}),
            status_code=200, headers=_cors(req), mimetype="application/json"
        )
    except Exception as e:
        logging.error(f"Get Day Trips Error: {e}")
        return func.HttpResponse(json.dumps({"success": False, "error": str(e)}), status_code=500, headers=_cors(req), mimetype="application/json")

@bp.route(route="operations/scrub-day", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def scrub_day(req: func.HttpRequest) -> func.HttpResponse:
    """
    Wipes all pipeline-generated records for a given date so the day can be
    rescanned cleanly from scratch.

    Deletes:
      - All TRIP-{YYYYMMDD}-* records (Uber + Private receipt extractions)

    Resets (back to Untagged) any TESSIE drives on that date whose Classification
    was set by the scan pipeline:
      - Uber_Matched, Uber_Pickup, Private_Trip, Private_Pickup

    Preserves:
      - INV-* booking records (real customer bookings)
      - Manual Tessie tags: Jackie, Daniel, Esmeralda, and any other human-applied tags
    """
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_cors(req))
    try:
        data = req.get_json() if req.get_body() else {}
        date_str = data.get("date")
        if not date_str:
            return func.HttpResponse(
                json.dumps({"success": False, "error": "date is required (YYYY-MM-DD)"}),
                status_code=400, headers=_cors(req), mimetype="application/json"
            )

        import datetime
        try:
            dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            return func.HttpResponse(
                json.dumps({"success": False, "error": "Invalid date format. Use YYYY-MM-DD."}),
                status_code=400, headers=_cors(req), mimetype="application/json"
            )

        date_compact = date_str.replace("-", "")
        date_only = dt.date()

        from services.database import DatabaseClient
        db = DatabaseClient()
        conn = db.get_connection()
        cursor = conn.cursor()
        logs = []

        # 1. Delete all TRIP- records for this date
        cursor.execute(
            "DELETE FROM Rides.Rides WHERE RideID LIKE ?",
            (f"TRIP-{date_compact}-%",)
        )
        deleted_trips = cursor.rowcount
        logs.append(f"SCRUB: Deleted {deleted_trips} TRIP-{date_compact}-* records")

        # 2. Reset pipeline-applied Tessie drive classifications back to Untagged.
        #    Only touch classifications that the scan pipeline writes — never human tags.
        pipeline_classifications = ('Uber_Matched', 'Uber_Pickup', 'Private_Trip', 'Private_Pickup')
        placeholders = ",".join("?" for _ in pipeline_classifications)
        cursor.execute(f"""
            UPDATE Rides.Rides
            SET TripType = NULL,
                Classification = 'Untagged',
                LastUpdated = GETUTCDATE()
            WHERE RideID LIKE 'TESSIE-%'
              AND CAST(Timestamp_Start AS DATE) = ?
              AND Classification IN ({placeholders})
        """, (date_only, *pipeline_classifications))
        reset_drives = cursor.rowcount
        logs.append(f"SCRUB: Reset {reset_drives} Tessie drive(s) to Untagged on {date_str}")

        conn.commit()
        cursor.close()
        conn.close()

        logs.append(f"SCRUB COMPLETE: {date_str} is clean. Upload Uber screenshots to OneDrive then hit Scan Day.")
        logging.info(f"Scrub Day {date_str}: {deleted_trips} TRIP records deleted, {reset_drives} Tessie drives reset.")

        return func.HttpResponse(
            json.dumps({"success": True, "date": date_str, "deleted_trips": deleted_trips, "reset_drives": reset_drives, "logs": logs}),
            status_code=200, headers=_cors(req), mimetype="application/json"
        )
    except Exception as e:
        logging.error(f"Scrub Day Error: {e}")
        return func.HttpResponse(
            json.dumps({"success": False, "error": str(e)}),
            status_code=500, headers=_cors(req), mimetype="application/json"
        )



@bp.route(route="operations/scan-day-expenses", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def scan_day_expenses(req: func.HttpRequest) -> func.HttpResponse:
    """Scans and extracts expense receipts from OneDrive daily folders, saving them to SQL and Vector Store."""
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_cors(req))
    try:
        data = req.get_json() if req.get_body() else {}
        date_str = data.get("date")
        explicit_path = data.get("path")
        if not date_str:
            return func.HttpResponse(
                json.dumps({"success": False, "error": "date is required (YYYY-MM-DD)"}),
                status_code=400, headers=_cors(req), mimetype="application/json"
            )
        service = CloudWatcherService()
        
        # Async-First Wrapper
        result = run_async_job(
            "Expense Receipt Ingestion",
            service.scan_and_log_expenses,
            date_str,
            explicit_path=explicit_path
        )
        
        return func.HttpResponse(
            json.dumps(result),
            status_code=202, headers=_cors(req), mimetype="application/json"
        )
    except Exception as e:
        logging.error(f"Scan Day Expenses Error: {e}")
        return func.HttpResponse(
            json.dumps({
                "status": "error",
                "execution": "sync",
                "errorType": "SetupError",
                "message": str(e)
            }),
            status_code=500, headers=_cors(req), mimetype="application/json"
        )

@bp.route(route="operations/upload-screenshot", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def upload_screenshot(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_cors(req))
    
    try:
        file = req.files.get("file")
        if not file:
            return func.HttpResponse(json.dumps({"success": False, "error": "No file provided"}), status_code=400, headers=_cors(req), mimetype="application/json")
        
        filename = file.filename
        image_bytes = file.read()
        
        from services.uber_matcher import UberMatcherService
        matcher = UberMatcherService()
        result = matcher.process_image_bytes(image_bytes, filename)
        
        return func.HttpResponse(
            json.dumps({"success": result.get("status") == "MATCHED", "result": result}),
            status_code=200,
            headers=_cors(req),
            mimetype="application/json"
        )
    except Exception as e:
        logging.error(f"Upload Screenshot Error: {e}")
        return func.HttpResponse(
            json.dumps({"success": False, "error": str(e)}),
            status_code=500,
            headers=_cors(req),
            mimetype="application/json"
        )

def _execute_daily_sync(target_date_str: str = None) -> dict:
    logs = []
    
    if target_date_str:
        now = datetime.strptime(target_date_str, "%Y-%m-%d")
        logs.append(f"[INFO] Targeted Daily Sync for {target_date_str}")
    else:
        now = datetime.now()
        logs.append(f"[INFO] Standard Daily Sync for {now.strftime('%Y-%m-%d')}")
    year = now.strftime("%Y")
    month = now.strftime("%B")
    day = now.strftime("%d")
    
    # Calendar week: Mon-Sun, Week 1 anchored on first Monday of month
    week_num = calendar_week_of_month(now)
    week_folder = f"Week {week_num}"
    
    # 1. Ensure OneDrive Folders Exist
    try:
        graph = GraphClient()
        short_year = now.strftime("%y")
        month_num = now.month
        day_padded = now.strftime("%d")
        folder_name = f"{month_num}.{day_padded}.{short_year}"
        
        full_path = f"Uber Driver/{year}/{month}/{week_folder}/{folder_name}"
        logs.append(f"[INFO] Ensuring OneDrive path exists: {full_path}")
        
        folder_id = graph.ensure_path_exists(full_path)
        logs.append(f"[SUCCESS] OneDrive folder verified: {folder_id}")
    except Exception as ge:
        logging.error(f"OneDrive Folder Error: {ge}")
        logs.append(f"[ERROR] OneDrive Folder Error: {str(ge)}")

    # 2. Sync Tessie Telemetry
    try:
        target_date = now.strftime("%Y-%m-%d")
        logs.append(f"[INFO] Syncing Tessie telemetry for {target_date}...")
        t_sync = TessieSyncService()
        t_result = t_sync.sync_day(target_date=target_date)
        logs.append(f"[SUCCESS] Tessie Sync: {t_result.get('drives_saved', 0)} drives, {t_result.get('charges_saved', 0)} charges saved.")
    except Exception as te:
        logging.error(f"Tessie Sync Error: {te}")
        logs.append(f"[ERROR] Tessie Sync Error: {str(te)}")

    # 3. Banking Sync — DISABLED (manual expense entry only)
    logs.append(f"[SKIP] Banking Auto-Sync disabled — use manual expense entry on dashboard.")

    # 4. Integrated Cloud Scan (Match screenshots to drives)
    try:
        logs.append(f"[INFO] Running Cloud Scan for {target_date_str or now.strftime('%Y-%m-%d')}...")
        cw_service = CloudWatcherService()
        scan_result = cw_service.scan_and_number_trips(target_date_str or now.strftime('%Y-%m-%d'))
        if scan_result.get("success"):
            logs.append(f"[SUCCESS] Cloud Scan: {len(scan_result.get('trips', []))} trips matched/updated.")
            logs.extend(scan_result.get("logs", []))
        else:
            logs.append(f"[WARNING] Cloud Scan Notice: {scan_result.get('error')}")
    except Exception as sce:
        logging.error(f"Cloud Scan Error: {sce}")
        logs.append(f"[ERROR] Cloud Scan Error: {str(sce)}")
    
    # 5. Integrated Expense Scanning (Identify and parse receipts)
    try:
        target_date = target_date_str or now.strftime('%Y-%m-%d')
        logs.append(f"[INFO] Running Expense Receipt Scan for {target_date}...")
        cw_service = CloudWatcherService()
        expense_result = cw_service.scan_and_log_expenses(target_date)
        if expense_result.get("success"):
            logs.append(f"[SUCCESS] Expense Scan: {expense_result.get('expense_count', 0)} receipts scanned, total ${expense_result.get('total_amount', 0.0):.2f}")
            logs.extend(expense_result.get("logs", []))
        else:
            logs.append(f"[WARNING] Expense Scan Notice: {expense_result.get('error')}")
    except Exception as ece:
        logging.error(f"Expense Scan Error: {ece}")
        logs.append(f"[ERROR] Expense Scan Error: {str(ece)}")

    return {
        "success": True,
        "message": "Daily Sync completed in the Cloud",
        "logs": logs
    }

@bp.route(route="daily-sync", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def daily_sync(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_cors(req))
        
    logging.info("Cloud Daily Sync Triggered")
    
    try:
        data = req.get_json() if req.get_body() else {}
        target_date_str = data.get("date") or data.get("processDate")
        
        # Async-First Wrapper
        result = run_async_job(
            "Daily Ingestion Sync",
            _execute_daily_sync,
            target_date_str=target_date_str
        )
        
        return func.HttpResponse(
            json.dumps(result),
            status_code=202,
            headers=_cors(req),
            mimetype="application/json"
        )
    except Exception as e:
        logging.error(f"Daily Sync Root Error: {e}")
        return func.HttpResponse(
            json.dumps({
                "status": "error",
                "execution": "sync",
                "errorType": "SetupError",
                "message": str(e)
            }),
            status_code=500,
            headers=_cors(req),
            mimetype="application/json"
        )

@bp.route(route="operations/screenshot-url", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def screenshot_url(req: func.HttpRequest) -> func.HttpResponse:
    """Resolves a screenshot filename + date to a OneDrive web URL."""
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_cors(req))

    try:
        date_str = req.params.get("date")
        filename = req.params.get("filename")

        if not date_str or not filename:
            return func.HttpResponse(
                json.dumps({"success": False, "error": "date (YYYY-MM-DD) and filename are required"}),
                status_code=400, headers=_cors(req), mimetype="application/json"
            )

        # Build the OneDrive path using the same logic as _execute_sync_folders
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        year = dt.strftime("%Y")
        month = dt.strftime("%B")
        week_num = calendar_week_of_month(dt)
        week_folder = f"Week {week_num}"
        short_year = dt.strftime("%y")
        month_num = dt.month
        day_padded = dt.strftime("%d")
        folder_name = f"{month_num}.{day_padded}.{short_year}"
        full_path = f"Uber Driver/{year}/{month}/{week_folder}/{folder_name}/{filename}"

        graph = GraphClient()
        item = graph.get_item_by_path(full_path)

        if not item:
            return func.HttpResponse(
                json.dumps({"success": False, "error": "File not found"}),
                status_code=404, headers=_cors(req), mimetype="application/json"
            )

        return func.HttpResponse(
            json.dumps({
                "success": True,
                "url": item.get("webUrl"),
                "downloadUrl": item.get("@microsoft.graph.downloadUrl")
            }),
            status_code=200, headers=_cors(req), mimetype="application/json"
        )
    except ValueError:
        return func.HttpResponse(
            json.dumps({"success": False, "error": "Invalid date format. Use YYYY-MM-DD."}),
            status_code=400, headers=_cors(req), mimetype="application/json"
        )
    except Exception as e:
        logging.error(f"Screenshot URL Error: {e}")
        return func.HttpResponse(
            json.dumps({"success": False, "error": str(e)}),
            status_code=500, headers=_cors(req), mimetype="application/json"
        )
