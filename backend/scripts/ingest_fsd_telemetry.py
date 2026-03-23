import os
import sys
import logging
from datetime import datetime
from dotenv import load_dotenv

dotenv_path = os.path.join(os.path.dirname(__file__), '..', '..', 'summit_sync', '.env')
load_dotenv(dotenv_path)

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from services.tessie import TessieClient
from services.vector_store import VectorStore
from services.fsd_normalizer import FSDNormalizer
from services.privacy import PrivacyManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def ingest_latest_drives():
    tessie = TessieClient()
    vs = VectorStore()
    
    vin = os.environ.get("TESSIE_VIN")
    if not vin:
        logging.error("No TESSIE_VIN found in environment.")
        return

    latest_drive = tessie.get_latest_drive(vin)
    if not latest_drive:
        logging.warning("No recent drives found to ingest.")
        return

    drive_id = str(latest_drive.get('drive_id', 'unknown'))
    distance = latest_drive.get('distance', 0.0)
    
    # In a real scenario, FSD % and external conditions would come from advanced telemetry.
    # We will simulate the required metrics for the Canonical Vector Contract.
    fsd_percentage = 0.995 # Simulated high FSD engagement
    traffic_density = 0.6  # Medium-heavy traffic
    weather_severity = 0.2 # Light rain
    terrain_complexity = 0.1 # Flat
    
    try:
        normalized_score = FSDNormalizer.normalize_metrics(
            fsd_percentage, traffic_density, weather_severity, terrain_complexity
        )
    except ValueError as e:
        logging.warning(f"Drive {drive_id} skipped: {e}")
        return

    # Semantic Abstraction & Hashing
    raw_telemetry = str(latest_drive)
    hashed_identity = PrivacyManager.hash_identity(vin)
    hashed_text = PrivacyManager.hash_raw_text(raw_telemetry)
    
    derivation = f"Continuous FSD segment of {distance:.1f} miles. Normalized score: {normalized_score:.3f} (Traffic: {traffic_density}, Weather: {weather_severity})"
    
    vector_data = {
        "vector_id": f"FSD-{drive_id}",
        "source_type": "FSD",
        "timestamp_utc": datetime.utcnow(),
        "vehicle_id": vin,
        "driver_id": hashed_identity,
        "confidence_score": min(normalized_score, 1.0),
        "embedding_model_version": "text-embedding-3-small",
        "raw_text_hash": hashed_text,
        "source_pointer": f"TessieDrive-{drive_id}",
        "derivation_reason": derivation
    }

    success = vs.add_vector(vector_data)
    if success:
        logging.info(f"Successfully ingested and vectorized drive {drive_id}.")
    else:
        logging.error(f"Failed to ingest drive {drive_id}.")

if __name__ == "__main__":
    ingest_latest_drives()
