import os
import json
import logging
from services.config_loader import config_loader

# Explicit Configuration Loading
try:
    config_loader.load()
except RuntimeError as e:
    print(f"FATAL: {e}")
    exit(1)

from services.pipeline import SummitPipeline

def test_modernized_pipeline():
    logging.basicConfig(level=logging.INFO)
    pipeline = SummitPipeline()
    
    # Use the Venmo screenshot for testing
    test_blob = "https://summitstoreus23436.blob.core.windows.net/function-releases/Screenshot_20260221_164352_Venmo.jpg"
    
    print("\n--- Phase 1: SIMULATE ---")
    success, actions, error = pipeline.simulate(test_blob)
    if not success:
        print(f"Simulation Failed: {error}")
        return
    print(f"Proposed Actions: {json.dumps(actions, indent=2)}")
    
    print("\n--- Phase 2: EXECUTE ---")
    success, record, error = pipeline.execute(actions)
    if not success:
        print(f"Execution Failed: {error}")
        return
    print(f"Canonical Artifact Record Created: {record['artifact_id']}")
    
    print("\n--- Phase 3: INTELLIGENCE ---")
    pipeline.intelligence(record)
    print("Intelligence Phase Completed (Vectorized & Logged)")
    
    # Check for NDJSON logs
    if os.path.exists("Audit_Log.ndjson"):
        print("\n--- Verification: NDJSON Logs Found ---")
        with open("Audit_Log.ndjson", "r") as f:
            for line in f:
                print(f"Log event: {line.strip()}")

if __name__ == "__main__":
    test_modernized_pipeline()
