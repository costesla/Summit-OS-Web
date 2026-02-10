import logging
import math
import os
import requests
from datetime import datetime
from typing import Dict, Any, Optional, List

class TripNormalizer:
    def __init__(self):
        self.gmaps_key = os.environ.get("GOOGLE_MAPS_API_KEY")

    def normalize_trip(self, trip_data: Dict[str, Any], previous_trip: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Applies accounting and EV formulas to normalize trip data.
        """
        # 1. Accounting Metrics
        rider_payment = trip_data.get('rider_payment', 0.0)
        driver_earnings = trip_data.get('driver_total', 0.0)
        
        if rider_payment > 0:
            trip_data['platform_cut_raw'] = rider_payment - driver_earnings
            trip_data['platform_cut_percent'] = (trip_data['platform_cut_raw'] / rider_payment) * 100
            trip_data['margin_percent'] = (driver_earnings / rider_payment) * 100
        else:
            trip_data['platform_cut_raw'] = 0.0
            trip_data['platform_cut_percent'] = 0.0
            trip_data['margin_percent'] = 100.0 # Private trip assumption

        # 2. EV Efficiency (Tessie Data)
        distance = trip_data.get('tessie_distance', trip_data.get('distance_miles', 0.0))
        # kWh used calculation (if available from Tessie match)
        # Note: Tessie 'drives' endpoint often provides energy_used
        energy_used = trip_data.get('energy_used', 0.0)
        
        if distance > 0:
            if energy_used > 0:
                trip_data['wh_mi'] = (energy_used * 1000) / distance
            else:
                # Estimate based on SOC delta if energy_used is missing
                start_soc = trip_data.get('start_soc_perc', 0.0)
                end_soc = trip_data.get('end_soc_perc', 0.0)
                soc_delta = start_soc - end_soc
                if soc_delta > 0:
                    # Assuming 82kWh pack for Model 3/Y Long Range
                    battery_capacity = 82.0
                    est_energy = (soc_delta / 100.0) * battery_capacity
                    trip_data['wh_mi'] = (est_energy * 1000) / distance
                    trip_data['energy_used_estimated'] = est_energy

        # 3. Elevation Analysis
        start_coords = trip_data.get('start_coords') # (lat, lon)
        end_coords = trip_data.get('end_coords')
        
        if self.gmaps_key and start_coords and end_coords:
            elevation_data = self._get_elevation_delta(start_coords, end_coords)
            if elevation_data:
                trip_data['elevation_start'] = elevation_data['start']
                trip_data['elevation_end'] = elevation_data['end']
                trip_data['elevation_delta'] = elevation_data['delta']
                trip_data['elevation_trend'] = "Ascend" if elevation_data['delta'] > 0 else "Descend"

        # 4. Idle Time
        if previous_trip:
            prev_end = previous_trip.get('end_time_epoch')
            curr_start = trip_data.get('start_time_epoch')
            if prev_end and curr_start:
                idle_seconds = curr_start - prev_end
                trip_data['idle_time_min'] = max(0, idle_seconds / 60.0)

        return trip_data

    def _get_elevation_delta(self, start: tuple, end: tuple) -> Optional[Dict[str, float]]:
        """
        Fetches elevation for start and end points using Google Maps Elevation API.
        """
        try:
            url = "https://maps.googleapis.com/maps/api/elevation/json"
            locations = f"{start[0]},{start[1]}|{end[0]},{end[1]}"
            params = {
                "locations": locations,
                "key": self.gmaps_key
            }
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('status') == 'OK' and len(data.get('results', [])) == 2:
                    elev_start = data['results'][0]['elevation']
                    elev_end = data['results'][1]['elevation']
                    # Convert meters to feet if desired, but project usually stays metric or standard
                    # SummitOS usually uses Feet for elevation in CO
                    return {
                        "start": elev_start * 3.28084,
                        "end": elev_end * 3.28084,
                        "delta": (elev_end - elev_start) * 3.28084
                    }
            return None
        except Exception as e:
            logging.error(f"Elevation API error: {e}")
            return None
