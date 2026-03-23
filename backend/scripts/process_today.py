import os
import logging
from azure.storage.blob import BlobServiceClient
from services.config_loader import config_loader
from services.pipeline import SummitPipeline

try:
    config_loader.load()
except RuntimeError as e:
    print(f"FATAL: {e}")
    exit(1)

def process_today():
    logging.basicConfig(level=logging.INFO)
    pipeline = SummitPipeline()
    
    conn_str = os.environ.get("AzureWebJobsStorage")
    container_name = "thor-backups"
    
    blob_service_client = BlobServiceClient.from_connection_string(conn_str)
    container_client = blob_service_client.get_container_client(container_name)
    
    # Prefix for today: 'Screenshot_20260223'
    prefix = "Screenshot_20260223"
    print(f"Scanning container '{container_name}' for blobs starting with '{prefix}'...")
    
    blobs = list(container_client.list_blobs(name_starts_with=prefix))
    
    if not blobs:
        print("No blobs found for today.")
        return

    results = {"success": [], "failed": []}
    
    print(f"\n=== Batch Processing: 2026-02-23 ({len(blobs)} items) ===")
    
    from azure.storage.blob import generate_blob_sas, BlobSasPermissions
    from datetime import datetime, timedelta, timezone

    for blob in blobs:
        # Generate SAS token
        sas_token = generate_blob_sas(
            account_name=blob_service_client.account_name,
            container_name=container_name,
            blob_name=blob.name,
            account_key=blob_service_client.credential.account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.now(timezone.utc) + timedelta(hours=1)
        )
        
        blob_url = f"https://summitstoreus23436.blob.core.windows.net/{container_name}/{blob.name}?{sas_token}"
        print(f"\n--- Ingesting: {blob.name} ---")
        
        try:
            # Phase 1: SIMULATE
            success, actions, error = pipeline.simulate(blob_url)

            if not success:
                print(f"  SIMULATE Failed: {error}")
                results["failed"].append({"blob": blob.name, "phase": "SIMULATE", "error": error})
                continue
                
            print(f"  SIMULATE: {actions['classification']} ({actions['confidence']}%)")
            
            # Phase 2: EXECUTE
            success, record, error = pipeline.execute(actions)
            if not success:
                print(f"  EXECUTE Failed: {error}")
                results["failed"].append({"blob": blob.name, "phase": "EXECUTE", "error": error})
                continue
                
            print(f"  EXECUTE: Record {record['artifact_id']} created.")
            
            # Phase 3: INTELLIGENCE
            pipeline.intelligence(record)
            print("  INTELLIGENCE: Vectorized and Logged.")
            
            results["success"].append(blob.name)
            
        except Exception as e:
            print(f"  UNEXPECTED ERROR: {e}")
            results["failed"].append({"blob": blob.name, "phase": "ORCHESTRATION", "error": str(e)})

    print("\n=== Batch Processing Summary ===")
    print(f"Successfully processed: {len(results['success'])}")
    print(f"Failed: {len(results['failed'])}")
    
    if results["failed"]:
        print("\nFailures Detail:")
        for f in results["failed"]:
            print(f"  - {f['blob']} ({f['phase']}): {f['error']}")

if __name__ == "__main__":
    process_today()
