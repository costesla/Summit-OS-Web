import logging
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional

from .tessie import TessieClient
from .database import DatabaseClient
from .semantic_ingestion import SemanticIngestionService

log = logging.getLogger(__name__)

class TessieSyncService:
    def __init__(self):
        self.tessie = TessieClient()
        self.db     = DatabaseClient()
        self.semantic = SemanticIngestionService()
        self.mdt    = timezone(timedelta(hours=-6)) # Mountain Time Support

    def sync_day(self, target_date: str = None) -> Dict[str, Any]:
        """
        Synchronizes all drives and charging sessions for a specific date (YYYY-MM-DD).
        Defaults to 'yesterday'.
        """
        if not target_date:
            target_date = (datetime.now(self.mdt) - timedelta(days=1)).strftime('%Y-%m-%d')
        
        log.info(f"Starting Tessie Sync for {target_date}...")
        
        # 1. Fetch from Tessie
        # Note: Tessie API uses 'since' and 'until' as Unix timestamps
        dt_start = datetime.strptime(target_date, '%Y-%m-%d').replace(tzinfo=self.mdt)
        dt_end   = dt_start + timedelta(days=1)
        
        start_ts = int(dt_start.timestamp())
        end_ts   = int(dt_end.timestamp())
        vin = os.environ.get("TESSIE_VIN")
        if not vin:
            raise ValueError("TESSIE_VIN environment variable not set")

        # Fetch Drives
        drives = self.tessie.get_drives(vin, from_ts=start_ts, to_ts=end_ts)
        # Fetch Charges
        charges = self.tessie.get_charges(vin, from_ts=start_ts, to_ts=end_ts)

        # 2. Process & Save
        results = {
            "date": target_date,
            "drives_found": len(drives),
            "charges_found": len(charges),
            "drives_saved": 0,
            "charges_saved": 0,
            "errors": []
        }

        # Save Drives
        for drive in drives:
            try:
                # Map Tessie fields to our SQL schema
                # Tessie fields: 'uid', 'started_at', 'distance_miles', 'starting_location', 'tag', etc.
                drive_data = {
                    "RideID":             f"TESSIE-{drive.get('uid')}",
                    "Timestamp_Start":    self._format_ts(drive.get('started_at')),
                    "Timestamp_End":      self._format_ts(drive.get('ended_at')),
                    "Distance_mi":        drive.get('distance_miles', 0),
                    "Duration_min":       drive.get('duration_minutes', 0),
                    "Pickup_Location":    drive.get('starting_location', 'Unknown'),
                    "Dropoff_Location":   drive.get('ending_location', 'Unknown'),
                    "Classification":     f"Auto:{drive.get('tag', 'None')}",
                    "Odometer_Distance":  drive.get('odometer_distance', 0),
                    "TripType":           "Uber" if "Uber" in (drive.get('tag') or "") else "Private",
                    "Sidecar_Artifact_JSON": json.dumps(drive)
                }
                self.db.save_trip(drive_data)
                
                # Semantic Ingestion
                self.semantic.ingest_tessie_drive(drive)
                
                results["drives_saved"] += 1
            except Exception as e:
                log.error(f"Error saving drive {drive.get('uid')}: {e}")
                results["errors"].append(f"Drive {drive.get('uid')}: {str(e)}")

        # Save Charges
        for charge in charges:
            try:
                # Tessie fields for charges: 'starting_at', 'starting_soc', 'energy_added', 'cost', etc.
                # Our schema: Energy_Added_kWh, Cost, Charger_Type, Starting_SoC, Ending_SoC, Odometer
                charge_data = {
                    "ChargeID":             f"CHG-{charge.get('uid')}",
                    "Timestamp_Start":      self._format_ts(charge.get('starting_at')),
                    "Timestamp_End":        self._format_ts(charge.get('ending_at')),
                    "Energy_Added_kWh":     charge.get('energy_added', 0),
                    "Cost":                 charge.get('cost', 0),
                    "Charger_Type":         charge.get('charger_type', 'Unknown'),
                    "Starting_SoC":         charge.get('starting_soc', 0),
                    "Ending_SoC":           charge.get('ending_soc', 0),
                    "Odometer":             charge.get('odometer', 0),
                    "Location":             charge.get('location', 'Unknown'),
                    "Source":               "Tessie",
                    "Sidecar_Artifact_JSON": json.dumps(charge)
                }
                # Assuming DatabaseClient has or should have a save_charge method
                # If not, we'll use a direct query or add it.
                self._save_charge(charge_data)
                results["charges_saved"] += 1
            except Exception as e:
                log.error(f"Error saving charge {charge.get('uid')}: {e}")
                results["errors"].append(f"Charge {charge.get('uid')}: {str(e)}")

        log.info(f"Sync Complete: {results['drives_saved']} drives, {results['charges_saved']} charges.")
        return results

    def _format_ts(self, ts: int) -> Optional[str]:
        if not ts: return None
        # Convert Tessie Unix timestamp to ISO string for SQL
        return datetime.fromtimestamp(ts, self.mdt).strftime('%Y-%m-%d %H:%M:%S')

    def _save_charge(self, data: Dict[str, Any]):
        """Direct SQL upsert for charging sessions."""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            MERGE INTO Rides.ChargingSessions AS target
            USING (SELECT ? AS ChargeID) AS source
            ON target.ChargeID = source.ChargeID
            WHEN MATCHED THEN
                UPDATE SET Timestamp_Start=?, Timestamp_End=?, Energy_Added_kWh=?, Cost=?, 
                           Charger_Type=?, Starting_SoC=?, Ending_SoC=?, Odometer=?, Location=?, Sidecar_Artifact_JSON=?, LastUpdated=GETDATE()
            WHEN NOT MATCHED THEN
                INSERT (ChargeID, Timestamp_Start, Timestamp_End, Energy_Added_kWh, Cost, 
                        Charger_Type, Starting_SoC, Ending_SoC, Odometer, Location, Sidecar_Artifact_JSON)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            data["ChargeID"],
            data["Timestamp_Start"], data["Timestamp_End"], data["Energy_Added_kWh"], data["Cost"],
            data["Charger_Type"], data["Starting_SoC"], data["Ending_SoC"], data["Odometer"], data["Location"], data["Sidecar_Artifact_JSON"],
            data["ChargeID"], data["Timestamp_Start"], data["Timestamp_End"], data["Energy_Added_kWh"], data["Cost"],
            data["Charger_Type"], data["Starting_SoC"], data["Ending_SoC"], data["Odometer"], data["Location"], data["Sidecar_Artifact_JSON"]
        ))
        conn.commit()
        cursor.close()
