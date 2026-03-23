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

def process_backlog_blob():
    logging.basicConfig(level=logging.INFO)
    pipeline = SummitPipeline()
    
    # Selected blob from 2026-02-21
    test_blob = "https://summitstoreus23436.blob.core.windows.net/function-releases/Screenshot_20260221_181453_Uber%20Driver.jpg"
    
    print(f"\n--- Processing: {os.path.basename(test_blob)} ---")
    
    # Phase 1: SIMULATE
    success, actions, error = pipeline.simulate(test_blob)
    if not success:
        print(f"SIMULATE Failed: {error}")
        return
    print(f"SIMULATE: Result {actions['classification']} (Confidence: {actions['confidence']})")
    
    # Phase 2: EXECUTE
    success, record, error = pipeline.execute(actions)
    if not success:
        print(f"EXECUTE Failed: {error}")
        return
    print(f"EXECUTE: Canonical Record Created for {record['artifact_id']}")
    
    # Phase 3: INTELLIGENCE
    pipeline.intelligence(record)
    print("INTELLIGENCE: Vectorization and Logging Complete.")

if __name__ == "__main__":
    process_backlog_blob()
