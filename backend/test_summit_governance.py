import os
import sys
import json
import logging

# Ensure root backend dir is in PYTHONPATH
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

# Configure logging
logging.basicConfig(level=logging.INFO)

# Set environment variables from local.settings.json manually to ensure they are loaded
settings_path = os.path.join(os.path.dirname(__file__), 'local.settings.json')
if os.path.exists(settings_path):
    with open(settings_path, 'r') as f:
        settings = json.load(f)
        for k, v in settings.get('Values', {}).items():
            os.environ[k] = v

from services.database import DatabaseClient
from services.agents.summit_intelligence import (
    TripsAgent, ChargingAgent, ExpensesAgent, VehicleAgent,
    MasterOrchestrator, GovernedQueryRouter
)

def run_diagnostics():
    print("=== STARTING SUMMIT INTELLIGENCE GOVERNED CORE DIAGNOSTICS ===")
    
    db = DatabaseClient()
    conn = db.get_connection()
    if not conn:
        print("[FAIL] Database Connection failed. Check local.settings.json or network permissions.")
        return
    print("[PASS] Database Connection established successfully.")
    conn.close()
    
    # 1. Test Router
    print("\n--- 1. Testing GovernedQueryRouter ---")
    router = GovernedQueryRouter()
    
    queries_to_test = [
        "What is my net profit today?",
        "Show my uber trips from last week",
        "How much did I spend on charging?",
        "What's my vehicle efficiency?",
        "List dining expenses for May 10 2026"
    ]
    
    for q in queries_to_test:
        res = router.parse_query(q)
        print(f"Query: '{q}'")
        print(f" -> Target Agent: {res.get('target_agent')}")
        print(f" -> Extracted Date: {res.get('date_str')} / Range: [{res.get('start_date')}, {res.get('end_date')}]")
        print("-" * 40)
        
    # 2. Test Isolated Agents
    print("\n--- 2. Testing Isolated Agents Queries ---")
    
    # Range of dates where we might have dummy/test data or real sync data
    start = "2026-05-01"
    end = "2026-05-19"
    
    trips_agent = TripsAgent(db)
    charging_agent = ChargingAgent(db)
    expenses_agent = ExpensesAgent(db)
    vehicle_agent = VehicleAgent(db)
    
    print(f"Querying TripsAgent for range [{start}, {end}]...")
    trips_data = trips_agent.query(start_date=start, end_date=end)
    print(f" -> Found {len(trips_data)} trips.")
    if trips_data:
        print(" -> Sample Trip Schema Validation:")
        print(json.dumps(trips_data[0], indent=2))
        # Ensure no cross domain properties leak
        assert "cost" not in trips_data[0]
        assert "category" not in trips_data[0]
        assert "soc_pct" not in trips_data[0]
        print(" -> [PASS] Trips domain isolation check.")
        
    print(f"\nQuerying ChargingAgent for range [{start}, {end}]...")
    charging_data = charging_agent.query(start_date=start, end_date=end)
    print(f" -> Found {len(charging_data)} charging sessions.")
    if charging_data:
        print(" -> Sample Charging Schema Validation:")
        print(json.dumps(charging_data[0], indent=2))
        assert "earnings" not in charging_data[0]
        assert "profit" not in charging_data[0]
        print(" -> [PASS] Charging domain isolation check.")
        
    print(f"\nQuerying ExpensesAgent for range [{start}, {end}]...")
    expenses_data = expenses_agent.query(start_date=start, end_date=end)
    print(f" -> Found {len(expenses_data)} expenses.")
    if expenses_data:
        print(" -> Sample Expense Schema Validation:")
        print(json.dumps(expenses_data[0], indent=2))
        assert "earnings" not in expenses_data[0]
        assert "kwh_added" not in expenses_data[0]
        print(" -> [PASS] Expenses domain isolation check.")
        
    print(f"\nQuerying VehicleAgent for range [{start}, {end}]...")
    vehicle_data = vehicle_agent.query(start_date=start, end_date=end)
    print(f" -> Found {len(vehicle_data)} telemetry records.")
    if vehicle_data:
        print(" -> Sample Vehicle Schema Validation:")
        print(json.dumps(vehicle_data[0], indent=2))
        assert "earnings" not in vehicle_data[0]
        assert "amount" not in vehicle_data[0]
        print(" -> [PASS] Vehicle domain isolation check.")
        
    # 3. Test Master Orchestrator aggregation & financial reconciliation
    print("\n--- 3. Testing Master Orchestrator aggregation ---")
    orchestrator = MasterOrchestrator(db)
    dashboard = orchestrator.aggregate_dashboard(start_date=start, end_date=end)
    print(" -> Aggregated Dashboard Schema Validation:")
    print(json.dumps({
        "total_earnings": dashboard.get("total_earnings"),
        "total_charging_cost": dashboard.get("total_charging_cost"),
        "total_expenses": dashboard.get("total_expenses"),
        "total_energy_cost": dashboard.get("total_energy_cost"),
        "net_profit": dashboard.get("net_profit"),
        "num_trips": len(dashboard.get("trips", [])),
        "num_charges": len(dashboard.get("charging_sessions", [])),
        "num_expenses": len(dashboard.get("expenses", []))
    }, indent=2))
    
    # Financial calculation verification
    calc_profit = round(dashboard["total_earnings"] - dashboard["total_charging_cost"] - dashboard["total_expenses"], 2)
    assert dashboard["net_profit"] == calc_profit, f"Mismatch: Dashboard profit = {dashboard['net_profit']}, Calculated = {calc_profit}"
    print(f" -> [PASS] Financial calculations match successfully (Net Profit: {dashboard['net_profit']}).")
    
    print("\n=== GOVERNED CORE DIAGNOSTICS COMPLETE: ALL PASS ===")

if __name__ == '__main__':
    run_diagnostics()
