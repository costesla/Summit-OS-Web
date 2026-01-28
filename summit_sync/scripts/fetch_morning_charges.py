
import os
import sys
import logging
import time
from dotenv import load_dotenv
from datetime import datetime, timedelta

# Add parent dir to path to import lib
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.tessie import TessieClient
from lib.database import DatabaseClient

# Setup
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def pull_and_save_charges():
    vin = os.environ.get("TESSIE_VIN")
    if not vin:
        logging.error("TESSIE_VIN not found in .env")
        return

    tessie = TessieClient()
    db = DatabaseClient()
    
    # Calculate start of today in local time (UTC-7)
    # Get current time in UTC, then adjust to local, then truncate to 00:00:00
    now = datetime.now()
    today_start = datetime(now.year, now.month, now.day)
    ts_start = int(today_start.timestamp())
    ts_end = int(now.timestamp())
    
    logging.info(f"Checking charges for today (since {today_start}) for VIN: {vin}")
    charges = tessie.get_charges(vin, ts_start, ts_end)
    
    if charges:
        num_sessions = len(charges)
        logging.info(f"Found {num_sessions} charging sessions today.")
        
        if num_sessions > 1:
            logging.warning(f"!!! ALERT: MULTIPLE CHARGING SESSIONS DETECTED ({num_sessions}) !!!")
            logging.warning("Please monitor energy usage and state of health.")

        for charge in charges:
            session_id = str(charge.get('id', ''))
            if not session_id:
                continue

            # Map to database fields
            start_time = datetime.fromtimestamp(charge.get('started_at')) if charge.get('started_at') else None
            end_time = datetime.fromtimestamp(charge.get('finished_at')) if charge.get('finished_at') else None
            
            charge_data = {
                "session_id": session_id,
                "start_time": start_time,
                "end_time": end_time,
                "location": charge.get('location', 'Unknown'),
                "start_soc": charge.get('starting_battery'),
                "end_soc": charge.get('ending_battery'),
                "energy_added": charge.get('charge_energy_added'),
                "cost": charge.get('cost', 0.0),
                "duration": charge.get('duration_minutes', 0.0)
            }
            
            logging.info(f"Processing session {session_id} - {charge_data['location']} | {charge_data['energy_added']} kWh")
            
            # Use standardized DatabaseClient logic
            db.save_charge(charge_data)
    else:
        logging.info("No charging sessions found for today.")

if __name__ == "__main__":
    pull_and_save_charges()
