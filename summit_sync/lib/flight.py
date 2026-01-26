import os
import requests
import logging
import datetime

class AviationStackClient:
    def __init__(self):
        self.api_key = os.environ.get("AVIATIONSTACK_API_KEY")
        self.base_url = "http://api.aviationstack.com/v1/flights"

    def get_flight_status(self, flight_iata):
        # Demo Mode Fallback (matches TS logic)
        if not self.api_key:
            logging.warning("AVIATIONSTACK_API_KEY not found. Returning DEMO data.")
            now = datetime.datetime.now()
            return {
                "flight_status": "active",
                "departure": {
                    "iata": "SFO",
                    "airport": "San Francisco International",
                    "scheduled": now.isoformat()
                },
                "arrival": {
                    "iata": "DEN",
                    "airport": "Denver International",
                    "scheduled": (now + datetime.timedelta(hours=1)).isoformat(),
                    "estimated": (now + datetime.timedelta(hours=1)).isoformat()
                },
                "airline": {
                    "name": "United Airlines",
                },
                "flight": {
                    "iata": flight_iata or "UA123"
                }
            }

        # Real API Call
        params = {
            "access_key": self.api_key,
            "flight_iata": flight_iata,
            "limit": 1
        }
        
        try:
            resp = requests.get(self.base_url, params=params)
            resp.raise_for_status()
            data = resp.json()
            
            if data.get("data") and len(data["data"]) > 0:
                return data["data"][0]
            else:
                return None
                
        except Exception as e:
            logging.error(f"AviationStack Error: {e}")
            raise e
