import logging
import azure.functions as func
import json
import os
from datetime import datetime
from services.graph import GraphClient
from services.tessie_sync import TessieSyncService
from services.cloud_watcher import CloudWatcherService

bp = func.Blueprint()

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type"
}

@bp.route(route="operations/sync-folders", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def sync_folders(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=CORS_HEADERS)

    logs = []
    try:
        data = req.get_json()
        process_date_str = data.get("processDate")
        dry_run = data.get("dryRun", False)

        dt = datetime.strptime(process_date_str, "%Y-%m-%d") if process_date_str else datetime.now()
        year = dt.strftime("%Y")
        month = dt.strftime("%B")
        day = dt.strftime("%d")
        
        # Week calculation: (Day-1)//7 + 1
        week_num = (dt.day - 1) // 7 + 1
        week_folder = f"Week {week_num}"

        full_path = f"Uber Driver/{year}/{month}/{week_folder}/{day}"
        
        if dry_run:
            logs.append(f"[INFO] MODE: Dry Run")
            logs.append(f"[INFO] Target Path: {full_path}")
            logs.append(f"[SUCCESS] Would create directory if missing.")
            return func.HttpResponse(
                json.dumps({"success": True, "logs": logs}),
                status_code=200,
                headers=CORS_HEADERS,
                mimetype="application/json"
            )
        else:
            logs.append(f"[INFO] MODE: Live Sync")
            logs.append(f"[INFO] Ensuring OneDrive path exists: {full_path}")
            graph = GraphClient()
            folder_id = graph.ensure_path_exists(full_path)
            logs.append(f"[SUCCESS] OneDrive folder verified: {folder_id}")

            return func.HttpResponse(
                json.dumps({"success": True, "logs": logs}),
                status_code=200,
                headers=CORS_HEADERS,
                mimetype="application/json"
            )
    except Exception as e:
        logging.error(f"Sync Folders Error: {e}")
        return func.HttpResponse(
            json.dumps({"success": False, "error": str(e), "logs": logs + [f"[ERROR] {str(e)}"]}),
            status_code=500,
            headers=CORS_HEADERS,
            mimetype="application/json"
        )

@bp.route(route="operations/trigger-cloud-scan", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def trigger_cloud_scan(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=CORS_HEADERS)

    try:
        data = req.get_json() if req.get_body() else {}
        target_date = data.get("date")
        
        service = CloudWatcherService()
        results = service.scan_and_route(target_date=target_date)
        return func.HttpResponse(
            json.dumps({
                "success": results.get("success", False),
                "processed": results.get("processed", 0),
                "matched": results.get("matched", 0),
                "logs": results.get("logs", [])
            }),
            status_code=200,
            headers=CORS_HEADERS,
            mimetype="application/json"
        )
    except Exception as e:
        logging.error(f"Trigger Cloud Scan Error: {e}")
        return func.HttpResponse(
            json.dumps({"success": False, "error": str(e)}),
            status_code=500,
            headers=CORS_HEADERS,
            mimetype="application/json"
        )

@bp.route(route="operations/upload-screenshot", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def upload_screenshot(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=CORS_HEADERS)
    
    try:
        file = req.files.get("file")
        if not file:
            return func.HttpResponse(json.dumps({"success": False, "error": "No file provided"}), status_code=400, headers=CORS_HEADERS, mimetype="application/json")
        
        filename = file.filename
        image_bytes = file.read()
        
        from services.uber_matcher import UberMatcherService
        matcher = UberMatcherService()
        result = matcher.process_image_bytes(image_bytes, filename)
        
        return func.HttpResponse(
            json.dumps({"success": result.get("status") == "MATCHED", "result": result}),
            status_code=200,
            headers=CORS_HEADERS,
            mimetype="application/json"
        )
    except Exception as e:
        logging.error(f"Upload Screenshot Error: {e}")
        return func.HttpResponse(
            json.dumps({"success": False, "error": str(e)}),
            status_code=500,
            headers=CORS_HEADERS,
            mimetype="application/json"
        )

@bp.route(route="daily-sync", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def daily_sync(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=CORS_HEADERS)
        
    logging.info("Cloud Daily Sync Triggered")
    logs = []
    
    try:
        data = req.get_json() if req.get_body() else {}
        target_date_str = data.get("date") or data.get("processDate")
        
        if target_date_str:
            now = datetime.strptime(target_date_str, "%Y-%m-%d")
            logs.append(f"[INFO] Targeted Daily Sync for {target_date_str}")
        else:
            now = datetime.now()
            logs.append(f"[INFO] Standard Daily Sync for {now.strftime('%Y-%m-%d')}")
        year = now.strftime("%Y")
        month = now.strftime("%B")
        day = now.strftime("%d")
        
        # Week calculation: (Day-1)//7 + 1
        week_num = (now.day - 1) // 7 + 1
        week_folder = f"Week {week_num}"
        
        # 1. Ensure OneDrive Folders Exist
        try:
            graph = GraphClient()
            full_path = f"Uber Driver/{year}/{month}/{week_folder}/{day}"
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
        # Bank auto-sync distorts daily numbers; expenses are captured via receipt screenshots.
        logs.append(f"[SKIP] Banking Auto-Sync disabled — use manual expense entry on dashboard.")

        # 4. Integrated Cloud Scan - DISABLED (User now uploads directly via UI)
        logs.append(f"[SKIP] Autonomous OneDrive Scan disabled — using direct UI upload.")
        
        return func.HttpResponse(
            json.dumps({
                "success": True,
                "message": "Daily Sync completed in the Cloud",
                "logs": logs
            }),
            status_code=200,
            headers=CORS_HEADERS,
            mimetype="application/json"
        )

    except Exception as e:
        logging.error(f"Daily Sync Root Error: {e}")
        return func.HttpResponse(
            json.dumps({
                "success": False,
                "error": str(e),
                "logs": logs + [f"[CRITICAL] {str(e)}"]
            }),
            status_code=500,
            headers=CORS_HEADERS,
            mimetype="application/json"
        )
