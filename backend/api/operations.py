import logging
import azure.functions as func
import json
import os
from datetime import datetime
from services.graph import GraphClient
from services.tessie_sync import TessieSyncService
from services.banking_sync import BankingSyncService

bp = func.Blueprint()

@bp.route(route="daily-sync", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def daily_sync(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Cloud Daily Sync Triggered")
    logs = []
    
    try:
        now = datetime.now()
        year = now.strftime("%Y")
        month = now.strftime("%B")
        day = now.strftime("%d")
        
        # 1. Ensure OneDrive Folders Exist
        try:
            graph = GraphClient()
            # Path: Uber Driver / 2026 / April / 25
            full_path = f"Uber Driver/{year}/{month}/{day}"
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
            b_result = b_sync.sync_recent(count=50, since_date=target_date)
            logs.append(f"[SUCCESS] Banking Sync: {b_result.get('transactions_vectorized', 0)} transactions vectorized.")
        except Exception as be:
            logging.error(f"Banking Sync Error: {be}")
            logs.append(f"[ERROR] Banking Sync Error: {str(be)}")

        return func.HttpResponse(
            json.dumps({
                "success": True,
                "message": "Daily Sync completed in the Cloud",
                "logs": logs
            }),
            status_code=200,
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
            mimetype="application/json"
        )
