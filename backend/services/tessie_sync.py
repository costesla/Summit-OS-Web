import logging
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional

from services.tessie import TessieClient
from services.database import DatabaseClient
from services.semantic_ingestion import SemanticIngestionService
from services.telemetry_analysis import TelemetryAnalysisService

log = logging.getLogger(__name__)

class TessieSyncService:
    def __init__(self):
        self.tessie = TessieClient()
        self.db     = DatabaseClient()
        self.semantic = SemanticIngestionService()
        self.telemetry = TelemetryAnalysisService()
        self.mdt    = timezone(timedelta(hours=-6)) # Mountain Time Support

    def sync_day(self, target_date: str = None) -> Dict[str, Any]:
        """
        Synchronizes all drives and charging sessions for a specific date (YYYY-MM-DD).
        Defaults to 'today'.
        """
        if not target_date:
            target_date = datetime.now(self.mdt).strftime('%Y-%m-%d')
        
        log.info(f"Starting Tessie Sync for {target_date}...")
        
        # 1. Fetch from Tessie
        # Note: Tessie API uses 'since' and 'until' as Unix timestamps
        # Shift the operational day from Midnight to 4:00 AM (rideshare standard)
        dt_start = datetime.strptime(target_date, '%Y-%m-%d').replace(tzinfo=self.mdt) + timedelta(hours=4)
        dt_end   = dt_start + timedelta(days=1)
        
        start_ts = int(dt_start.timestamp())
        end_ts   = int(dt_end.timestamp())
        
        vin = self.tessie.secrets.get_secret("TESSIE_VIN")
        if not vin:
            raise ValueError("TESSIE_VIN not found in environment or Key Vault")

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
                # Tessie fields: 'id', 'started_at', 'distance_miles', 'starting_location', 'tag', etc.
                drive_data = {
                    "RideID":             f"TESSIE-{drive.get('id')}",
                    "Timestamp_Start":    self._format_ts(drive.get('started_at')),
                    "Timestamp_End":      self._format_ts(drive.get('ended_at')),
                    "Distance_mi":        drive.get('distance') or drive.get('distance_miles') or drive.get('odometer_distance', 0),
                    "Duration_min":       drive.get('duration_minutes', 0),
                    "Pickup_Location":    drive.get('starting_location', 'Unknown'),
                    "Dropoff_Location":   drive.get('ending_location', 'Unknown'),
                    "Start_SOC":          drive.get('starting_battery'),
                    "End_SOC":            drive.get('ending_battery'),
                    "Energy_Used_kWh":    drive.get('energy_used'),
                    "Efficiency_Wh_mi":   drive.get('efficiency'),
                    "TripType":           "Uber" if "uber" in (drive.get('tag') or "").lower() else "Private",
                    "Classification":     self._classify_drive(drive.get('tag')),
                    "Sidecar_Artifact_JSON": json.dumps(drive)
                }
                
                # Only save to DB if it's tagged with a recognized business label (avoids "ghost" data)
                tag = (drive.get('tag') or '').lower()
                is_valid_tag = any(label in tag for label in ['uber', 'jackie', 'esmeralda'])
                
                if is_valid_tag:
                    self.db.save_trip(drive_data)
                    results["drives_saved"] += 1
                else:
                    log.info(f"Skipping drive {drive.get('id')} with tag '{drive.get('tag')}' - not a recognized business trip.")
                
                # Fetch & Analyze Telemetry
                drive_id = drive.get('id')
                d_start = drive.get('started_at')
                d_end = drive.get('ended_at')
                
                telemetry_summary = ""
                if d_start and d_end:
                    tlm = self.tessie.get_drive_telemetry(vin, d_start, d_end)
                    if tlm:
                        self.db.save_drive_telemetry(f"TESSIE-{drive_id}", tlm)
                        telemetry_summary = self.telemetry.analyze_drive(tlm)
                
                # Semantic Ingestion
                self.semantic.ingest_tessie_drive(drive, telemetry_summary=telemetry_summary)
                
            except Exception as e:
                log.error(f"Error saving drive {drive.get('id')}: {e}")
                results["errors"].append(f"Drive {drive.get('id')}: {str(e)}")

        # Save Charges
        for charge in charges:
            try:
                # Tessie fields for charges: 'starting_at', 'starting_soc', 'energy_added', 'cost', etc.
                # Map to database.py save_charge expected keys:
                # session_id, start_time, end_time, location, energy_added, cost
                charge_data = {
                    "session_id":   str(charge.get('id')),
                    "start_time":   self._format_ts(charge.get('started_at') or charge.get('starting_at')),
                    "end_time":     self._format_ts(charge.get('ended_at') or charge.get('ending_at')),
                    "energy_added": charge.get('energy_added', 0),
                    "cost":         charge.get('cost', 0),
                    "location":     charge.get('location', 'Unknown')
                }
                self.db.save_charge(charge_data)
                results["charges_saved"] += 1
            except Exception as e:
                log.error(f"Error saving charge {charge.get('id')}: {e}")
                results["errors"].append(f"Charge {charge.get('id')}: {str(e)}")

        log.info(f"Sync Complete: {results['drives_saved']} drives, {results['charges_saved']} charges.")
        return results

    def _format_ts(self, ts: int) -> Optional[str]:
        if not ts: return None
        return datetime.fromtimestamp(ts, self.mdt).strftime('%Y-%m-%d %H:%M:%S')

    def _classify_drive(self, tag: str) -> str:
        """
        Maps a Tessie tag to a SummitOS Classification value.
        These values are used by the dashboard query and the screenshot matcher.
        """
        if not tag:
            return 'Untagged'
        t = tag.lower()
        if 'uber' in t:
            return 'Uber_Dropoff'   # Required by UberMatcherService._find_match()
        if 'jackie' in t:
            return 'Jackie'
        if 'esmeralda' in t:
            return 'Esmeralda'
        return f'Private:{tag}'
