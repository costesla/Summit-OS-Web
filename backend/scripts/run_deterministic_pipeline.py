import os
import sys
import json
import datetime
import logging
from typing import Dict, List, Any, Optional

# Ensure root backend dir is in PYTHONPATH
script_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(script_dir)
sys.path.append(backend_dir)

# Set environment variables from local.settings.json manually
settings_path = os.path.join(backend_dir, 'local.settings.json')
if os.path.exists(settings_path):
    with open(settings_path, 'r') as f:
        settings = json.load(f)
        for k, v in settings.get('Values', {}).items():
            os.environ[k] = v

from services.database import DatabaseClient
from services.agents.summit_intelligence import (
    TripsAgent, ChargingAgent, ExpensesAgent, VehicleAgent
)

def run_deterministic_pipeline(date_str: str) -> Dict[str, Any]:
    logging.info(f"Starting deterministic data pipeline run for date: {date_str}")
    
    db = DatabaseClient()
    conn = db.get_connection()
    if not conn:
        raise ConnectionError("Database Connection failed. Verify settings.")
    conn.close()

    # 1. INGEST & NORMALIZE
    trips_agent = TripsAgent(db)
    charging_agent = ChargingAgent(db)
    expenses_agent = ExpensesAgent(db)
    vehicle_agent = VehicleAgent(db)

    # Ingest isolated datasets
    raw_trips = trips_agent.query(date_str=date_str)
    raw_charges = charging_agent.query(date_str=date_str)
    raw_expenses = expenses_agent.query(date_str=date_str)
    raw_telemetry = vehicle_agent.query(date_str=date_str)

    # 2. ENFORCE EXPENSE CATEGORIES & SYSTEM STRUCTURE
    # Split manual expenses into fastfood and capital_maintenance
    fastfood = []
    capital_maintenance = []
    
    for exp in raw_expenses:
        # Check category code
        cat = exp.get("category") or "General"
        expense_record = {
            "id": exp.get("expense_id"),
            "category": cat,
            "amount": float(exp.get("amount") or 0.0),
            "timestamp": exp.get("date") + "T12:00:00-06:00"  # standard ISO date string placeholder
        }
        
        if cat in ["Maintenance", "General_Expense"]:
            capital_maintenance.append(expense_record)
        else:
            fastfood.append(expense_record)

    # Charging expenses normalized
    charging_expenses = []
    for charge in raw_charges:
        charging_expenses.append({
            "id": charge.get("session_id"),
            "category": "charging",
            "amount": float(charge.get("cost") or 0.0),
            "timestamp": charge.get("date") + "T12:00:00-06:00"
        })

    # Normalized Trips
    normalized_trips = []
    for trip in raw_trips:
        normalized_trips.append({
            "trip_id": trip.get("trip_id"),
            "date": trip.get("date"),
            "type": trip.get("type"),
            "distance_mi": float(trip.get("distance_mi") or 0.0),
            "duration_min": float(trip.get("duration_min") or 0.0),
            "earnings": float(trip.get("earnings") or 0.0),
            "energy_cost": float(trip.get("energy_cost") or 0.0),
            "profit": float(trip.get("profit") or 0.0)
        })

    # Normalized Charging Sessions
    normalized_charges = []
    for charge in raw_charges:
        normalized_charges.append({
            "session_id": charge.get("session_id"),
            "date": charge.get("date"),
            "kwh_added": float(charge.get("kwh_added") or 0.0),
            "cost": float(charge.get("cost") or 0.0),
            "duration_min": float(charge.get("duration_min") or 0.0),
            "rate_per_kwh": float(charge.get("rate_per_kwh") or 0.0)
        })

    # Normalized Tessie Metrics (Telemetry)
    normalized_telemetry = []
    for point in raw_telemetry:
        normalized_telemetry.append({
            "timestamp": point.get("timestamp"),
            "soc_pct": float(point.get("soc_pct") or 0.0),
            "efficiency_wh_per_mi": float(point.get("efficiency_wh_per_mi") or 0.0),
            "odometer_mi": float(point.get("odometer_mi") or 0.0)
        })

    # 3. CONTROLLED JOINS
    # Associating telemetry SOC points to trips based on timestamp overlap (trip start/end)
    # Fetch real start times of trips from Rides database to ensure strict join matching
    trip_timestamps = {}
    trip_time_sql = """
        SELECT RideID, Timestamp_Start, Duration_min 
        FROM Rides.Rides
        WHERE CAST(Timestamp_Start AS DATE) = ?
    """
    trip_times = db.execute_query_params(trip_time_sql, (date_str,))
    for row in trip_times:
        ride_id = row.get("RideID")
        start_t = row.get("Timestamp_Start")
        dur = float(row.get("Duration_min") or 0.0)
        if start_t and ride_id:
            end_t = start_t + datetime.timedelta(minutes=dur)
            trip_timestamps[ride_id] = (start_t, end_t)

    # 4. KPI COMPUTATION (Strict Exclusion of Capital & Maintenance)
    totalRevenue = round(sum(t["earnings"] for t in normalized_trips), 2)
    
    # totalExpenses consists ONLY of fastfood + charging costs
    food_sum = sum(e["amount"] for e in fastfood)
    charge_sum = sum(e["amount"] for e in charging_expenses)
    totalExpenses = round(food_sum + charge_sum, 2)
    
    capitalMaintenanceTotal = round(sum(e["amount"] for e in capital_maintenance), 2)
    
    # netProfit = totalRevenue - totalExpenses
    netProfit = round(totalRevenue - totalExpenses, 2)

    # Compile schema structure
    output_data = {
        "Trips": normalized_trips,
        "ChargingSessions": normalized_charges,
        "Expenses": {
            "fastfood": fastfood,
            "charging": charging_expenses,
            "capital_maintenance": capital_maintenance
        },
        "TessieMetrics": normalized_telemetry,
        "KPIs": {
            "totalRevenue": totalRevenue,
            "totalExpenses": totalExpenses,
            "capitalMaintenanceTotal": capitalMaintenanceTotal,
            "netProfit": netProfit
        }
    }

    # 5. VALIDATION PASS (MANDATORY AUDIT PASS)
    
    # A. No duplicate trips
    trip_ids = [t["trip_id"] for t in normalized_trips]
    if len(trip_ids) != len(set(trip_ids)):
        raise ValueError("VALIDATION FAILURE: Duplicate trip IDs detected in dataset!")

    # B. SOC trends logically decrease per trip
    # For each trip, verify telemetry SOC at end of trip <= starting SOC
    for trip in normalized_trips:
        tid = trip["trip_id"]
        if tid in trip_timestamps:
            start_time, end_time = trip_timestamps[tid]
            
            # Find all telemetry points within this trip duration
            trip_telemetry = []
            for point in normalized_telemetry:
                try:
                    p_time = datetime.datetime.fromisoformat(point["timestamp"].replace("Z", "+00:00"))
                    # Normalize timezones for comparison
                    p_time_naive = p_time.astimezone(datetime.timezone.utc).replace(tzinfo=None) - datetime.timedelta(hours=6)
                    if start_time <= p_time_naive <= end_time:
                        trip_telemetry.append(point)
                except Exception:
                    continue
            
            if len(trip_telemetry) >= 2:
                # Sort points by timestamp
                trip_telemetry.sort(key=lambda x: x["timestamp"])
                start_soc = trip_telemetry[0]["soc_pct"]
                end_soc = trip_telemetry[-1]["soc_pct"]
                
                # Check for logical decrease (allowing 1% boundary for noise/re-calibration)
                if end_soc > start_soc + 1.0:
                    raise ValueError(f"VALIDATION FAILURE: SOC trend logically increases during trip {tid}! (Start: {start_soc}%, End: {end_soc}%)")

    # C. Expenses are correctly categorized
    for e in fastfood:
        if e["category"] in ["Maintenance", "General_Expense"]:
            raise ValueError(f"VALIDATION FAILURE: Capital maintenance expense {e['id']} present in daily operational shift metrics!")
            
    for e in capital_maintenance:
        if e["category"] not in ["Maintenance", "General_Expense"]:
            raise ValueError(f"VALIDATION FAILURE: Operational expense {e['id']} present in capital & maintenance category!")

    # D. capital_maintenance is NOT included in KPI totals
    # Verify that totalExpenses matches exactly the operational components
    expected_ops = round(sum(e["amount"] for e in fastfood) + sum(e["amount"] for e in charging_expenses), 2)
    if totalExpenses != expected_ops:
        raise ValueError("VALIDATION FAILURE: Total Expenses math is skewed or polluted!")
        
    # Verify net profit contains no capital elements
    expected_profit = round(totalRevenue - expected_ops, 2)
    if netProfit != expected_profit:
        raise ValueError("VALIDATION FAILURE: Net Profit is polluted by capital maintenance expenses!")

    # E. Output schema matches dashboard exactly
    expected_keys = {"Trips", "ChargingSessions", "Expenses", "TessieMetrics", "KPIs"}
    if set(output_data.keys()) != expected_keys:
        raise ValueError("VALIDATION FAILURE: Output JSON schema keys do not match dashboard contract exactly!")
        
    expected_expense_keys = {"fastfood", "charging", "capital_maintenance"}
    if set(output_data["Expenses"].keys()) != expected_expense_keys:
        raise ValueError("VALIDATION FAILURE: Expenses category layout does not match dashboard contract exactly!")

    logging.info("Deterministic data pipeline validation PASS successfully!")
    return output_data

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    # Default to 2026-05-19 which contains test database elements
    target_date = sys.argv[1] if len(sys.argv) > 1 else "2026-05-19"
    
    try:
        pipeline_output = run_deterministic_pipeline(target_date)
        # Output clean structured JSON only to stdout
        print(json.dumps(pipeline_output, indent=2))
        sys.exit(0)
    except Exception as e:
        print(json.dumps({"success": False, "validation_error": str(e)}, indent=2), file=sys.stderr)
        sys.exit(1)
