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

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (float, int)):
            return obj
        import decimal
        if isinstance(obj, decimal.Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

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
            }, cls=DecimalEncoder),
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

@bp.route(route="driver/sync", methods=["GET", "POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def driver_sync(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=CORS_HEADERS)

    db = DatabaseClient()

    if req.method == "GET":
        try:
            date_str = req.params.get("date")
            if not date_str:
                return func.HttpResponse(json.dumps({"error": "Missing date parameter"}), status_code=400, headers=CORS_HEADERS)
            
            trips = db.get_trips_by_date(date_str)
            expenses = db.get_expenses_by_date(date_str)
            
            return func.HttpResponse(
                json.dumps({
                    "success": True,
                    "date": date_str,
                    "trips": trips,
                    "expenses": expenses
                }, cls=DecimalEncoder),
                status_code=200,
                headers=CORS_HEADERS,
                mimetype="application/json"
            )
        except Exception as e:
            logging.error(f"Driver Data Fetch Error for date {date_str}: {e}")
            return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500, headers=CORS_HEADERS)

    try:
        data = req.get_json()
        trips = data.get("trips", [])
        expenses = data.get("expenses", {}) # { fastfood: [], charging: [] }
        
        from services.semantic_ingestion import SemanticIngestionService
        semantic = SemanticIngestionService()
        
        results = {
            "trips_saved": 0,
            "expenses_saved": 0,
            "vectors_created": 0
        }

        logging.info(f"Driver Sync POST: Received {len(trips)} trips and {len(expenses.get('fastfood', [])) + len(expenses.get('charging', []))} expenses.")

        # 1. Save Trips
        for trip in trips:
            # Handle both PascalCase (old/cached frontend) and lowercase (new frontend)
            fare = float(trip.get("fare") or trip.get("Fare") or 0)
            tip = float(trip.get("tip") or trip.get("Tip") or 0)
            fees = float(trip.get("fees") or trip.get("Fees") or 0)
            insurance = float(trip.get("insurance") or trip.get("Insurance") or 0)
            otherFees = float(trip.get("otherFees") or trip.get("OtherFees") or 0)
            
            # Distance and ID handling
            ride_id = str(trip.get("id") or trip.get("RideID"))
            ts = trip.get("timestamp") or trip.get("Timestamp_Start")
            dist = float(trip.get("distance_miles") or trip.get("Distance_mi") or 0)
            tdid = trip.get("tessie_drive_id") or trip.get("Tessie_DriveID")

            trip_payload = {
                "RideID": ride_id,
                "TripType": trip.get("type") or trip.get("TripType"),
                "Timestamp_Start": ts,
                "fare": fare,
                "tip": tip,
                "driver_total": fare + tip,
                "uber_cut": fees + insurance + otherFees,
                "distance_miles": dist,
                "tessie_drive_id": tdid,
                "Classification": "Manual_Entry"
            }
            db.save_trip(trip_payload)
            results["trips_saved"] += 1
            
            # Vectorize for Copilot
            try:
                semantic.ingest_tessie_drive(trip_payload, telemetry_summary="Manually logged trip from Driver Dashboard.")
                results["vectors_created"] += 1
            except:
                pass

        # 2. Save Fast Food Expenses
        for exp in expenses.get("fastfood", []):
            db.save_manual_expense({
                "id": str(exp.get("id") or exp.get("ExpenseID")),
                "category": "FastFood",
                "amount": float(exp.get("amount") or exp.get("Amount") or 0),
                "note": exp.get("note") or exp.get("Note"),
                "timestamp": exp.get("timestamp") or exp.get("Timestamp")
            })
            results["expenses_saved"] += 1

        # 3. Save Charging Expenses
        for charge in expenses.get("charging", []):
            db.save_charge({
                "session_id": str(charge.get("id") or charge.get("SessionID")),
                "start_time": charge.get("timestamp") or charge.get("Timestamp") or charge.get("Start_Time"),
                "end_time": charge.get("timestamp") or charge.get("Timestamp") or charge.get("End_Time"),
                "location": charge.get("note") or charge.get("Note") or "Manual Entry",
                "energy_added": 0, 
                "cost": float(charge.get("amount") or charge.get("Amount") or 0)
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
# Triggering fresh build after setting fix
