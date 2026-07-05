import logging
import json
import os
import datetime
import azure.functions as func
from services.database import DatabaseClient
from services.semantic_ingestion import SemanticIngestionService
from services.datetime_utils import get_operational_window, get_timezone, utc_to_local
from services.customer_pricing import JackieBillingEngine

bp = func.Blueprint()

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, PATCH, OPTIONS",
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
            private_payments = db.get_private_payments(date_str, date_str)

            headers = CORS_HEADERS.copy()
            headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            headers["Pragma"] = "no-cache"
            headers["Expires"] = "0"

            return func.HttpResponse(
                json.dumps({
                    "success": True,
                    "date": date_str,
                    "trips": trips,
                    "expenses": expenses,
                    "private_payments": private_payments
                }, cls=DecimalEncoder),
                status_code=200,
                headers=headers,
                mimetype="application/json"
            )
        except Exception as e:
            logging.error(f"Driver Data Fetch Error for date {date_str}: {e}")
            return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500, headers=CORS_HEADERS)

    try:
        data = req.get_json()
        trips = data.get("trips", [])
        expenses = data.get("expenses", {}) # { fastfood: [], charging: [], capital_maintenance: [] }
        
        from services.semantic_ingestion import SemanticIngestionService
        from services.artifact_registry import ArtifactRegistry
        semantic = SemanticIngestionService()
        registry = ArtifactRegistry()
        
        results = {
            "trips_saved": 0,
            "expenses_saved": 0,
            "vectors_created": 0
        }

        logging.info(f"Driver Sync POST: Received {len(trips)} trips and {len(expenses.get('fastfood', [])) + len(expenses.get('charging', [])) + len(expenses.get('capital_maintenance', []))} expenses.")

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
                "driver_total": fare + tip - (fees + insurance + otherFees),
                "uber_cut": fees + insurance + otherFees,
                "distance_miles": dist,
                "tessie_drive_id": tdid,
                "Classification": trip.get("classification") or trip.get("Classification") or "Manual_Entry",
                "payment_status": trip.get("payment_status") or trip.get("PaymentStatus")
            }
            # Register artifact first so source_pointer is a stable GUID URI
            try:
                trip_payload['source_path'] = 'manual://dashboard'
                registry.register(
                    artifact_type='Trip',
                    entity_id=str(ride_id),
                    entity_table='Rides.Rides',
                    source_path='manual://dashboard',
                    ingestion_path='Manual',
                )
            except Exception:
                pass
            db.save_trip(trip_payload)
            results["trips_saved"] += 1

            # Vectorize for Copilot
            try:
                semantic.ingest_tessie_drive(trip_payload, telemetry_summary="Manually logged trip from Driver Dashboard.")
                results["vectors_created"] += 1
            except Exception:
                pass

        # 2. Save Fast Food Expenses
        for exp in expenses.get("fastfood", []):
            cat = exp.get("category") or "FastFood"
            payload = {
                "id": str(exp.get("id") or exp.get("ExpenseID")),
                "category": cat,
                "amount": float(exp.get("amount") or exp.get("Amount") or 0),
                "note": exp.get("note") or exp.get("Note"),
                "timestamp": exp.get("timestamp") or exp.get("Timestamp"),
                "included_in_kpi": 1,
                "expense_type": exp.get("expense_type") or "OpEx"
            }
            db.save_manual_expense(payload)
            results["expenses_saved"] += 1
            try:
                semantic.ingest_manual_expense(payload, cat)
                results["vectors_created"] += 1
            except Exception:
                pass

        # 3. Save Charging Expenses
        for charge in expenses.get("charging", []):
            payload = {
                "id": str(charge.get("id") or charge.get("SessionID")),
                "amount": float(charge.get("amount") or charge.get("Amount") or 0),
                "note": charge.get("note") or charge.get("Note") or "Manual Entry",
                "timestamp": charge.get("timestamp") or charge.get("Timestamp") or charge.get("Start_Time"),
            }
            db.save_charge({
                "session_id": payload["id"],
                "start_time": payload["timestamp"],
                "end_time":   payload["timestamp"],
                "location":   payload["note"],
                "energy_added": 0,
                "cost": payload["amount"]
            })
            results["expenses_saved"] += 1
            try:
                semantic.ingest_manual_expense(payload, "Charging")
                results["vectors_created"] += 1
            except Exception:
                pass

        # 4. Save Capital & Maintenance Expenses
        for exp in expenses.get("capital_maintenance", []):
            cat = exp.get("category") or "Maintenance"
            payload = {
                "id": str(exp.get("id") or exp.get("ExpenseID")),
                "category": cat,
                "amount": float(exp.get("amount") or exp.get("Amount") or 0),
                "note": exp.get("note") or exp.get("Note"),
                "timestamp": exp.get("timestamp") or exp.get("Timestamp"),
                "included_in_kpi": 0 if cat in ["Maintenance", "General_Expense"] else 1,
                "expense_type": exp.get("expense_type") or "CapEx"
            }
            db.save_manual_expense(payload)
            results["expenses_saved"] += 1
            try:
                semantic.ingest_manual_expense(payload, cat)
                results["vectors_created"] += 1
            except Exception:
                pass

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

@bp.route(route="jackie/deferred", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def jackie_deferred(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=CORS_HEADERS)

    db = DatabaseClient()
    try:
        # Fetch all Jackie rides (unpaid/deferred + credits for cap context)
        query = """
            SELECT RideID, Timestamp_Start, Fare, PaymentStatus, Tessie_Label, Classification, Pickup_Location, Dropoff_Location, Sidecar_Artifact_JSON
            FROM Rides.Rides
            WHERE RideID LIKE 'INV-JACKIE-%'
              AND PaymentStatus IN ('Deferred', 'Credit')
              AND DeletedAt IS NULL
              AND (IsTest IS NULL OR IsTest = 0)
            ORDER BY Timestamp_Start ASC
        """
        results = db.execute_query_with_results(query)

        # Helper: scrub house number from address for visual privacy
        def scrub_address(addr: str | None) -> str | None:
            if not addr:
                return None
            import re
            return re.sub(r'^\d+\s+', '', addr.strip())

        # Group rides by operational day
        grouped_by_day = {}
        for r in results:
            ts = r["Timestamp_Start"]
            # Attributes the ride to the operational day
            if ts.hour < 4:
                op_date = (ts - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
            else:
                op_date = ts.strftime("%Y-%m-%d")
            
            if op_date not in grouped_by_day:
                grouped_by_day[op_date] = []
            grouped_by_day[op_date].append(r)

        # Calculate current local date to compute aging
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        now_local = utc_to_local(now_utc)
        current_local_date = now_local.date()

        days_list = []
        for op_date, day_rides in grouped_by_day.items():
            # Filter out AA trips (they never appear in Panel 1 deferred tracker)
            non_aa_rides = []
            for r in day_rides:
                tessie_label = r.get("Tessie_Label") or ""
                classification = r.get("Classification") or ""
                if not JackieBillingEngine.is_aa_trip(tessie_label, classification):
                    non_aa_rides.append(r)

            if not non_aa_rides:
                continue

            # Determine legs counts
            legs = len(non_aa_rides)
            deferred_rides = [r for r in non_aa_rides if r["PaymentStatus"] == "Deferred"]
            credit_rides = [r for r in non_aa_rides if r["PaymentStatus"] == "Credit"]
            
            # If there are no outstanding deferred invoices on this day, it is not outstanding
            if not deferred_rides:
                continue

            deferred_count = len(deferred_rides)
            credit_count = len(credit_rides)
            billed_amount = float(sum(r["Fare"] for r in deferred_rides))
            invoice_ids = [r["RideID"] for r in deferred_rides]

            # Parse operational date for age calculation
            op_dt = datetime.datetime.strptime(op_date, "%Y-%m-%d").date()
            age_days = (current_local_date - op_dt).days

            # Generate notes
            notes = []
            for r in deferred_rides:
                pickup = scrub_address(r.get("Pickup_Location")) or "Unknown"
                dropoff = scrub_address(r.get("Dropoff_Location")) or "Unknown"
                notes.append(f"{pickup} to {dropoff}")
            note_str = " · ".join(notes)

            days_list.append({
                "date": op_date,
                "legs": legs,
                "billed_legs": deferred_count,
                "credited_legs": credit_count,
                "billed_amount": billed_amount,
                "invoice_ids": invoice_ids,
                "age_days": age_days,
                "note": note_str
            })

        # Sort: oldest operational day first
        days_list.sort(key=lambda d: d["date"])

        return func.HttpResponse(
            json.dumps({"success": True, "days": days_list}, cls=DecimalEncoder),
            status_code=200,
            headers=CORS_HEADERS,
            mimetype="application/json"
        )
    except Exception as e:
        logging.error(f"Jackie Deferred API Error: {e}")
        return func.HttpResponse(
            json.dumps({"success": False, "error": str(e)}),
            status_code=500,
            headers=CORS_HEADERS,
            mimetype="application/json"
        )

@bp.route(route="invoices/bulk-collect", methods=["PATCH", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def bulk_collect(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=CORS_HEADERS)

    db = DatabaseClient()
    try:
        req_body = req.get_json()
        invoice_ids = req_body.get("invoice_ids", [])
        if not invoice_ids:
            return func.HttpResponse(
                json.dumps({"success": False, "error": "No invoice IDs provided"}),
                status_code=400,
                headers=CORS_HEADERS,
                mimetype="application/json"
            )

        success = db.bulk_collect_invoices(invoice_ids)
        return func.HttpResponse(
            json.dumps({"success": success, "collected": len(invoice_ids)}),
            status_code=200,
            headers=CORS_HEADERS,
            mimetype="application/json"
        )
    except Exception as e:
        logging.error(f"Bulk Collect API Error: {e}")
        return func.HttpResponse(
            json.dumps({"success": False, "error": str(e)}),
            status_code=500,
            headers=CORS_HEADERS,
            mimetype="application/json"
        )

@bp.route(route="financials/summary", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def financials_summary(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=CORS_HEADERS)

    db = DatabaseClient()
    try:
        date_param = req.params.get("date", "").strip()
        if date_param:
            try:
                datetime.datetime.strptime(date_param, "%Y-%m-%d")
                date_str = date_param
            except ValueError:
                return func.HttpResponse(
                    json.dumps({"error": "Invalid date format. Use YYYY-MM-DD."}),
                    status_code=400, mimetype="application/json", headers=CORS_HEADERS
                )
        else:
            # Default: current local date
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            now_local = utc_to_local(now_utc)
            date_str = now_local.strftime("%Y-%m-%d")

        selected_dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        
        # Calculate Week Start (Monday) of the week containing selected_dt
        week_start = selected_dt - datetime.timedelta(days=selected_dt.weekday())
        week_start_str = week_start.strftime("%Y-%m-%d")

        # Calculate Month Start (1st) of the month containing selected_dt
        month_start_str = selected_dt.strftime("%Y-%m-01")

        # Fetch range stats
        today_stats = db.get_summary_metrics_for_range(date_str, date_str)
        week_stats = db.get_summary_metrics_for_range(week_start_str, date_str)
        month_stats = db.get_summary_metrics_for_range(month_start_str, date_str)

        # Global outstanding deferred balance
        deferred_total = db.get_global_deferred_total()

        # Targets derived from REVENUE_TARGET_MONTHLY environment variable
        target_monthly = float(os.environ.get("REVENUE_TARGET_MONTHLY", 6500.0))
        target_weekly = round(target_monthly / 4.0)
        target_daily = round(target_weekly / 7.0)

        payload = {
            "success": True,
            "date": date_str,
            "gross_earnings": today_stats["gross_earnings"],
            "uber_earnings": today_stats["uber_earnings"],
            "uber_tips": today_stats.get("uber_tips", 0.0),
            "private_income": today_stats["private_income"],
            "opex_expenses": today_stats.get("opex_expenses", 0.0),
            "capex_expenses": today_stats.get("capex_expenses", 0.0),
            "expenses": today_stats["expenses"],
            "net_profit": today_stats["net_profit"],
            "deferred_total": deferred_total,
            "targets": {
                "daily": target_daily,
                "weekly": target_weekly,
                "monthly": target_monthly
            },
            "progress": {
                "today": { "actual": today_stats["gross_earnings"], "target": target_daily },
                "week": { "actual": week_stats["gross_earnings"], "target": target_weekly },
                "month": { "actual": month_stats["gross_earnings"], "target": target_monthly }
            }
        }

        return func.HttpResponse(
            json.dumps(payload, cls=DecimalEncoder),
            status_code=200,
            headers=CORS_HEADERS,
            mimetype="application/json"
        )
    except Exception as e:
        logging.error(f"Financials Summary API Error: {e}")
        return func.HttpResponse(
            json.dumps({"success": False, "error": str(e)}),
            status_code=500,
            headers=CORS_HEADERS,
            mimetype="application/json"
        )

@bp.route(route="tools/rebuild-day", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def tools_rebuild_day(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=CORS_HEADERS)

    try:
        from api.operations import _execute_daily_sync, run_async_job
        data = req.get_json() if req.get_body() else {}
        target_date_str = data.get("date") or data.get("processDate")
        result = run_async_job("Daily Ingestion Sync", _execute_daily_sync, target_date_str=target_date_str)
        return func.HttpResponse(json.dumps(result), status_code=202, headers=CORS_HEADERS, mimetype="application/json")
    except Exception as e:
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500, headers=CORS_HEADERS, mimetype="application/json")

@bp.route(route="tools/scrub-day", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def tools_scrub_day(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=CORS_HEADERS)

    try:
        data = req.get_json() if req.get_body() else {}
        date_str = data.get("date") or data.get("processDate")
        if not date_str:
            return func.HttpResponse(json.dumps({"success": False, "error": "date is required"}), status_code=400, headers=CORS_HEADERS, mimetype="application/json")
        
        result = _execute_scrub_day(date_str)
        status_code = 200 if result.get("success") else 500
        return func.HttpResponse(json.dumps(result), status_code=status_code, headers=CORS_HEADERS, mimetype="application/json")
    except Exception as e:
        return func.HttpResponse(json.dumps({"success": False, "error": str(e)}), status_code=500, headers=CORS_HEADERS, mimetype="application/json")

def _execute_scrub_day(date_str: str) -> dict:
    from services.database import DatabaseClient
    db = DatabaseClient()
    conn = db.get_connection()
    if not conn:
        return {"success": False, "error": "No database connection"}
    conn.autocommit = False
    cursor = conn.cursor()
    
    logs = []
    try:
        date_compact = date_str.replace("-", "")
        dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        date_only = dt.date()

        # 1. Delete TRIP- records
        cursor.execute("DELETE FROM Rides.Rides WHERE RideID LIKE ?", (f"TRIP-{date_compact}-%",))
        deleted = cursor.rowcount
        logs.append(f"SCRUB: Deleted {deleted} TRIP-{date_compact}-* records")

        # 2. Revert Tessie drives
        cursor.execute("""
            SELECT RideID, Classification, TripType, Sidecar_Artifact_JSON
            FROM Rides.Rides
            WHERE RideID LIKE 'TESSIE-%'
              AND CAST(Timestamp_Start AS DATE) = ?
        """, (date_only,))
        tessie_drives = cursor.fetchall()
        for td in tessie_drives:
            td_id, cur_class, cur_type, sc_str = td
            orig_class = 'Untagged'
            orig_type = None
            if sc_str:
                try:
                    sc = json.loads(sc_str)
                    if "Classification" in sc:
                        orig_class = sc.get("Classification", "Untagged")
                        orig_type = sc.get("TripType")
                    else:
                        nested = sc.get("Sidecar_Artifact_JSON")
                        if isinstance(nested, str): nested = json.loads(nested)
                        if nested and "tag" in nested:
                            tag = nested.get("tag")
                            if tag is not None:
                                from services.tessie_sync import TessieSyncService
                                orig_class = TessieSyncService()._classify_drive(tag)
                                orig_type = 'Uber' if orig_class == 'Uber_Dropoff' else 'Private'
                except:
                    pass
            cursor.execute("""
                UPDATE Rides.Rides
                SET Classification = ?, TripType = ?, LastUpdated = GETUTCDATE()
                WHERE RideID = ?
            """, (orig_class, orig_type, td_id))
        logs.append(f"SCRUB: Reverted {len(tessie_drives)} Tessie drive(s) to original tags.")

        # 3. Clear telemetry on bookings
        cursor.execute("""
            SELECT RideID, Tessie_DriveID, ValidationStatus
            FROM Rides.Rides
            WHERE (RideID LIKE 'INV-%' OR (RideID LIKE 'TRIP-%' AND TripType = 'Private'))
              AND CAST(Timestamp_Start AS DATE) = ?
              AND DeletedAt IS NULL
        """, (date_only,))
        bookings = cursor.fetchall()
        for b in bookings:
            b_id, t_id, b_status = b
            can_rematch = False
            if t_id:
                cursor.execute("SELECT COUNT(*) FROM Rides.Rides WHERE RideID = ?", (t_id,))
                can_rematch = cursor.fetchone()[0] > 0
            
            if can_rematch:
                cursor.execute("""
                    UPDATE Rides.Rides
                    SET Tessie_DriveID = NULL, Distance_mi = NULL, Duration_min = NULL,
                        Start_SOC = NULL, End_SOC = NULL, Energy_Used_kWh = NULL, Efficiency_Wh_mi = NULL,
                        ValidationStatus = NULL, LastUpdated = GETUTCDATE()
                    WHERE RideID = ?
                """, (b_id,))
            else:
                new_status = 'OrphanTelemetry' if t_id else b_status
                cursor.execute("""
                    UPDATE Rides.Rides
                    SET ValidationStatus = ?, LastUpdated = GETUTCDATE()
                    WHERE RideID = ?
                """, (new_status, b_id))
        logs.append(f"SCRUB: Unlinked/flagged {len(bookings)} bookings on {date_str}.")

        conn.commit()
        return {"success": True, "logs": logs}
    except Exception as e:
        conn.rollback()
        return {"success": False, "error": str(e), "logs": logs}
    finally:
        conn.close()

@bp.route(route="tools/create-folders", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def tools_create_folders(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=CORS_HEADERS)

    try:
        from api.operations import _execute_sync_folders, run_async_job
        data = req.get_json() if req.get_body() else {}
        process_date_str = data.get("date") or data.get("processDate")
        result = run_async_job("OneDrive Folder Sync", _execute_sync_folders, process_date_str=process_date_str, dry_run=False)
        return func.HttpResponse(json.dumps(result), status_code=202, headers=CORS_HEADERS, mimetype="application/json")
    except Exception as e:
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500, headers=CORS_HEADERS, mimetype="application/json")

@bp.route(route="tools/save-day", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def tools_save_day(req: func.HttpRequest) -> func.HttpResponse:
    # Thin wrapper of driver_sync POST logic
    return driver_sync(req)


# Triggering fresh build after setting fix
