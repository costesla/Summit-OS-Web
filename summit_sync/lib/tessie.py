import os
import logging
import requests
from datetime import datetime

class TessieClient:
    def __init__(self):
        self.api_key = os.environ.get("TESSIE_API_KEY")
        self.base_url = "https://api.tessie.com"
        
        if not self.api_key:
            logging.warning("Tessie API key not found. Telemetry will not function.")

    def _resolve_address(self, lat, lon):
        """
        Uses OpenStreetMap (Nominatim) to reverse geocode lat/lon if Tessie doesn't provide address.
        """
        if not lat or not lon:
            return None
            
        try:
            # Simple User-Agent required by OSM
            headers = {'User-Agent': 'SummitOS/1.0'}
            url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}"
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                # Try to get street address
                addr = data.get('address', {})
                return f"{addr.get('road', 'Unknown Road')}, {addr.get('city', 'Unknown City')}"
            return None
        except:
            return None

    def get_vehicle_state(self, vin):
        """
        Fetches the current real-time state of the vehicle (battery, location, temperature, etc).
        """
        if not self.api_key:
            return None

        logging.info(f"Fetching real-time state for VIN: {vin}")
        try:
            # Tessie's state endpoint
            url = f"{self.base_url}/{vin}/state"
            headers = {"Authorization": f"Bearer {self.api_key}"}
            
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            
            return response.json()
        except Exception as e:
            logging.error(f"Error fetching vehicle state: {str(e)}")
            return None

    def get_latest_drive(self, vin):
        """
        Fetches the most recent drive for the specified VIN.
        """
        if not self.api_key:
            return None

        logging.info(f"Fetching latest drive for VIN: {vin}")
        try:
            url = f"{self.base_url}/{vin}/drives"
            headers = {"Authorization": f"Bearer {self.api_key}"}
            # Limit to 1 to get the latest
            params = {"limit": 1} 
            
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            
            data = response.json()
            if data and 'results' in data and len(data['results']) > 0:
                return data['results'][0]
            return None
            
        except Exception as e:
            logging.error(f"Error fetching Tessie data: {str(e)}")
            return None

    def get_drives(self, vin, from_ts, to_ts):
        """
        Fetches drive sessions for the specified VIN within a time range.
        """
        if not self.api_key:
            return None

        logging.info(f"Fetching drives for VIN: {vin}")
        try:
            url = f"{self.base_url}/{vin}/drives"
            headers = {"Authorization": f"Bearer {self.api_key}"}
            params = {
                "from": from_ts,
                "to": to_ts,
                "limit": 50 # Capture all stops in a day
            }
            
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            
            data = response.json()
            if data and 'results' in data:
                # Tessie returns newest first usually, but we might want to sort by start time later
                return data['results']
            return []
            
        except Exception as e:
            logging.error(f"Error fetching Tessie drives: {str(e)}")
            return []

    def match_drive_to_trip(self, vin, trip_end_timestamp, is_private=False):
        """
        Matches a trip's end timestamp (from file creation) to a Tessie drive.
        Tolerance: 20 mins for Uber, 120 mins for Private.
        """
        if not self.api_key:
            return None
            
        allowed_gap_minutes = 120 if is_private else 20
        trip_end_dt = datetime.fromtimestamp(trip_end_timestamp)

        # 1. Fetch drives for the day of the trip (plus/minus buffer)
        # We search a broad range to be safe
        ts_start = int(trip_end_timestamp - (3600 * 4)) # 4 hours before
        ts_end = int(trip_end_timestamp + (3600 * 4))   # 4 hours after
        
        try:
            url = f"{self.base_url}/{vin}/drives"
            headers = {"Authorization": f"Bearer {self.api_key}"}
            params = {
                "from": ts_start,
                "to": ts_end,
                "limit": 10 # Should be enough for a 8 hour window
            }
            
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            
            data = response.json()
            drives = data.get('results', [])
            
            logging.info(f"Searching {len(drives)} drives for match near {trip_end_dt}")

            for drive in drives:
                # Tessie ending_time is usually Unix timestamp
                drive_end_ts = drive.get('ending_time')
                if not drive_end_ts:
                    continue
                    
                diff_minutes = abs((drive_end_ts - trip_end_timestamp) / 60)
                
                if diff_minutes < allowed_gap_minutes:
                    logging.info(f"Drive Match Found! Diff: {diff_minutes:.2f} min (Window: {allowed_gap_minutes})")
                    
                    # ENHANCEMENT: Auto-resolve address if missing
                    # Tessie often omits 'starting_address' in list view, or returns 'lat/lon' only
                    start_addr = drive.get('starting_address')
                    if not start_addr or start_addr == 'Unknown':
                        s_lat = drive.get('starting_latitude')
                        s_lon = drive.get('starting_longitude')
                        resolved = self._resolve_address(s_lat, s_lon)
                        if resolved:
                            drive['starting_address'] = resolved
                            
                    end_addr = drive.get('ending_address')
                    if not end_addr or end_addr == 'Unknown':
                        e_lat = drive.get('ending_latitude')
                        e_lon = drive.get('ending_longitude')
                        resolved = self._resolve_address(e_lat, e_lon)
                        if resolved:
                            drive['ending_address'] = resolved

                    return drive
            
            logging.info("No matching drive found.")
            return None

        except Exception as e:
            logging.error(f"Error matching Tessie drive: {str(e)}")
            return None

    def get_charges(self, vin, from_ts, to_ts):
        """
        Fetches charging sessions for the specified VIN within a time range.
        """
        if not self.api_key:
            return None

        logging.info(f"Fetching charges for VIN: {vin}")
        try:
            url = f"{self.base_url}/{vin}/charges"
            headers = {"Authorization": f"Bearer {self.api_key}"}
            params = {
                "from": from_ts,
                "to": to_ts,
                "limit": 5
            }
            
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            
            data = response.json()
            if data and 'results' in data:
                return data['results']
            return []
            
        except Exception as e:
            logging.error(f"Error fetching Tessie charges: {str(e)}")
            return []

    def set_seat_heater(self, vin, seat, level):
        """
        Controls seat heaters.
        seat: 'front_left', 'front_right', 'rear_left', 'rear_right', 'rear_center'
        level: 0-3
        """
        if not self.api_key: return None
        
        logging.info(f"Setting seat heater {seat} to {level} for {vin}")
        try:
            url = f"{self.base_url}/{vin}/command/set_seat_heater"
            headers = {"Authorization": f"Bearer {self.api_key}"}
            params = {"seat": seat, "level": level}
            
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logging.error(f"Error setting seat heater: {e}")
            return None

    def control_windows(self, vin, command):
        """
        Controls windows.
        command: 'vent' or 'close'
        """
        if not self.api_key: return None
        
        logging.info(f"Window control: {command} for {vin}")
        try:
            action = "vent_windows" if command == "vent" else "close_windows"
            url = f"{self.base_url}/{vin}/command/{action}"
            headers = {"Authorization": f"Bearer {self.api_key}"}
            
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logging.error(f"Error controlling windows: {e}")
            return None
