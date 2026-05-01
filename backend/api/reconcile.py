import logging
import json
import base64
import azure.functions as func
from services.reconciliation import ReconciliationService
from services.banking_sync import BankingSyncService
from services.ocr import OCRClient

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


@bp.route(
    route="reconcile/pending-expenses",
    methods=["GET", "OPTIONS"],
    auth_level=func.AuthLevel.ANONYMOUS
)
def get_pending_expenses(req: func.HttpRequest) -> func.HttpResponse:
    """
    Returns today's PENDING debit transactions from Chase/Teller.
    Use this to preview what can be matched against receipt screenshots.

    GET params:
        date  - YYYY-MM-DD (defaults to today)
    """
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=CORS_HEADERS)

    try:
        date_str = req.params.get("date")
        service = BankingSyncService()
        pending = service.get_pending_expenses(date_str=date_str)

        return func.HttpResponse(
            json.dumps({
                "success": True,
                "date": date_str or "today",
                "count": len(pending),
                "pending_expenses": pending
            }),
            status_code=200,
            headers=CORS_HEADERS,
            mimetype="application/json"
        )
    except Exception as e:
        logging.error(f"Pending Expenses Error: {e}")
        return func.HttpResponse(
            json.dumps({"success": False, "error": str(e)}),
            status_code=500,
            headers=CORS_HEADERS,
            mimetype="application/json"
        )


@bp.route(
    route="reconcile/match-receipt",
    methods=["POST", "OPTIONS"],
    auth_level=func.AuthLevel.ANONYMOUS
)
def match_receipt_to_pending(req: func.HttpRequest) -> func.HttpResponse:
    """
    Screenshot → OCR → match against today's pending bank transactions.

    POST body (JSON):
    {
        "image_base64":    "base64-encoded image bytes",
        "source_filename": "Receipt_Starbucks_20260501.jpg",
        "date":            "2026-05-01",    // optional, defaults to today
        "vehicle_ref":     "Thor"           // optional
    }

    Flow:
    1. Decode base64 → run Azure OCR
    2. Extract merchant, total, date from OCR text
    3. Match against pending Teller debit transactions (±$0.50 window)
    4. Write full reconciliation record to Ledger + Vector DB
    5. Return spec-compliant JSON with match result
    """
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=CORS_HEADERS)

    try:
        body = req.get_json()
        image_b64 = body.get("image_base64", "")
        source_filename = body.get("source_filename", "receipt.jpg")
        date_str = body.get("date")
        vehicle_ref = body.get("vehicle_ref", "Thor")

        if not image_b64:
            return func.HttpResponse(
                json.dumps({"success": False, "error": "image_base64 is required"}),
                status_code=400,
                headers=CORS_HEADERS,
                mimetype="application/json"
            )

        # 1. OCR the image
        image_bytes = base64.b64decode(image_b64)
        ocr = OCRClient()
        ocr_text = ocr.analyze_image_bytes(image_bytes)

        if not ocr_text:
            return func.HttpResponse(
                json.dumps({"success": False, "error": "OCR returned no text"}),
                status_code=422,
                headers=CORS_HEADERS,
                mimetype="application/json"
            )

        # 2. Run full reconciliation (matches against bank feed automatically)
        recon = ReconciliationService()
        result = recon.reconcile_receipt(
            ocr_text=ocr_text,
            source_filename=source_filename,
            parsed_date=date_str,
            vehicle_ref=vehicle_ref
        )

        # 3. Also surface the pending bank item it matched (if any)
        chase_ref = result.get("sql_ledger", {}).get("data", {}).get("chase_reference_id")
        matched_tx = None
        if chase_ref:
            banking = BankingSyncService()
            pending = banking.get_pending_expenses(date_str=date_str)
            matched_tx = next((p for p in pending if p["id"] == chase_ref), None)

        result["matched_bank_transaction"] = matched_tx
        result["ocr_text_extracted"] = ocr_text[:500]  # Preview for UI

        return func.HttpResponse(
            json.dumps(result),
            status_code=200,
            headers=CORS_HEADERS,
            mimetype="application/json"
        )

    except Exception as e:
        logging.error(f"Match Receipt Error: {e}")
        return func.HttpResponse(
            json.dumps({"success": False, "error": str(e)}),
            status_code=500,
            headers=CORS_HEADERS,
            mimetype="application/json"
        )
