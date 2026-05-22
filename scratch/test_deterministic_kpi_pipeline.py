import sys
import os
import json
import logging

# Ensure root backend dir is in PYTHONPATH
script_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.join(os.path.dirname(script_dir), "backend")
sys.path.insert(0, backend_dir)

# Load settings
settings_path = os.path.join(backend_dir, "local.settings.json")
if os.path.exists(settings_path):
    with open(settings_path, "r", encoding="utf-8") as f:
        settings = json.load(f)
        for k, v in (settings.get("Values", {}) or {}).items():
            os.environ[str(k)] = str(v)

from scripts.run_deterministic_pipeline import run_deterministic_pipeline

def test_pipeline_validation():
    logging.basicConfig(level=logging.INFO)
    print("Testing successful pipeline run...")
    try:
        output = run_deterministic_pipeline("2026-05-19")
        print("Success! Output generated correctly and all validation tests passed.")
        print(f"Operational expenses: {len(output['Expenses']['fastfood'])} fastfood, {len(output['Expenses']['charging'])} charging.")
        print(f"Capital maintenance expenses: {len(output['Expenses']['capital_maintenance'])} items.")
        print(f"KPI totalExpenses: {output['KPIs']['totalExpenses']}, capitalMaintenanceTotal: {output['KPIs']['capitalMaintenanceTotal']}, netProfit: {output['KPIs']['netProfit']}")
        print(f"Amortization: total_amortized_today = {output['Amortization']['total_amortized_today']} ({len(output['Amortization']['daily_costs'])} active schedules today)")
        print(f"Operating Profit: {output['KPIs']['operatingProfit']} (Margin: {output['KPIs']['operatingMargin'] * 100:.2f}%)")
        print(f"True Profit: {output['KPIs']['trueProfit']} (Margin: {output['KPIs']['trueMargin'] * 100:.2f}%)")
    except Exception as e:
        print(f"FAILED: Pipeline run failed unexpectedly: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    test_pipeline_validation()
