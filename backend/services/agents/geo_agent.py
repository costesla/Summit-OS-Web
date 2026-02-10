import logging
import os
import requests
from typing import Dict, Any, Optional

class GeoAgent:
    def __init__(self):
        self.gmaps_key = os.environ.get("GOOGLE_MAPS_API_KEY")

    def process(self, trip_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Resolves geospatial context and elevation.
        """
        logging.info("GeoAgent: Computing elevation...")
        
        start_coords = trip_data.get('start_coords')
        end_coords = trip_data.get('end_coords')
        
        results = {}
        if self.gmaps_key and start_coords and end_coords:
            elevation_data = self._get_elevation_delta(start_coords, end_coords)
            if elevation_data:
                results['elevation_start'] = elevation_data['start']
                results['elevation_end'] = elevation_data['end']
                results['elevation_delta'] = elevation_data['delta']
                results['elevation_trend'] = "Ascend" if elevation_data['delta'] > 0 else "Descend"

        return results

    def _get_elevation_delta(self, start: tuple, end: tuple) -> Optional[Dict[str, float]]:
        try:
            url = "https://maps.googleapis.com/maps/api/elevation/json"
            locations = f"{start[0]},{start[1]}|{end[0]},{end[1]}"
            params = {"locations": locations, "key": self.gmaps_key}
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('status') == 'OK' and len(data.get('results', [])) == 2:
                    s = data['results'][0]['elevation'] * 3.28084
                    e = data['results'][1]['elevation'] * 3.28084
                    return {"start": s, "end": e, "delta": e - s}
            return None
        except Exception as e:
            logging.error(f"GeoAgent API error: {e}")
            return None
