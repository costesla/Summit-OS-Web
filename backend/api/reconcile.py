import logging
import json
import azure.functions as func
from services.reconciliation import ReconciliationService

bp = func.Blueprint()

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type"
}


@bp.route(
    route="reconcile/receipt",
    methods=["POST", "OPTIONS"],
    auth_level=func.AuthLevel.ANONYMOUS
)
def reconcile_receipt(req: func.HttpRequest) -> func.HttpResponse:
    """
    Reconcile a single receipt.

    POST body (JSON):
    {
        "ocr_text":        "raw OCR string from Azure Vision / Document Intelligence",
        "source_filename": "Screenshot_20260429_143022.jpg",
        "parsed_amount":   null | 12.50,     // optional override
        "parsed_date":     null | "2026-04-29",
        "parsed_merchant": null | "Starbucks",
        "vehicle_ref":     "Thor"             // optional, default "Thor"
    }
    """
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=CORS_HEADERS)

    try:
        body = req.get_json()
        service = ReconciliationService()
        result = service.reconcile_receipt(
            ocr_text=body.get("ocr_text", ""),
            source_filename=body.get("source_filename", "unknown"),
            parsed_amount=body.get("parsed_amount"),
            parsed_date=body.get("parsed_date"),
            parsed_merchant=body.get("parsed_merchant"),
            vehicle_ref=body.get("vehicle_ref", "Thor")
        )
        return func.HttpResponse(
            json.dumps(result),
            status_code=200,
            headers=CORS_HEADERS,
            mimetype="application/json"
        )
    except Exception as e:
        logging.error(f"Reconcile Receipt Error: {e}")
        return func.HttpResponse(
            json.dumps({"success": False, "error": str(e)}),
            status_code=500,
            headers=CORS_HEADERS,
            mimetype="application/json"
        )


@bp.route(
    route="reconcile/batch",
    methods=["POST", "OPTIONS"],
    auth_level=func.AuthLevel.ANONYMOUS
)
def reconcile_batch(req: func.HttpRequest) -> func.HttpResponse:
    """
    Reconcile multiple receipts in one call.

    POST body (JSON):
    {
        "vehicle_ref": "Thor",
        "receipts": [
            { "ocr_text": "...", "source_filename": "...", "parsed_amount": 12.50, ... },
            ...
        ]
    }
    """
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=CORS_HEADERS)

    try:
        body = req.get_json()
        service = ReconciliationService()
        result = service.reconcile_batch(
            receipts=body.get("receipts", []),
            vehicle_ref=body.get("vehicle_ref", "Thor")
        )
        return func.HttpResponse(
            json.dumps(result),
            status_code=200,
            headers=CORS_HEADERS,
            mimetype="application/json"
        )
    except Exception as e:
        logging.error(f"Reconcile Batch Error: {e}")
        return func.HttpResponse(
            json.dumps({"success": False, "error": str(e)}),
            status_code=500,
            headers=CORS_HEADERS,
            mimetype="application/json"
        )


@bp.route(
    route="reconcile/ledger",
    methods=["GET", "OPTIONS"],
    auth_level=func.AuthLevel.ANONYMOUS
)
def get_ledger(req: func.HttpRequest) -> func.HttpResponse:
    """
    Query the Reconciliation_Ledger.

    GET params:
        date        - filter by TransactionDate (YYYY-MM-DD)
        unmatched   - if "true", return only requires_review=1 records
        limit       - max records (default 50)
    """
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=CORS_HEADERS)

    try:
        from services.database import DatabaseClient
        db = DatabaseClient()

        date_filter = req.params.get("date")
        unmatched = req.params.get("unmatched", "").lower() == "true"
        limit = int(req.params.get("limit", 50))

        query = f"""
            SELECT TOP {limit}
                RecordID, MerchantName, TransactionDate, TotalAmount, Currency,
                ChaseReferenceID, MatchConfidence, Category,
                Reconciled, RequiresReview, ReviewReason, SourceFile,
                FORMAT(CreatedAt, 'yyyy-MM-ddTHH:mm:ss') AS CreatedAt
            FROM Rides.Reconciliation_Ledger
            WHERE 1=1
        """
        params = []

        if date_filter:
            query += " AND TransactionDate = CAST(? AS DATE)"
            params.append(date_filter)

        if unmatched:
            query += " AND RequiresReview = 1"

        query += " ORDER BY CreatedAt DESC"

        records = db.execute_query_params(query, params) if params else \
                  db.execute_query_with_results(query)

        return func.HttpResponse(
            json.dumps({"success": True, "count": len(records), "records": records}),
            status_code=200,
            headers=CORS_HEADERS,
            mimetype="application/json"
        )
    except Exception as e:
        logging.error(f"Ledger Query Error: {e}")
        return func.HttpResponse(
            json.dumps({"success": False, "error": str(e)}),
            status_code=500,
            headers=CORS_HEADERS,
            mimetype="application/json"
        )
