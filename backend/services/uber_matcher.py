import logging
import json
import re
import datetime
from datetime import timezone, timedelta
from typing import Dict, Any, Optional, List

from .database import DatabaseClient
from .ocr import OCRClient
from .semantic_ingestion import SemanticIngestionService

log = logging.getLogger(__name__)

class UberMatcherService:
    def __init__(self):
        self.db = DatabaseClient()
        self.ocr = OCRClient()
        self.semantic = SemanticIngestionService()
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

        # 2.5 Check if already processed (Idempotency)
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT RideID FROM Rides.Rides WHERE Sidecar_Artifact_JSON LIKE ?", (f'%"{filename}"%',))
        existing_row = cursor.fetchone()
        if existing_row:
            log.info(f"Screenshot {filename} was already processed.")
            # Still return matched data so the caller knows what happened
            return {
                "status": "MATCHED",
                "ride_id": existing_row[0],
                "driver_earnings": card["driver_earnings"],
                "rider_payment": card["rider_payment"]
            }

        # 3. Match by Timestamp
        # Support multiple filename formats:
        # 1. Screenshot_YYYYMMDD_HHMMSS (or with dash Screenshot_YYYYMMDD-HHMMSS)
        # 2. Screenshot YYYY-MM-DD HHMMSS (or with hyphens)
        
        card_dt = None
        
        # Pattern 1: Screenshot_20260328_053614 or Screenshot_20260328-053614
        m1 = re.search(r"Screenshot_(\d{8})[-_](\d{6})", filename)
        if m1:
            card_dt = datetime.datetime.strptime(m1.group(1)+m1.group(2), "%Y%m%d%H%M%S")
            
        # Pattern 2: Screenshot 2026-04-27 070003 or Screenshot 2026-04-27-070003
        if not card_dt:
            m2 = re.search(r"Screenshot.*?(\d{4}-\d{2}-\d{2}).*?(\d{2})[-_:]?(\d{2})[-_:]?(\d{2})", filename)
            if m2:
                card_dt = datetime.datetime.strptime(f"{m2.group(1)} {m2.group(2)}{m2.group(3)}{m2.group(4)}", "%Y-%m-%d %H%M%S")

        # Pattern 3: YYYYMMDD_HHMMSS anywhere
        if not card_dt:
            m3 = re.search(r"(\d{8})[-_](\d{6})", filename)
            if m3:
                card_dt = datetime.datetime.strptime(m3.group(1)+m3.group(2), "%Y%m%d%H%M%S")

        if card_dt:
            card_dt = card_dt.replace(tzinfo=self.mdt)
        else:
            # Fallback: Try to find a date string in the filename
            # e.g. 2026-04-27
            m_date = re.search(r"(\d{4}-\d{2}-\d{2})", filename)
            if m_date:
                card_dt = datetime.datetime.strptime(m_date.group(1), "%Y-%m-%d").replace(hour=12, tzinfo=self.mdt)
            else:
                log.warning(f"Could not parse date from filename: {filename}. Using current time.")
                card_dt = datetime.datetime.now(self.mdt)

        # 4. Find closest unmatched Uber drive in SQL
        # Increased tolerance to 24 hours to handle edge cases where the exact time cannot be parsed
        # and we fall back to midday. It will still pick the closest available unmatched drive.
        match = self._find_match(card_dt, tolerance_hours=24)

        uber_cut = round(card["rider_payment"] - card["driver_earnings"], 2)
        sidecar = {
            "source": "uber_card_auto",
            "filename": filename,
            "raw_text": text,
            "card_data": card,
            "matched_at": datetime.datetime.now(self.mdt).isoformat()
        }

        if not match:
            # Create a new ride if no unmatched shell was found
            ride_id = self._create_ride(card_dt, card, uber_cut, sidecar)
        else:
            ride_id = match["RideID"]
            self._update_ride(ride_id, card, uber_cut, sidecar)

        # 6. Vectorize the matched ride for Copilot semantic memory
        try:
            embedding_text = (
                f"Uber trip matched via OCR card '{filename}'. "
                f"Driver earned ${card['driver_earnings']:.2f} "
                f"(rider paid ${card['rider_payment']:.2f}, tip ${card.get('tip', 0):.2f}, "
                f"Uber cut ${uber_cut:.2f}). "
                f"Tessie ride ID: {ride_id}. "
                f"Screenshot timestamp: {card_dt.strftime('%Y-%m-%d %H:%M')} MST. "
                f"Operational vehicle: Thor (Tesla fleet)."
            )
            self.semantic.ingest_tessie_drive(
                {"RideID": ride_id, "Timestamp_Start": card_dt.isoformat(),
                 "Classification": "Uber_Matched"},
                telemetry_summary=embedding_text
            )
        except Exception as ve:
            log.warning(f"Vector embedding failed for {ride_id}: {ve}")
            
        return {
            "status": "MATCHED",
            "ride_id": ride_id,
            "driver_earnings": card["driver_earnings"],
            "rider_payment": card["rider_payment"],
            "uber_cut": uber_cut
        }

    def _parse_uber_card(self, text: str) -> Dict[str, Any]:
        """Parses Uber card text using the robust OCRClient logic."""
        parsed = self.ocr.parse_ubertrip(text)
        
        # Map OCRClient fields to UberMatcherService expectations
        return {
            "fare": parsed.get("rider_payment", 0.0),
            "driver_earnings": parsed.get("driver_total", 0.0),
            "tip": parsed.get("tip", 0.0),
            "rider_payment": parsed.get("rider_payment", 0.0)
        }

    def _find_match(self, card_dt: datetime.datetime, tolerance_hours: int = 4) -> Optional[Dict[str, Any]]:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # Search for Uber-labeled drives around that time (+/- 4 hours)
        # Only looking for ones that don't have a fare yet (to avoid double-matching)
        cursor.execute("""
            SELECT RideID, Timestamp_Start, Classification
            FROM Rides.Rides
            WHERE (Classification LIKE '%Uber%' OR Classification = 'Manual_Entry')
              AND (Classification LIKE '%DropOff%' OR Classification LIKE '%Dropoff%' OR Classification = 'Manual_Entry')
              AND (Fare IS NULL OR Fare = 0)
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
                Classification='Uber_Matched', Sidecar_Artifact_JSON=?, LastUpdated=GETUTCDATE()
            WHERE RideID = ?
        """, (
            card["rider_payment"], card.get("tip", 0.0), card["driver_earnings"], uber_cut,
            json.dumps(sidecar), ride_id
        ))
        conn.commit()
        cursor.close()

    def _create_ride(self, card_dt: datetime.datetime, card: Dict[str, Any], uber_cut: float, sidecar: Dict[str, Any]) -> str:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        ride_id = f"UBER-{int(card_dt.timestamp())}"
        cursor.execute("""
            INSERT INTO Rides.Rides 
            (RideID, TripType, Timestamp_Start, Fare, Driver_Earnings, Tip, Platform_Cut, Classification, Sidecar_Artifact_JSON, CreatedAt, LastUpdated)
            VALUES (?, 'Uber', ?, ?, ?, ?, ?, 'Uber_Matched', ?, GETUTCDATE(), GETUTCDATE())
        """, (
            ride_id, card_dt, card["rider_payment"], card["driver_earnings"], card.get("tip", 0.0), uber_cut, json.dumps(sidecar)
        ))
        conn.commit()
        cursor.close()
        return ride_id
