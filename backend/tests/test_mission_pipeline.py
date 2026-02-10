import os
import sys
import time
import json
import logging
from datetime import datetime

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

from services.orchestrator import OrchestratorHub

def test_pipeline():
    logging.basicConfig(level=logging.INFO)
    
    # Mock Data (Extraction Agent Output)
    trip_data = {
        "trip_id": "T_PARALLEL_TEST_123",
        "classification": "Uber_Core",
        "service_type": "Uber Comfort",
        "rider_payment": 60.0,
        "driver_total": 40.0,
        "distance_miles": 20.0,
        "duration_minutes": 45,
        "source_url": "https://mockstorage.blob.core.windows.net/uploads/test_orchestration.jpg",
        "timestamp_epoch": time.time(),
        "start_location": "Castle Pines, CO",
        "end_location": "Colorado Springs, CO",
        "start_coords": (39.467, -104.896),
        "end_coords": (38.833, -104.821),
        "start_soc_perc": 90.0,
        "end_soc_perc": 78.0,
        "energy_used_kWh": 11.2,
        "airport": False,
        "block_name": "Orchestration_Block"
    }

    print("\n--- [START] SummitOS Multi-Agent Orchestration Test ---")
    
    # 1. Orchestration
    print("Step 1: Running Parallel Orchestrator...")
    orchestrator = OrchestratorHub()
    final_deliverables = orchestrator.orchestrate(trip_data)
    
    print(f" > Compliance Verdict: {final_deliverables.get('compliance_verdict')}")
    print(f" > Margin: {final_deliverables.get('margin_percent', 0):.1f}%")
    print(f" > Wh/mi: {final_deliverables.get('wh_mi', 0):.1f}")
    
    # 2. Verification of Pipeline Gates
    print("Step 2: Verifying Gates...")
    for gate, passed in final_deliverables.get('compliance_gates', {}).items():
        status = "PASS" if passed else "FAIL"
        print(f"   [GATE] {gate.upper()}: {status}")

    # 3. Output Verification
    output_path = final_deliverables.get('output_path')
    print(f"Step 3: Checking Outputs at {output_path}")
    
    md_file = os.path.join(output_path, "Trip_Summary.md")
    json_file = os.path.join(output_path, f"{final_deliverables['trip_id']}_sidecar.json")
    
    if os.path.exists(md_file):
        print(" [SUCCESS] Orchestrated Card created.")
        with open(md_file, "r", encoding="utf-8") as f:
            print(f"\n--- Card Preview ---\n{f.read()[:600]}...\n")
    else:
        print(" [FAILURE] Orchestrated Card missing.")

    if os.path.exists(json_file):
        print(" [SUCCESS] Canoncial Sidecar created.")
    else:
        print(" [FAILURE] Canoncial Sidecar missing.")

    print("--- [END] Orchestration Test ---")

if __name__ == "__main__":
    test_pipeline()
