import logging
import json
import azure.functions as func
from services.database import DatabaseClient
from services.semantic_ingestion import SemanticIngestionService

bp = func.Blueprint()

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type"
}

@bp.route(route="stripe/balance", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def stripe_balance(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=CORS_HEADERS)

    try:
        import stripe
        import os
        stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
        if not stripe.api_key:
            return func.HttpResponse(json.dumps({"error": "Stripe key not found"}), status_code=500, headers=CORS_HEADERS)

        balance = stripe.Balance.retrieve()
        
        # Stripe balance is in cents, convert to dollars
        available = sum(b.amount for b in balance.available if b.currency == 'usd') / 100.0
        pending = sum(b.amount for b in balance.pending if b.currency == 'usd') / 100.0

        return func.HttpResponse(
            json.dumps({
                "success": True, 
                "available": available,
                "pending": pending,
                "currency": "usd"
            }),
            status_code=200,
            headers=CORS_HEADERS,
            mimetype="application/json"
        )
    except Exception as e:
        logging.error(f"Stripe Balance API Error: {e}")
        return func.HttpResponse(
            json.dumps({"success": False, "error": str(e)}),
            status_code=500,
            headers=CORS_HEADERS,
            mimetype="application/json"
        )

@bp.route(route="driver/sync", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def driver_sync(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=CORS_HEADERS)

    try:
        data = req.get_json()
        trips = data.get("trips", [])
        expenses = data.get("expenses", {}) # { fastfood: [], charging: [] }
        
        db = DatabaseClient()
        semantic = SemanticIngestionService()
        
        results = {
            "trips_saved": 0,
            "expenses_saved": 0,
            "vectors_created": 0
        }

        # 1. Save Trips
        for trip in trips:
            # Normalize for save_trip
            trip_payload = {
                "RideID": trip.get("id"),
                "TripType": trip.get("type"),
                "Timestamp_Start": trip.get("timestamp"),
                "Fare": trip.get("fare"),
                "Tip": trip.get("tip"),
                "Driver_Earnings": trip.get("fare") + trip.get("tip"),
                "Platform_Cut": trip.get("fees") + trip.get("insurance") + trip.get("otherFees"),
                "Classification": "Manual_Entry"
            }
            db.save_trip(trip_payload)
            results["trips_saved"] += 1
            
            # Vectorize for Copilot
            semantic.ingest_tessie_drive(trip_payload, telemetry_summary="Manually logged trip from Driver Dashboard.")
            results["vectors_created"] += 1

        # 2. Save Fast Food Expenses
        for exp in expenses.get("fastfood", []):
            db.save_manual_expense({
                "id": exp.get("id"),
                "category": "FastFood",
                "amount": exp.get("amount"),
                "note": exp.get("note"),
                "timestamp": exp.get("timestamp")
            })
            results["expenses_saved"] += 1

        # 3. Save Charging Expenses
        for charge in expenses.get("charging", []):
            db.save_charge({
                "session_id": charge.get("id"),
                "start_time": charge.get("timestamp"),
                "end_time": charge.get("timestamp"),
                "location": "Manual Entry",
                "energy_added": 0, # Could be improved if we add fields
                "cost": charge.get("amount")
            })
            results["expenses_saved"] += 1

        return func.HttpResponse(
            json.dumps({"success": True, "results": results}),
            status_code=200,
            headers=CORS_HEADERS,
            mimetype="application/json"
        )

    except Exception as e:
        logging.error(f"Driver Sync API Error: {e}")
        return func.HttpResponse(
            json.dumps({"success": False, "error": str(e)}),
            status_code=500,
            headers=CORS_HEADERS,
            mimetype="application/json"
        )
