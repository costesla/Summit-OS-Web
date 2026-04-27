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

@bp.route(route="process-blob", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def process_blob_http(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Modernized SummitOS Pipeline Triggered")
    pipeline = SummitPipeline()
    try:
        req_body = req.get_json()
        blob_url = req_body.get('blob_url')
        if not blob_url:
            return func.HttpResponse("Missing blob_url", status_code=400)

        # --- Phase 1: SIMULATE ---
        success, actions, error = pipeline.simulate(blob_url)
        if not success:
            return func.HttpResponse(json.dumps({"error": f"SIMULATE Phase Failed: {error}"}), status_code=500)

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
             }), status_code=202) # 202 Accepted for background processing but rejected from primary DB

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
