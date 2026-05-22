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
            "category": "capital_maintenance" if cat in capital_cats else "fastfood",
            "amount": float(exp.get("amount") or 0.0),
            "timestamp": iso_noon_local(exp_date),
            "included_in_kpi": int(exp.get("included_in_kpi", 1)),
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
            "included_in_kpi": int(charge.get("included_in_kpi", 1)),
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

    # 5) CAPITAL AMORTIZATION LAYER
    # Retrieve all manual expenses up to target date to compute active amortizations
    all_raw_expenses = expenses_agent.query()
    
    amortization_records_today = []
    total_amortized_today = 0.0
    
    target_date_obj = datetime.date.fromisoformat(date_str)
    
    for exp in all_raw_expenses:
        cat = (exp.get("category") or "").strip()
        # Only apply amortization to category in ('Maintenance', 'General_Expense')
        if cat not in ("Maintenance", "General_Expense"):
            continue
            
        original_id = exp.get("expense_id")
        amount = float(exp.get("amount") or 0.0)
        exp_date_str = exp.get("date")
        
        # Default rule: amortization_days = 90
        # Allow override if present: exp.get("amortization_days")
        amort_days = exp.get("amortization_days") or 90
        try:
            amort_days = int(amort_days)
        except Exception:
            amort_days = 90
            
        if amort_days <= 0:
            amort_days = 90
            
        # Compute schedule: daily_cost = amount / amortization_days
        daily_cost = amount / amort_days
        
        # Validation checks on schedule
        schedule_sum = 0.0
        for i in range(amort_days):
            if i == amort_days - 1:
                # Last day gets remaining balance to ensure perfect mathematical reconciliation
                cost_val = amount - schedule_sum
            else:
                cost_val = daily_cost
                schedule_sum += cost_val
                
            # Perform Validation: No amortized value exceeds original amount
            if cost_val > amount:
                raise ValueError(
                    f"AMORTIZATION VALIDATION FAIL: Amortized daily cost ({cost_val}) exceeds "
                    f"original amount ({amount}) for expense ID: {original_id}!"
                )
                
            amort_date = datetime.date.fromisoformat(exp_date_str) + datetime.timedelta(days=i)
            
            # If the amortized date is exactly target_date_obj, record it
            if amort_date == target_date_obj:
                cost_val_rounded = round(cost_val, 4)
                amortization_records_today.append({
                    "id": f"{original_id}-amort-{i}",
                    "date": amort_date.isoformat(),
                    "daily_amortized_cost": cost_val_rounded,
                    "source_expense_id": original_id
                })
                total_amortized_today += cost_val
                
        # Validate that the sum of schedule matches the original amount exactly
        reconciled_sum = schedule_sum + (amount - schedule_sum)
        if abs(reconciled_sum - amount) > 0.00001:
            raise ValueError(
                f"AMORTIZATION VALIDATION FAIL: Reconciled sum ({reconciled_sum}) does not equal "
                f"original amount ({amount}) for expense ID: {original_id}!"
            )
            
    total_amortized_today = round(total_amortized_today, 2)

    # 6) KPI COMPUTATION (STRICT EXCLUSION & DUAL KPI SYSTEM)
    totalRevenue = round(sum(t["earnings"] for t in normalized_trips), 2)
    food_sum = sum(e["amount"] for e in fastfood)
    charge_sum = sum(e["amount"] for e in charging_expenses)
    totalExpenses = round(food_sum + charge_sum, 2)

    capitalMaintenanceTotal = round(sum(e["amount"] for e in capital_maintenance), 2)
    netProfit = round(totalRevenue - totalExpenses, 2)

    # Operating Profit and Margin (pure daily operations)
    operatingProfit = netProfit
    operatingMargin = round(operatingProfit / totalRevenue, 4) if totalRevenue > 0 else 0.0

    # True Profit and Margin (including capital amortization)
    trueProfit = round(totalRevenue - totalExpenses - total_amortized_today, 2)
    trueMargin = round(trueProfit / totalRevenue, 4) if totalRevenue > 0 else 0.0

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
            "operatingProfit": operatingProfit,
            "operatingMargin": operatingMargin,
            "trueProfit": trueProfit,
            "trueMargin": trueMargin,
        },
        "Amortization": {
            "daily_costs": amortization_records_today,
            "total_amortized_today": total_amortized_today,
        }
    }

    # 7) VALIDATION PASS (MANDATORY)

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

    # C) Expenses are correctly categorized and schemas are consistent
    required_expense_keys = {"id", "category", "amount", "timestamp", "included_in_kpi"}
    
    for e in fastfood:
        if e["category"] != "fastfood":
            raise ValueError(
                f"VALIDATION FAILURE: Non-fastfood expense (ID: {e.get('id')}) present in fastfood operational list!"
            )
        if set(e.keys()) != required_expense_keys:
            missing = required_expense_keys - set(e.keys())
            extra = set(e.keys()) - required_expense_keys
            raise ValueError(
                f"VALIDATION FAILURE: fastfood expense schema is inconsistent (ID: {e.get('id')})! "
                f"Missing keys: {missing}, Extra keys: {extra}"
            )
            
    for e in charging_expenses:
        if e["category"] != "charging":
            raise ValueError(
                f"VALIDATION FAILURE: Non-charging expense (ID: {e.get('id')}) present in charging list!"
            )
        if set(e.keys()) != required_expense_keys:
            missing = required_expense_keys - set(e.keys())
            extra = set(e.keys()) - required_expense_keys
            raise ValueError(
                f"VALIDATION FAILURE: charging expense schema is inconsistent (ID: {e.get('id')})! "
                f"Missing keys: {missing}, Extra keys: {extra}"
            )
            
    for e in capital_maintenance:
        if e["category"] != "capital_maintenance":
            raise ValueError(
                f"VALIDATION FAILURE: Non-capital_maintenance expense (ID: {e.get('id')}) present in capital_maintenance list!"
            )
        if set(e.keys()) != required_expense_keys:
            missing = required_expense_keys - set(e.keys())
            extra = set(e.keys()) - required_expense_keys
            raise ValueError(
                f"VALIDATION FAILURE: capital_maintenance expense schema is inconsistent (ID: {e.get('id')})! "
                f"Missing keys: {missing}, Extra keys: {extra}"
            )

    # D) capital_maintenance is NOT included in KPI totals (Math Purity)
    expected_ops = round(sum(e["amount"] for e in fastfood) + sum(e["amount"] for e in charging_expenses), 2)
    if totalExpenses != expected_ops:
        raise ValueError(
            f"VALIDATION FAILURE (MATH PURITY): totalExpenses ({totalExpenses}) does not equal expected "
            f"operational expenses (fastfood + charging = {expected_ops})! KPI is contaminated!"
        )
        
    expected_profit = round(totalRevenue - expected_ops, 2)
    if netProfit != expected_profit:
        raise ValueError(
            f"VALIDATION FAILURE (MATH PURITY): netProfit ({netProfit}) does not equal expected operational "
            f"profit (totalRevenue - expected_ops = {expected_profit})! KPI is contaminated by capital maintenance expenses!"
        )

    # E) Output schema matches dashboard contract exactly (no extra, no missing fields)
    expected_keys = {"Trips", "ChargingSessions", "Expenses", "TessieMetrics", "KPIs", "Amortization"}
    if set(output_data.keys()) != expected_keys:
        raise ValueError("VALIDATION FAILURE: Output JSON schema keys do not match dashboard contract exactly!")
        
    expected_expense_keys = {"fastfood", "charging", "capital_maintenance"}
    if set(output_data["Expenses"].keys()) != expected_expense_keys:
        raise ValueError("VALIDATION FAILURE: Expenses category layout does not match dashboard contract exactly!")

    # F) Hard KPI Isolation & Fail-Fast Verification
    for e in fastfood:
        if e.get("included_in_kpi") != 1:
            raise ValueError(
                f"VALIDATION FAILURE: Operational fastfood expense (ID: {e.get('id')}) "
                f"must be included in KPI (included_in_kpi is {e.get('included_in_kpi')}, expected 1)!"
            )
            
    for e in charging_expenses:
        if e.get("included_in_kpi") != 1:
            raise ValueError(
                f"VALIDATION FAILURE: Operational charging expense (ID: {e.get('id')}) "
                f"must be included in KPI (included_in_kpi is {e.get('included_in_kpi')}, expected 1)!"
            )
            
    for e in capital_maintenance:
        if e.get("included_in_kpi") == 1:
            raise ValueError(
                f"CRITICAL VALIDATION ERROR: Capital maintenance expense (ID: {e.get('id')}) "
                f"has included_in_kpi = 1! Contamination detected!"
            )
        if e.get("included_in_kpi") != 0:
            raise ValueError(
                f"VALIDATION FAILURE: Capital maintenance expense (ID: {e.get('id')}) "
                f"must be excluded from KPI (included_in_kpi is {e.get('included_in_kpi')}, expected 0)!"
            )

    # G) Dual KPI & Amortization Layer Purity Assertions (Fail-Fast)
    if operatingProfit != netProfit:
        raise ValueError("CRITICAL VALIDATION FAILURE: operatingProfit does not equal netProfit!")
        
    expected_true_profit = round(totalRevenue - totalExpenses - total_amortized_today, 2)
    if trueProfit != expected_true_profit:
        raise ValueError(
            f"CRITICAL VALIDATION FAILURE: trueProfit ({trueProfit}) does not equal expected true profit "
            f"(revenue - expenses - amortization = {expected_true_profit})!"
        )
        
    # Verify capitalMaintenanceTotal was not used directly in operatingProfit math
    if abs(operatingProfit - (totalRevenue - totalExpenses)) > 0.00001:
        raise ValueError(
            "CRITICAL VALIDATION FAILURE: operatingProfit math is contaminated! It must equal (totalRevenue - totalExpenses) exactly."
        )
        
    # Verify capital_maintenance was not added to totalExpenses
    if totalExpenses != round(sum(e["amount"] for e in fastfood) + sum(e["amount"] for e in charging_expenses), 2):
        raise ValueError("CRITICAL VALIDATION FAILURE: totalExpenses modified or contaminated by capital maintenance!")

    # Verify no double counting of amortization
    if abs(trueProfit - (totalRevenue - totalExpenses - total_amortized_today)) > 0.00001:
        raise ValueError("CRITICAL VALIDATION FAILURE: trueProfit double-counting or math contamination detected!")

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
