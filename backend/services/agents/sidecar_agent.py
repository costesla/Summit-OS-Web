import os
import json
import logging
import hashlib
from datetime import datetime
from typing import Dict, Any

class SidecarAgent:
    def __init__(self, root_dir: str = r"C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\SummitOS_Data"):
        self.root_dir = root_dir

    def process(self, verified_data: Dict[str, Any]) -> str:
        """
        Creates canoncial folder structure and saves the JSON sidecar.
        """
        logging.info("SidecarAgent: Finalizing artifact lineage...")
        
        # 1. Determine Path Components
        dt = datetime.fromtimestamp(verified_data.get('timestamp_epoch', datetime.now().timestamp()))
        year = dt.strftime("%Y")
        month = dt.strftime("%B")
        week = f"Week {dt.isocalendar()[1]}"
        date_folder = dt.strftime("%m.%d.%y")
        block = verified_data.get('block_name', 'Default_Block')
        trip_id = verified_data.get('trip_id', 'Unknown_Trip')

        trip_path = os.path.join(self.root_dir, year, month, week, date_folder, block, trip_id)
        os.makedirs(trip_path, exist_ok=True)

        # 2. Add Hash & Lineage
        source_url = verified_data.get('source_url', '')
        verified_data['artifact_hash'] = hashlib.sha256(source_url.encode()).hexdigest()
        verified_data['ingestion_time'] = datetime.now().isoformat()
        
        # 3. Save Sidecar
        sidecar_filename = f"{trip_id}_sidecar.json"
        sidecar_path = os.path.join(trip_path, sidecar_filename)
        
        with open(sidecar_path, "w") as f:
            json.dump(verified_data, f, indent=4, default=str)
            
        logging.info(f"SidecarAgent: Sidecar created at {sidecar_path}")
        return trip_path
