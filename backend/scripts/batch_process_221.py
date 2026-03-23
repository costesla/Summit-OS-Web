import os
import json
import logging
from services.config_loader import config_loader
from services.pipeline import SummitPipeline

# Explicit Configuration Loading
try:
    config_loader.load()
except RuntimeError as e:
    print(f"FATAL: {e}")
    exit(1)

def batch_process_221():
    logging.basicConfig(level=logging.INFO)
    pipeline = SummitPipeline()
    
    base_url = "https://summitstoreus23436.blob.core.windows.net/function-releases/"
    blobs = [
        "Screenshot_20260221_174116.jpg",
        "Screenshot_20260221_174246.jpg",
        "Screenshot_20260221_183252.jpg",
        "Screenshot_20260221_183306.jpg",
        "Screenshot_20260221_191412.jpg",
        "Screenshot_20260221_210340_Uber%20Driver.jpg",
        "Screenshot_20260221_210501.jpg",
        "Screenshot_20260221_210546.jpg",
        "Screenshot_20260221_211038_Uber%20Driver.jpg",
        "Screenshot_20260221_222824_Uber%20Driver.jpg",
        "Screenshot_20260221_231335_Uber%20Driver.jpg"
    ]
    
    results = {
        "success": [],
        "failed": []
    }
    
    print(f"\n=== Batch Processing: 2026-02-21 ({len(blobs)} items) ===")
    
    for blob_name in blobs:
        blob_url = base_url + blob_name
        print(f"\n--- Ingesting: {blob_name} ---")
        
        try:
            # Phase 1: SIMULATE
            success, actions, error = pipeline.simulate(blob_url)
            if not success:
                print(f"  SIMULATE Failed: {error}")
                results["failed"].append({"blob": blob_name, "phase": "SIMULATE", "error": error})
                continue
                
            print(f"  SIMULATE: {actions['classification']} ({actions['confidence']}%)")
            
            # Phase 2: EXECUTE
            success, record, error = pipeline.execute(actions)
            if not success:
                print(f"  EXECUTE Failed: {error}")
                results["failed"].append({"blob": blob_name, "phase": "EXECUTE", "error": error})
                continue
                
            print(f"  EXECUTE: Record {record['artifact_id']} created.")
            
            # Phase 3: INTELLIGENCE
            pipeline.intelligence(record)
            print("  INTELLIGENCE: Vectorized and Logged.")
            
            results["success"].append(blob_name)
            
        except Exception as e:
            print(f"  UNEXPECTED ERROR: {e}")
            results["failed"].append({"blob": blob_name, "phase": "ORCHESTRATION", "error": str(e)})

    print("\n=== Batch Processing Summary ===")
    print(f"Successfully processed: {len(results['success'])}")
    print(f"Failed: {len(results['failed'])}")
    
    if results["failed"]:
        print("\nFailures Detail:")
        for f in results["failed"]:
            print(f"  - {f['blob']} ({f['phase']}): {f['error']}")

if __name__ == "__main__":
    batch_process_221()
