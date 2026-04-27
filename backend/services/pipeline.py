import logging
import hashlib
import time
import os
from datetime import datetime
from typing import Dict, Any, Tuple, Optional
import requests # Added for archive_artifact

from services.ocr import OCRClient
from services.database import DatabaseClient
from services.vector_store import VectorStore
from services.validation_gate import ValidationGate
from services.vector_contract import ArtifactRecord, UberTripRecord, CanonicalVector
from services.config_loader import config_loader
from services.sharepoint import SharePointClient

class SummitPipeline:
    """
    Orchestrates the 3-phase Modernized SummitOS Pipeline.
    1. SIMULATE -> ProposedActions
    2. EXECUTE -> Canonical Records (Validated/Persisted)
    3. INTELLIGENCE -> Vectorized/Logged
    """
    def __init__(self):
        self.ocr = OCRClient()
        self.gate = ValidationGate()
        self.vs = VectorStore()
        self.db = DatabaseClient()
        self.sp = SharePointClient()
        
        # Load environment if needed (ConfigLoader already called in entry points)
        logging.info("SummitPipeline: Modernized 3-Phase Orchestrator Initialized.")

    def simulate(self, blob_url: str) -> Tuple[bool, Dict[str, Any], Optional[str]]:
        """Phase 1: Produce ProposedActions with no side effects."""
        start_time = time.time()
        artifact_id = f"sha256-{hashlib.sha256(blob_url.encode()).hexdigest()}"
        
        raw_text = self.ocr.extract_text(blob_url)
        if not raw_text:
            self.gate.log_event(artifact_id, "OCR", "SIMULATE", int((time.time()-start_time)*1000), "FAILURE", "OCR Extract Failed")
            return False, {}, "OCR Failed"

        classification = self.ocr.classify_image_llm(raw_text)
        
        proposed_actions = {
            "artifact_id": artifact_id,
           "source_url": blob_url,
            "classification": classification,
            "raw_text": raw_text,
            "timestamp_epoch": time.time(),
            "confidence": 95.0 # Placeholder for LLM confidence
        }
        
        self.gate.log_event(artifact_id, "Analyze", "SIMULATE", int((time.time()-start_time)*1000), "SUCCESS")
        return True, proposed_actions, None

    def execute(self, proposed_actions: Dict[str, Any]) -> Tuple[bool, Any, Optional[str]]:
        """Phase 2: Validate and Persist Canonical Records."""
        start_time = time.time()
        artifact_id = proposed_actions['artifact_id']
        
        try:
            # 1. Privacy Enforcement: Strip Raw Text from record if needed or hash it
            # Deterministic Routing Labels (Mobility Semantics)
            semantics = self._derive_mobility_semantics(proposed_actions['raw_text'])
            
            # 2. Build ArtifactRecord
            artifact_data = {
                "artifact_id": artifact_id,
                "filename": os.path.basename(proposed_actions['source_url']),
                "source_url": proposed_actions['source_url'],
                "integrity_hash": artifact_id, # Simplified for now
                "ocr_output": {
                    "raw_text": proposed_actions['raw_text'],
                    "confidence": proposed_actions['confidence']
                },
                "provenance": {
                    "ingestion_timestamp": datetime.now().isoformat()
                }
            }
            
            if not self.gate.validate_record(ArtifactRecord, artifact_data):
                 self.gate.quarantine(artifact_id, None, proposed_actions, "ArtifactRecord Schema Violation")
                 return False, None, "Schema Violation"

            # 3. Build UberTripRecord if applicable
            if proposed_actions['classification'] == "Uber_Core":
                trip_raw = self.ocr.parse_ubertrip(proposed_actions['raw_text'])
                trip_data = {
                    "trip_id": f"UT-{artifact_id[:8]}",
                    "artifact_id": artifact_id,
                    "status": "Executed",
                    "classification": "Uber_Core",
                    "financials": {
                        "rider_payment": trip_raw.get('rider_payment', 0),
                        "driver_earnings": trip_raw.get('driver_total', 0),
                        "platform_cut_raw": trip_raw.get('uber_cut', 0)
                    },
                    "mobility_semantics": semantics,
                    "confidence_score": proposed_actions['confidence']
                }
                
                if not self.gate.validate_record(UberTripRecord, trip_data):
                    self.gate.quarantine(artifact_id, None, proposed_actions, "UberTripRecord Schema/Privacy Violation")
                    return False, None, "Schema/Privacy Violation"
                
                # Persistence
                self.db.save_trip(trip_data)
                
            self.gate.log_event(artifact_id, "Persistence", "EXECUTE", int((time.time()-start_time)*1000), "SUCCESS")
            return True, artifact_data, None
            
        except Exception as e:
            self.gate.log_event(artifact_id, "Execution", "EXECUTE", 0, "FAILURE", error=str(e))
            return False, None, str(e)

    def _derive_mobility_semantics(self, text: str) -> Dict[str, str]:
        """Privacy-safe semantics extraction."""
        # Simple rule-based extraction for now
        city = "Phoenix" # Default
        state = "AZ"
        pickup = "_Pickup/Unspecified"
        dropoff = "_Dropoff/Unspecified"
        
        if "Sky Harbor" in text: pickup = "_Pickup/PHX-Airport"
        if "Old Town" in text: dropoff = "_Dropoff/Scottsdale-OldTown"
        
        return {
            "pickup_label": pickup,
            "dropoff_label": dropoff,
            "city": city,
            "state": state
        }

    def intelligence(self, record: Dict[str, Any]):
        """
        Phase 3: INTELLIGENCE
        Emits governed outputs, vectorizes data, and archives artifacts.
        """
        start_time = time.time()
        try:
            # 1. Vectorization
            artifact_id = record['artifact_id']
            self.vs.add_document(
                filename=record['filename'],
                content=record['ocr_output']['raw_text'],
                metadata={"artifact_id": artifact_id, "classification": "Modernized"}
            )
            
            # 2. SharePoint Archival (Extension)
            if record.get('source_url'):
                self.archive_artifact(record)

            duration = int((time.time() - start_time) * 1000)
            self.gate.log_event(
                artifact_id=record['artifact_id'],
                action="Vectorization & Archival",
                phase="INTELLIGENCE",
                duration_ms=duration,
                result="SUCCESS"
            )
            logging.info(f"Pipeline INTELLIGENCE Complete for {record['artifact_id']}")

        except Exception as e:
            duration = int((time.time() - start_time) * 1000)
            self.gate.log_event(
                artifact_id=record['artifact_id'],
                action="Intelligence",
                phase="INTELLIGENCE",
                duration_ms=duration,
                result="FAILURE",
                error=str(e)
            )
            logging.error(f"Intelligence Phase Error: {e}")

    def archive_artifact(self, record: Dict[str, Any]):
        """Moves processed artifact to SharePoint archival with metadata tagging."""
        try:
            source_url = record.get('source_url')
            if not source_url: return

            # Construct destination path: YYYY/MM/DD/artifact_id.jpg
            # Use provenance timestamp if possible, or now()
            prov = record.get('provenance', {}).get('ingestion_timestamp', datetime.now().isoformat())
            ts = datetime.fromisoformat(prov.replace('Z', '+00:00'))
            dest_folder = ts.strftime("%Y/%m/%d")
            filename = f"{record['artifact_id'][:12]}.jpg"
            dest_path = f"{dest_folder}/{filename}"

            logging.info(f"Archiving artifact to SharePoint: {dest_path}")

            # 1. Download blob content
            response = requests.get(source_url)
            response.raise_for_status()
            content = response.content

            # 2. Upload to SharePoint
            item = self.sp.upload_file(filename, dest_path, file_content=content)
            
            if item:
                # 3. Update Metadata
                metadata = {
                    "ArtifactID": record['artifact_id'],
                    "Classification": record.get('classification', 'Unknown'),
                    "IngestionDate": datetime.now().strftime("%Y-%m-%d")
                }
                self.sp.update_metadata(item['id'], metadata)
                logging.info(f"✅ SharePoint Archival Success: {dest_path}")
                
                self.gate.log_event(
                    artifact_id=record['artifact_id'],
                    action="Archival",
                    phase="INTELLIGENCE",
                    duration_ms=0,
                    result="SUCCESS"
                )

        except Exception as e:
            logging.error(f"Archival failed for {record['artifact_id']}: {e}")
            self.gate.log_event(
                artifact_id=record['artifact_id'],
                action="Archival",
                phase="INTELLIGENCE",
                duration_ms=0,
                result="FAILURE",
                error=str(e)
            )
