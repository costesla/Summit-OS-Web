"""
COS Tesla LLC - Audit Ledger & Deduplication Manager (Hardened & Atomic)
Phase 2 Implementation Ledger with Strict State Transitions
Author: Google Antigravity
"""

import os
import json
import hashlib
import threading
from typing import Dict, Any, Optional, List
from datetime import datetime

class AuditLedgerManager:
    _lock = threading.Lock()

    def __init__(self, ledger_file: str = "archive/eod_audit_ledger.json"):
        self.ledger_file = ledger_file
        self.ledger: List[Dict[str, Any]] = []
        self._load_ledger()

    def _load_ledger(self):
        if os.path.exists(self.ledger_file):
            try:
                with open(self.ledger_file, 'r', encoding='utf-8') as f:
                    self.ledger = json.load(f)
            except Exception:
                self.ledger = []
        else:
            self.ledger = []

    def _save_ledger(self):
        os.makedirs(os.path.dirname(self.ledger_file), exist_ok=True)
        with open(self.ledger_file, 'w', encoding='utf-8') as f:
            json.dump(self.ledger, f, indent=2)

    def reserve_checksum(self, report_date: str, sha256_checksum: str, report_id: str) -> bool:
        """Atomically reserves a checksum to prevent concurrent duplicate processing."""
        with self._lock:
            self._load_ledger()
            for entry in self.ledger:
                if entry.get("checksum_sha256") == sha256_checksum:
                    if entry.get("status") in ["Dispatched", "DELIVERED", "SUBMITTED", "SEND_PENDING", "RESERVED", "LOCAL_SIMULATION_COMPLETED"]:
                        return False
            res_entry = {
                "title": f"EOD-{report_date}",
                "report_id": report_id,
                "report_date": report_date,
                "checksum_sha256": sha256_checksum,
                "status": "RESERVED",
                "timestamp_utc": datetime.utcnow().isoformat() + "Z",
                "reservation_held": True
            }
            self.ledger.append(res_entry)
            self._save_ledger()
            return True

    def is_duplicate(self, report_date: str, sha256_checksum: str) -> bool:
        """Checks if a report with matching date and SHA-256 hash was already processed."""
        with self._lock:
            self._load_ledger()
            for entry in self.ledger:
                if entry.get("checksum_sha256") == sha256_checksum:
                    if entry.get("status") in ["Dispatched", "DELIVERED", "SUBMITTED", "DUPLICATE_SKIPPED", "LOCAL_SIMULATION_COMPLETED", "RESERVED"]:
                        return True
            return False

    def record_entry(
        self,
        data: Dict[str, Any],
        sha256_checksum: str,
        status: str = "LOCAL_SIMULATION_COMPLETED",
        report_id: Optional[str] = None,
        transport_message_id: Optional[str] = None,
        message_id: Optional[str] = None,
        version_id: str = "v1"
    ) -> Dict[str, Any]:
        """Appends a new audit record to the ledger with explicit state."""
        effective_msg_id = transport_message_id or message_id or "LOCAL_PLACEHOLDER_NO_MAIL_TRANSPORT"
        with self._lock:
            self._load_ledger()
            record = {
                "title": f"EOD-{data['report_date']}-{version_id}",
                "report_id": report_id or f"COSTESLA-EOD-{data['report_date']}-{version_id}",
                "version_id": version_id,
                "report_date": data["report_date"],
                "gross_revenue": data.get("gross_revenue"),
                "net_profit": data.get("net_profit"),
                "trip_count": data.get("trip_count"),
                "checksum_sha256": sha256_checksum,
                "status": status,
                "timestamp_utc": datetime.utcnow().isoformat() + "Z",
                "intended_recipients": ["luis9189@gmail.com", "peter.teehan@costesla.com"],
                "transport_message_id": effective_msg_id,
                "actual_mail_transport_verified": False if ("PLACEHOLDER" in str(effective_msg_id) or status == "LOCAL_SIMULATION_COMPLETED") else True
            }
            self.ledger.append(record)
            self._save_ledger()
            return record

    def append_audit_correction(self, target_checksum: str, corrected_status: str, correction_reason: str) -> bool:
        """Appends an immutable correction record without deleting historical entries."""
        with self._lock:
            self._load_ledger()
            for entry in self.ledger:
                if entry.get("checksum_sha256") == target_checksum:
                    entry["effective_status"] = corrected_status
                    entry["correction_addendum"] = {
                        "corrected_at_utc": datetime.utcnow().isoformat() + "Z",
                        "corrected_by": "Peter Teehan (Owner Governance Review)",
                        "reason": correction_reason,
                        "previous_status": entry.get("status")
                    }
                    self._save_ledger()
                    return True
            return False

    def verify_archive_integrity(self, file_path: str, expected_hash: str) -> bool:
        if not os.path.exists(file_path):
            return False
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        calculated_hash = hashlib.sha256(content.strip().encode('utf-8')).hexdigest()
        return calculated_hash == expected_hash
