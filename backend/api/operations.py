import logging
import azure.functions as func
import json
import os
from datetime import datetime
from services.graph import GraphClient
from services.tessie_sync import TessieSyncService
from services.banking_sync import BankingSyncService
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

        # 3. Sync Banking Data
        try:
            logs.append(f"[INFO] Syncing Banking transactions...")
            b_sync = BankingSyncService()
            b_result = b_sync.sync_recent(count=15, since_date=target_date)
            logs.append(f"[SUCCESS] Banking Sync: {b_result.get('expenses_synced', 0)} expenses synced, {b_result.get('income_skipped', 0)} income skipped.")
        except Exception as be:
            logging.error(f"Banking Sync Error: {be}")
            logs.append(f"[ERROR] Banking Sync Error: {str(be)}")

        # 4. Integrated Cloud Scan
        try:
            logs.append(f"[INFO] Triggering Autonomous Cloud Scan...")
            c_watcher = CloudWatcherService()
            c_result = c_watcher.scan_and_route(target_date=target_date)
            logs.append(f"[SUCCESS] Cloud Scan: {c_result.get('processed', 0)} files analyzed, {c_result.get('matched', 0)} Uber trips routed.")
            # Append cloud scan logs to main logs for visibility
            for l in c_result.get("logs", []):
                logs.append(f"  > {l}")
        except Exception as ce:
            logging.error(f"Cloud Scan Error: {ce}")
            logs.append(f"[ERROR] Cloud Scan Error: {str(ce)}")

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
