import logging
import json
import re
import datetime
from datetime import timezone, timedelta
from typing import Dict, Any, Optional, List

from .database import DatabaseClient
from .ocr import OCRClient

log = logging.getLogger(__name__)

class UberMatcherService:
    def __init__(self):
        self.db = DatabaseClient()
        self.ocr = OCRClient()
        self.mdt = timezone(timedelta(hours=-6))

    def process_image_bytes(self, image_bytes: bytes, filename: str) -> Dict[str, Any]:
        """Runs OCR on image bytes and matches to the closest Tessie Uber drive."""
        log.info(f"Processing Uber card: {filename}")
        
        # 1. OCR (Using the service's existing method if possible, or direct)
        # Assuming OCRClient has a method to process bytes. If not, we'll use a wrapper.
        text = self.ocr.analyze_image_bytes(image_bytes)
        if not text:
            return {"status": "ERROR", "message": "OCR failed to extract text"}

        # 2. Parse Uber Card
        card = self._parse_uber_card(text)
        log.info(f"Parsed Card: {card['driver_earnings']} earned | {card['rider_payment']} rider paid")

        # 3. Match by Timestamp
        # Extract timestamp from filename or metadata if available
        # Format: Screenshot_YYYYMMDD_HHMMSS
        m = re.search(r"Screenshot_(\d{8})_(\d{6})", filename)
        card_dt = None
        if m:
            card_dt = datetime.datetime.strptime(m.group(1)+m.group(2), "%Y%m%d%H%M%S").replace(tzinfo=self.mdt)
        
        if not card_dt:
            # Fallback: Use current time or try to find date in text
            card_dt = datetime.datetime.now(self.mdt)

        # 4. Find closest unmatched Uber drive in SQL
        match = self._find_match(card_dt, tolerance_hours=4)
        if not match:
            return {"status": "NO_MATCH", "parsed": card, "text": text}

        # 5. Update SQL
        uber_cut = round(card["rider_payment"] - card["driver_earnings"], 2)
        sidecar = {
            "source": "uber_card_auto",
            "filename": filename,
            "raw_text": text,
            "card_data": card,
            "matched_at": datetime.datetime.now(self.mdt).isoformat()
        }

        self._update_ride(match["RideID"], card, uber_cut, sidecar)
        
        return {
            "status": "MATCHED",
            "ride_id": match["RideID"],
            "driver_earnings": card["driver_earnings"],
            "rider_payment": card["rider_payment"],
            "uber_cut": uber_cut
        }

    def _parse_uber_card(self, text: str) -> Dict[str, Any]:
        # Logic from ocr_uber_v2.py
        data = {"fare": 0.0, "driver_earnings": 0.0, "tip": 0.0, "rider_payment": 0.0}
        
        # Simple extraction logic (refined for the Uber Trip Details layout)
        m = re.search(r"Your earnings\s*\$?([\d.]+)", text, re.IGNORECASE)
        if m: data["driver_earnings"] = float(m.group(1))
        
        m = re.search(r"Rider payment\s*\$?([\d.]+)", text, re.IGNORECASE)
        if m: data["rider_payment"] = float(m.group(1))
        
        m = re.search(r"Added tip\s*\$?([\d.]+)", text, re.IGNORECASE)
        if m: data["tip"] = float(m.group(1))
        
        return data

    def _find_match(self, card_dt: datetime.datetime, tolerance_hours: int = 4) -> Optional[Dict[str, Any]]:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # Search for Uber-labeled drives around that time (+/- 4 hours)
        # Only looking for ones that don't have a fare yet (to avoid double-matching)
        cursor.execute("""
            SELECT RideID, Timestamp_Start, Classification
            FROM Rides.Rides
            WHERE Classification LIKE '%Uber%'
              AND (Classification LIKE '%DropOff%' OR Classification LIKE '%Dropoff%')
              AND Fare IS NULL
              AND Timestamp_Start BETWEEN ? AND ?
            ORDER BY ABS(DATEDIFF(SECOND, Timestamp_Start, ?)) ASC
        """, (
            card_dt - datetime.timedelta(hours=tolerance_hours),
            card_dt + datetime.timedelta(hours=tolerance_hours),
            card_dt
        ))
        row = cursor.fetchone()
        if row:
            return {"RideID": row[0], "Timestamp_Start": row[1]}
        return None

    def _update_ride(self, ride_id: str, card: Dict[str, Any], uber_cut: float, sidecar: Dict[str, Any]):
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE Rides.Rides
            SET Fare=?, Tip=?, Driver_Earnings=?, Platform_Cut=?, 
                Sidecar_Artifact_JSON=?, LastUpdated=GETDATE()
            WHERE RideID=?
        """, (
            card["rider_payment"], card["tip"], card["driver_earnings"], uber_cut,
            json.dumps(sidecar), ride_id
        ))
        conn.commit()
        cursor.close()
