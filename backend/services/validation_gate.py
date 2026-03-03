import os
import json
import logging
import shutil
import time
from datetime import datetime
from typing import Dict, Any, Optional
from pydantic import ValidationError

class ValidationGate:
    """
    Enforces SummitOS safety gates and provides NDJSON observability.
    Handles Quarantine for non-compliant data.
    """
    def __init__(self, log_path: str = "Audit_Log.ndjson", quarantine_root: str = "Quarantine"):
        self.log_path = log_path
        self.quarantine_root = quarantine_root
        
        log_dir = os.path.dirname(self.log_path)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
            
        if self.quarantine_root:
            os.makedirs(self.quarantine_root, exist_ok=True)

    def log_event(self, artifact_id: str, action: str, phase: str, duration_ms: int, result: str, error: Optional[str] = None):
        """Emits an NDJSON log event."""
        event = {
            "timestamp": datetime.now().isoformat(),
            "artifact_id": artifact_id,
            "action": action,
            "phase": phase,
            "duration_ms": duration_ms,
            "result": result,
            "error": error
        }
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event) + "\n")
        except Exception as e:
            logging.error(f"Failed to write NDJSON log: {e}")

    def validate_record(self, model_class, data: Dict[str, Any]) -> bool:
        """Validates data against a Pydantic model class."""
        try:
            model_class(**data)
            return True
        except ValidationError as e:
            logging.error(f"Validation FAILED for {model_class.__name__}: {e.json()}")
            return False

    def quarantine(self, artifact_id: str, artifact_path: Optional[str], proposed_actions: dict, reason: str):
        """Moves artifact and metadata to quarantine."""
        dt = datetime.now().strftime("%Y/%B")
        target_dir = os.path.join(self.quarantine_root, "Rejected_Records", dt)
        os.makedirs(target_dir, exist_ok=True)
        
        # Save rejection reason
        reason_path = os.path.join(target_dir, f"{artifact_id}_rejection.txt")
        with open(reason_path, "w") as f:
            f.write(f"Rejection Reason: {reason}\nTimestamp: {datetime.now().isoformat()}")
            
        # Save proposed actions for debugging
        actions_path = os.path.join(target_dir, f"{artifact_id}_actions.json")
        with open(actions_path, "w") as f:
            json.dump(proposed_actions, f, indent=4)
            
        # Move file if provided (simulated move for now)
        if artifact_path and os.path.exists(artifact_path):
            try:
                shutil.move(artifact_path, os.path.join(target_dir, os.path.basename(artifact_path)))
                logging.info(f"Artifact {artifact_id} moved to quarantine.")
            except Exception as e:
                logging.error(f"Failed to move artifact to quarantine: {e}")
        
        self.log_event(artifact_id, "Validation", "EXECUTE", 0, "QUARANTINE", error=reason)
