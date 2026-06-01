import logging
import azure.functions as func
import json
import time
import os
import traceback
from services.ocr import OCRClient
from services.tessie import TessieClient
from services.database import DatabaseClient
from services.vector_store import VectorStore

bp = func.Blueprint()

from services.pipeline import SummitPipeline

bp = func.Blueprint()
# pipeline = SummitPipeline() # Moved inside function to avoid startup deadlocks

def _get_onedrive_download_info(file_id: str) -> tuple[str, str]:
    """
    Fetches the temporary anonymous download URL and actual file name from MS Graph for the given file_id.
    """
    import asyncio
    from api.pre_shift_check import _get_graph_token, _get_sharepoint_drive_id
    import requests as _req

    async def _resolve():
        token = await _get_graph_token()
        if not token:
            raise ValueError("MS Graph credentials not configured")
        
        site_id, drive_id, source, res_ms = await _get_sharepoint_drive_id(token)
        if not drive_id:
            raise ValueError("Failed to resolve SharePoint/OneDrive Drive ID")
            
        return token, drive_id

    # Run in event loop
    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        token, drive_id = loop.run_until_complete(_resolve())
    except Exception as e:
        raise ValueError(f"SharePoint/OneDrive authentication or resolution failed: {e}")

    url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{file_id}"
    headers = {"Authorization": f"Bearer {token}"}
    
    resp = _req.get(url, headers=headers, timeout=10)
    if resp.status_code == 429:
        import time
        retry_after = int(resp.headers.get("Retry-After", "2"))
        time.sleep(min(retry_after, 3))
        resp = _req.get(url, headers=headers, timeout=10)
        
    resp.raise_for_status()
    data = resp.json()
    
    download_url = data.get("@microsoft.graph.downloadUrl")
    file_name = data.get("name")
    
    if not download_url:
        raise ValueError(f"No @microsoft.graph.downloadUrl returned for file_id: {file_id}")
        
    return download_url, file_name


@bp.route(route="process-blob", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def process_blob_http(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Modernized SummitOS Pipeline Triggered")
    pipeline = SummitPipeline()
    try:
        req_body = req.get_json()
        blob_url = req_body.get('blob_url')
        file_id = req_body.get('file_id')
        source = req_body.get('source')
        file_name = req_body.get('file_name')

        custom_artifact_id = None
        custom_filename = None

        if not blob_url and not file_id:
            return func.HttpResponse(
                json.dumps({"error": "Missing blob_url or file_id parameter"}), 
                status_code=400,
                mimetype="application/json"
            )

        if file_id:
            # OneDrive Trigger flow: dynamic resolution of direct download URL and stable custom_artifact_id
            logging.info(f"Resolving OneDrive direct download URL for file_id: {file_id}")
            blob_url, actual_name = _get_onedrive_download_info(file_id)
            custom_artifact_id = f"onedrive-{file_id}"
            custom_filename = file_name or actual_name
            logging.info(f"Successfully resolved OneDrive download URL. Custom ID: {custom_artifact_id}, Custom Name: {custom_filename}")

        # --- Phase 1: SIMULATE ---
        success, actions, error = pipeline.simulate(blob_url, custom_artifact_id, custom_filename)
        if not success:
            return func.HttpResponse(json.dumps({"error": f"SIMULATE Phase Failed: {error}"}), status_code=500, mimetype="application/json")

        # --- Phase 2: EXECUTE ---
        # In a real system, we might ask for approval here if status == "Proposed"
        # For this automation, we auto-promote to EXECUTE if simulation is success.
        success, record, error = pipeline.execute(actions)
        if not success:
             # This includes Quarantine scenarios
             return func.HttpResponse(json.dumps({
                 "status": "QUARANTINED",
                 "reason": error,
                 "artifact_id": actions.get('artifact_id')
             }), status_code=202, mimetype="application/json") # 202 Accepted for background processing but rejected from primary DB

        # --- Phase 3: INTELLIGENCE ---
        pipeline.intelligence(record)
        
        return func.HttpResponse(
            json.dumps({
                "status": "success", 
                "classification": actions['classification'],
                "artifact_id": record['artifact_id']
            }),
            status_code=200,
            mimetype="application/json"
        )
    except Exception as e:
        logging.error(f"Pipeline Error: {traceback.format_exc()}")
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500, mimetype="application/json")
