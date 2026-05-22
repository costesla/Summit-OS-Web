import os
import sys
import json
import datetime
import logging
from typing import Dict, Any
from zoneinfo import ZoneInfo

# Ensure root backend dir is in PYTHONPATH
script_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(script_dir)
sys.path.insert(0, backend_dir)

# Load env vars from local.settings.json (local dev only)
settings_path = os.path.join(backend_dir, "local.settings.json")
if os.path.exists(settings_path):
    with open(settings_path, "r", encoding="utf-8") as f:
        settings = json.load(f)
        for k, v in (settings.get("Values", {}) or {}).items():
            os.environ[str(k)] = str(v)

from services.database import DatabaseClient
from services.agents.summit_intelligence import TripsAgent, ChargingAgent, ExpensesAgent, VehicleAgent

MT = ZoneInfo("America/Denver")


def iso_noon_local(date_str: str) -> str:
    """Create a stable, DST-correct ISO timestamp at 12:00 local time for date-only records."""
    d = datetime.date.fromisoformat(date_str)
    dt = datetime.datetime(d.year, d.month, d.day, 12, 0, 0, tzinfo=MT)
    return dt.isoformat()


def parse_iso_to_local_naive(ts: str) -> datetime.datetime | None:
    """
    Parse an ISO timestamp and convert to America/Denver, then drop tzinfo
    so it can be compared to DB naive datetimes safely.
    """
    if not ts:
        return None
    try:
        # Handle Zulu
        ts_norm = ts.replace("Z", "+00:00")
        dt = datetime.datetime.fromisoformat(ts_norm)
        if dt.tzinfo is None:
            # If telemetry timestamp comes in naive, assume it's UTC to avoid guessing local
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        local = dt.astimezone(MT)
        return local.replace(tzinfo=None)
    except Exception:
        return None


def run_deterministic_pipeline(date_str: str) -> Dict[str, Any]:
    logging.info(f"Starting deterministic data pipeline run for date: {date_str}")

    db = DatabaseClient()
    conn = db.get_connection()
    if not conn:
        raise ConnectionError("Database Connection failed. Verify settings.")
    conn.close()

    # 1) INGEST (isolated)
    trips_agent = TripsAgent(db)
    charging_agent = ChargingAgent(db)
    expenses_agent = ExpensesAgent(db)
    vehicle_agent = VehicleAgent(db)

    raw_trips = trips_agent.query(date_str=date_str)
    raw_charges = charging_agent.query(date_str=date_str)
    raw_expenses = expenses_agent.query(date_str=date_str)
    raw_telemetry = vehicle_agent.query(date_str=date_str)

    # 2) ENFORCE EXPENSE CATEGORIES (3 buckets)
    capital_cats = {"Maintenance", "General_Expense"}

    fastfood: list[dict] = []
    capital_maintenance: list[dict] = []

    for exp in raw_expenses:
        exp_date = exp.get("date") or date_str
        cat = (exp.get("category") or "General").strip()
        record = {
            "id": exp.get("expense_id"),
            "category": cat,
            "amount": float(exp.get("amount") or 0.0),
            "timestamp": iso_noon_local(exp_date),
        }
        if cat in capital_cats:
            capital_maintenance.append(record)
        else:
            fastfood.append(record)

    charging_expenses: list[dict] = []
    for charge in raw_charges:
        ch_date = charge.get("date") or date_str
        charging_expenses.append({
            "id": charge.get("session_id"),
            "category": "charging",
            "amount": float(charge.get("cost") or 0.0),
            "timestamp": iso_noon_local(ch_date),
        })

    # 3) NORMALIZE DATASETS
    normalized_trips: list[dict] = []
    for trip in raw_trips:
        normalized_trips.append({
            "trip_id": trip.get("trip_id"),
            "date": trip.get("date"),
            "type": trip.get("type"),
            "distance_mi": float(trip.get("distance_mi") or 0.0),
            "duration_min": float(trip.get("duration_min") or 0.0),
            "earnings": float(trip.get("earnings") or 0.0),
            "energy_cost": float(trip.get("energy_cost") or 0.0),
            "profit": float(trip.get("profit") or 0.0),
        })

    normalized_charges: list[dict] = []
    for charge in raw_charges:
        normalized_charges.append({
            "session_id": charge.get("session_id"),
            "date": charge.get("date"),
            "kwh_added": float(charge.get("kwh_added") or 0.0),
            "cost": float(charge.get("cost") or 0.0),
            "duration_min": float(charge.get("duration_min") or 0.0),
            "rate_per_kwh": float(charge.get("rate_per_kwh") or 0.0),
        })

    normalized_telemetry: list[dict] = []
    for point in raw_telemetry:
        normalized_telemetry.append({
            "timestamp": point.get("timestamp"),
            "soc_pct": float(point.get("soc_pct") or 0.0),
            "efficiency_wh_per_mi": float(point.get("efficiency_wh_per_mi") or 0.0),
            "odometer_mi": float(point.get("odometer_mi") or 0.0),
        })

    # 4) CONTROLLED JOINS (trip time windows from SQL)
    trip_timestamps: dict[str, tuple[datetime.datetime, datetime.datetime]] = {}
    trip_time_sql = """
        SELECT RideID, Timestamp_Start, Duration_min
        FROM Rides.Rides
        WHERE CAST(Timestamp_Start AS DATE) = CAST(? AS DATE)
    """
    trip_times = db.execute_query_params(trip_time_sql, (date_str,))
    for row in trip_times:
        ride_id = row.get("RideID")
        start_t = row.get("Timestamp_Start")  # DB datetime (likely naive)
        dur = float(row.get("Duration_min") or 0.0)
        if ride_id and start_t:
            trip_timestamps[str(ride_id)] = (start_t, start_t + datetime.timedelta(minutes=dur))

    # 5) KPI COMPUTATION (STRICT EXCLUSION)
    totalRevenue = round(sum(t["earnings"] for t in normalized_trips), 2)
    food_sum = sum(e["amount"] for e in fastfood)
    charge_sum = sum(e["amount"] for e in charging_expenses)
    totalExpenses = round(food_sum + charge_sum, 2)

    capitalMaintenanceTotal = round(sum(e["amount"] for e in capital_maintenance), 2)
    netProfit = round(totalRevenue - totalExpenses, 2)

    output_data = {
        "Trips": normalized_trips,
        "ChargingSessions": normalized_charges,
        "Expenses": {
            "fastfood": fastfood,
            "charging": charging_expenses,
            "capital_maintenance": capital_maintenance,
        },
        "TessieMetrics": normalized_telemetry,
        "KPIs": {
            "totalRevenue": totalRevenue,
            "totalExpenses": totalExpenses,
            "capitalMaintenanceTotal": capitalMaintenanceTotal,
            "netProfit": netProfit,
        },
    }

    # 6) VALIDATION PASS (MANDATORY)

    # A) No duplicate trip IDs
    trip_ids = [t["trip_id"] for t in normalized_trips if t.get("trip_id")]
    if len(trip_ids) != len(set(trip_ids)):
        raise ValueError("VALIDATION FAILURE: Duplicate trip IDs detected in dataset!")

    # B) SOC trends logically decrease per trip
    for trip in normalized_trips:
        tid = str(trip.get("trip_id"))
        if tid in trip_timestamps:
            start_t, end_t = trip_timestamps[tid]
            trip_telemetry = []
            for point in normalized_telemetry:
                p_time = parse_iso_to_local_naive(point["timestamp"])
                if p_time and start_t <= p_time <= end_t:
                    trip_telemetry.append((p_time, point["soc_pct"]))
            
            if len(trip_telemetry) >= 2:
                # Sort telemetry chronologically
                trip_telemetry.sort(key=lambda x: x[0])
                start_soc = trip_telemetry[0][1]
                end_soc = trip_telemetry[-1][1]
                
                # Allow a 1.0% margin for minor fluctuations/cell balancing noise
                if end_soc > start_soc + 1.0:
                    raise ValueError(
                        f"VALIDATION FAILURE: SOC trend logically increases during trip {tid}! "
                        f"(Start SOC: {start_soc}%, End SOC: {end_soc}%)"
                    )

    # C) Expenses are correctly categorized
    for e in fastfood:
        if e["category"] in capital_cats:
            raise ValueError(
                f"VALIDATION FAILURE: Capital maintenance expense (ID: {e['id']}) present in fastfood operational list!"
            )
            
    for e in capital_maintenance:
        if e["category"] not in capital_cats:
            raise ValueError(
                f"VALIDATION FAILURE: Operational expense (ID: {e['id']}) present in capital_maintenance list!"
            )

    # D) capital_maintenance is NOT included in KPI totals
    expected_ops = round(sum(e["amount"] for e in fastfood) + sum(e["amount"] for e in charging_expenses), 2)
    if totalExpenses != expected_ops:
        raise ValueError("VALIDATION FAILURE: Total Expenses math is skewed or polluted!")
        
    expected_profit = round(totalRevenue - expected_ops, 2)
    if netProfit != expected_profit:
        raise ValueError("VALIDATION FAILURE: Net Profit is polluted by capital maintenance expenses!")

    # E) Output schema matches dashboard contract exactly (no extra, no missing fields)
    expected_keys = {"Trips", "ChargingSessions", "Expenses", "TessieMetrics", "KPIs"}
    if set(output_data.keys()) != expected_keys:
        raise ValueError("VALIDATION FAILURE: Output JSON schema keys do not match dashboard contract exactly!")
        
    expected_expense_keys = {"fastfood", "charging", "capital_maintenance"}
    if set(output_data["Expenses"].keys()) != expected_expense_keys:
        raise ValueError("VALIDATION FAILURE: Expenses category layout does not match dashboard contract exactly!")

    logging.info("Deterministic data pipeline validation PASS successfully!")
    return output_data


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    
    # Default to 2026-05-19 which contains test database elements
    target_date = sys.argv[1] if len(sys.argv) > 1 else "2026-05-19"
    
    try:
        pipeline_output = run_deterministic_pipeline(target_date)
        print(json.dumps(pipeline_output, indent=2))
        sys.exit(0)
    except Exception as e:
        print(json.dumps({"success": False, "validation_error": str(e)}, indent=2), file=sys.stderr)
        sys.exit(1)
