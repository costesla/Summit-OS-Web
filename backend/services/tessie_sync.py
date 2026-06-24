import logging
import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional

from services.tessie import TessieClient
from services.database import DatabaseClient
from services.semantic_ingestion import SemanticIngestionService
from services.telemetry_analysis import TelemetryAnalysisService

from services.datetime_utils import get_timezone, get_operational_window

log = logging.getLogger(__name__)

class TessieSyncService:
    def __init__(self):
        self.tessie = TessieClient()
        self.db     = DatabaseClient()
        self.semantic = SemanticIngestionService()
        self.telemetry = TelemetryAnalysisService()
        self.mdt    = get_timezone() # DST-aware Mountain Time Support

    def sync_day(self, target_date: str = None) -> Dict[str, Any]:
        """
        Synchronizes all drives and charging sessions for a specific date (YYYY-MM-DD).
        Defaults to 'today'.
        """
        if not target_date:
            target_date = datetime.now(self.mdt).strftime('%Y-%m-%d')
        
        log.info(f"Starting Tessie Sync for {target_date}...")
        
        # 1. Fetch from Tessie
        # Note: Tessie API uses 'since' and 'until' as Unix timestamps.
        # The operational day runs from 04:00 MT on target_date to 04:00 MT the
        # next calendar day (rideshare standard).  get_operational_window() is the
        # single source of truth for this boundary — cloud_watcher.py uses the
        # same helper so both subsystems are always in sync.
        dt_start, dt_end = get_operational_window(target_date, tz=self.mdt)

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

        for drive in drives:
            try:
                # Map Tessie fields to our SQL schema
                # Tessie fields: 'id', 'started_at', 'distance_miles', 'starting_location', 'tag', etc.
                # Calculate duration in minutes from started_at and ended_at Unix timestamps
                started_at = drive.get('started_at')
                ended_at = drive.get('ended_at')
                duration_min = 0
                if started_at and ended_at:
                    duration_min = round((ended_at - started_at) / 60, 2)

                drive_data = {
                    "RideID":             f"TESSIE-{drive.get('id')}",
                    "Timestamp_Start":    self._format_ts(started_at),
                    "Timestamp_End":      self._format_ts(ended_at),
                    "Distance_mi":        drive.get('distance') or drive.get('distance_miles') or drive.get('odometer_distance', 0),
                    "Duration_min":       duration_min,
                    "Pickup_Location":    drive.get('starting_location', 'Unknown'),
                    "Dropoff_Location":   drive.get('ending_location', 'Unknown'),
                    "Start_SOC":          drive.get('starting_battery'),
                    "End_SOC":            drive.get('ending_battery'),
                    "Energy_Used_kWh":    drive.get('energy_used'),
                    "Efficiency_Wh_mi":   drive.get('efficiency'),
                    "TripType":           "Uber" if "uber" in (drive.get('tag') or "").lower() else "Private",
                    "Classification":     self._classify_drive(drive.get('tag')),
                    "Tessie_Label":       drive.get('tag'),
                    "Sidecar_Artifact_JSON": json.dumps(drive)
                }
                
                # Save all drives to DB (filtered out on dashboard if not business, but useful for matching/mileage)
                # This ensures "Untagged" drives are available for the Uber Matcher to claim them.
                self.db.save_trip(drive_data)
                results["drives_saved"] += 1
                
                # Upsert Location Intelligence if tagged
                tag = drive.get('tag')
                if tag:
                    lat = drive.get('ending_latitude')
                    lon = drive.get('ending_longitude')
                    addr = drive.get('ending_location') or drive.get('ending_address') or 'Unknown'
                    t_lower = tag.lower()
                    if 'pickup' in t_lower or 'pick up' in t_lower:
                        dtype = 'Pickup_Zone'
                    elif 'dropoff' in t_lower or 'drop off' in t_lower:
                        dtype = 'Dropoff_Zone'
                    elif 'charging session' in t_lower or 'charge session' in t_lower:
                        dtype = 'Charging'
                    else:
                        dtype = 'POI'
                    
                    if lat is not None and lon is not None:
                        self.db.upsert_location_intelligence(tag, lat, lon, addr, dtype, self._format_ts(ended_at))
                
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
                    "end_time":     self._format_ts(charge.get('finished_at') or charge.get('ended_at') or charge.get('ending_at')),
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
        t = tag.lower().strip()
        
        # 1. Contains "Pickup" -> Deadhead/Positioning
        if 'pickup' in t or 'pick up' in t:
            return 'Deadhead/Positioning'
            
        # 2. "Uber Trip N DropOff" — exact Tessie format → Uber_Dropoff (must come before
        #    the generic dropoff extraction so the trip number isn't parsed as a client name)
        if re.match(r'uber\s+trip\s+\d+', t):
            return 'Uber_Dropoff'

        # 3. Contains "Dropoff" → extract client name
        if 'dropoff' in t or 'drop off' in t:
            # Match word before dropoff
            match = re.search(r'(\w+)\s+(?:dropoff|drop\s+off)', tag, re.IGNORECASE)
            if match:
                client_word = match.group(1).lower()
                if client_word in ["jackie", "jacquelyn", "jacquelyn heslep"]:
                    return "Jacquelyn Heslep"
                elif client_word in ["david", "david berezov"]:
                    return "David Berezov"
                return client_word.capitalize()
            
        # 4. Starts with "Charging Session" -> Charging
        if t.startswith('charging session') or t.startswith('charge session'):
            return 'Charging'
            
        # 5. Starts with "Uber Trip" -> Uber_Dropoff
        if t.startswith('uber trip') or 'uber' in t:
            return 'Uber_Dropoff'
            
        # 6. Matches a known client name exactly
        try:
            known_clients = self.db.get_known_client_names()
        except Exception:
            known_clients = ["jackie", "jacquelyn", "esmeralda", "daniel", "ryan", "lauren", "terrance", "lorynne", "nancy", "adrienne", "david", "emerson"]

        search_str = t
        if "jacquelyn" in search_str:
            search_str += " jackie"
            
        for client in known_clients:
            if client == t:
                if client in ["jackie", "jacquelyn", "jacquelyn heslep"]:
                    return "Jacquelyn Heslep"
                elif client in ["david", "david berezov"]:
                    return "David Berezov"
                return client.capitalize()
                
        # 6. Any other text -> POI
        return 'POI'

    def watch_tessie_labels(self) -> Dict[str, Any]:
        """
        Watches for Tessie API tag updates within the last 48 hours.
        Updates Tessie_Label, Classification, and Location_Intelligence
        if a label has been newly set (was NULL in the database).
        Logs but preserves original if a label has changed.
        """
        log.info("Starting Tessie Label Watcher (48-hour lookback)...")
        now = datetime.now(self.mdt)
        start_dt = now - timedelta(hours=48)
        start_ts = int(start_dt.timestamp())
        end_ts = int(now.timestamp())

        vin = self.tessie.secrets.get_secret("TESSIE_VIN")
        if not vin:
            raise ValueError("TESSIE_VIN not found in environment or Key Vault")

        drives = self.tessie.get_drives(vin, from_ts=start_ts, to_ts=end_ts)
        log.info(f"Watcher retrieved {len(drives)} drives from Tessie API.")

        results = {
            "drives_evaluated": len(drives),
            "labels_set": 0,
            "labels_ignored": 0,
            "errors": []
        }

        conn = self.db.get_connection()
        if not conn:
            raise RuntimeError("Database connection failed")
        cursor = conn.cursor()

        try:
            for drive in drives:
                drive_id = f"TESSIE-{drive.get('id')}"
                tag = drive.get('tag')
                if not tag:
                    continue

                # Query database for existing label and classification
                cursor.execute("""
                    SELECT Tessie_Label, Classification 
                    FROM Rides.Rides 
                    WHERE RideID = ?
                """, (drive_id,))
                row = cursor.fetchone()

                if not row:
                    # Drive is not in database yet; let's write-once if it doesn't exist by using save_trip.
                    log.info(f"WATCHER: Drive {drive_id} not found in DB. Ingesting via save_trip.")
                    try:
                        started_at = drive.get('started_at')
                        ended_at = drive.get('ended_at')
                        duration_min = round((ended_at - started_at) / 60, 2) if started_at and ended_at else 0
                        
                        drive_data = {
                            "RideID":             drive_id,
                            "Timestamp_Start":    self._format_ts(started_at),
                            "Timestamp_End":      self._format_ts(ended_at),
                            "Distance_mi":        drive.get('distance') or drive.get('distance_miles') or drive.get('odometer_distance', 0),
                            "Duration_min":       duration_min,
                            "Pickup_Location":    drive.get('starting_location', 'Unknown'),
                            "Dropoff_Location":   drive.get('ending_location', 'Unknown'),
                            "Start_SOC":          drive.get('starting_battery'),
                            "End_SOC":            drive.get('ending_battery'),
                            "Energy_Used_kWh":    drive.get('energy_used'),
                            "Efficiency_Wh_mi":   drive.get('efficiency'),
                            "TripType":           "Uber" if "uber" in tag.lower() else "Private",
                            "Classification":     self._classify_drive(tag),
                            "Tessie_Label":       tag,
                            "Sidecar_Artifact_JSON": json.dumps(drive)
                        }
                        self.db.save_trip(drive_data)
                        results["labels_set"] += 1
                        
                        # Upsert Location Intelligence
                        lat = drive.get('ending_latitude')
                        lon = drive.get('ending_longitude')
                        addr = drive.get('ending_location') or drive.get('ending_address') or 'Unknown'
                        t_lower = tag.lower()
                        dtype = 'POI'
                        if 'pickup' in t_lower or 'pick up' in t_lower:
                            dtype = 'Pickup_Zone'
                        elif 'dropoff' in t_lower or 'drop off' in t_lower:
                            dtype = 'Dropoff_Zone'
                        elif 'charging session' in t_lower or 'charge session' in t_lower:
                            dtype = 'Charging'
                        
                        if lat is not None and lon is not None:
                            self.db.upsert_location_intelligence(tag, lat, lon, addr, dtype, self._format_ts(ended_at))
                    except Exception as ing_err:
                        log.error(f"WATCHER: Failed to ingest drive {drive_id}: {ing_err}")
                        results["errors"].append(f"Ingest {drive_id}: {str(ing_err)}")
                    continue

                existing_label, existing_class = row

                if existing_label is None:
                    # Label is newly set (was NULL in database)!
                    new_class = self._classify_drive(tag)
                    log.info(f"WATCHER: Newly set label on {drive_id}: '{tag}'. Class derived: '{new_class}'.")
                    
                    cursor.execute("""
                        UPDATE Rides.Rides
                        SET Tessie_Label = ?,
                            Classification = ?,
                            LastUpdated = GETUTCDATE()
                        WHERE RideID = ?
                    """, (tag, new_class, drive_id))
                    conn.commit()
                    results["labels_set"] += 1

                    # Upsert Location Intelligence
                    lat = drive.get('ending_latitude')
                    lon = drive.get('ending_longitude')
                    addr = drive.get('ending_location') or drive.get('ending_address') or 'Unknown'
                    t_lower = tag.lower()
                    dtype = 'POI'
                    if 'pickup' in t_lower or 'pick up' in t_lower:
                        dtype = 'Pickup_Zone'
                    elif 'dropoff' in t_lower or 'drop off' in t_lower:
                        dtype = 'Dropoff_Zone'
                    elif 'charging session' in t_lower or 'charge session' in t_lower:
                        dtype = 'Charging'
                    
                    if lat is not None and lon is not None:
                        ended_at = drive.get('ended_at')
                        self.db.upsert_location_intelligence(tag, lat, lon, addr, dtype, self._format_ts(ended_at))
                else:
                    # Label is already non-null in DB
                    if tag.strip().lower() != existing_label.strip().lower():
                        log.info(f"WATCHER: Label change detected for {drive_id} in Tessie: '{existing_label}' -> '{tag}'. Preserving original SQL label.")
                        results["labels_ignored"] += 1
        except Exception as watch_err:
            log.error(f"Error in Tessie Label Watcher: {watch_err}")
            results["errors"].append(str(watch_err))
        finally:
            cursor.close()
            conn.close()

        log.info(f"Watcher Complete: {results['labels_set']} labels set/updated, {results['labels_ignored']} changes logged and ignored.")
        return results
