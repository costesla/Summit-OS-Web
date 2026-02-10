import shutil
import os
import time
import logging
import threading
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from dotenv import load_dotenv

# Import the trip processor
from process_trips_v2 import process_trips

# Load environment variables
load_dotenv()

# --- Configuration ---
# Hardcoded local path as requested
WATCH_DIR = r"C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\Pictures\Camera Roll\2026"
SHAREPOINT_ARCHIVE_PATH = os.environ.get("SHAREPOINT_ARCHIVE_PATH")

# Logging Setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

class Debouncer:
    def __init__(self, interval=5.0, action=None):
        self.interval = interval
        self.action = action
        self.timer = None

    def trigger(self):
        if self.timer:
            self.timer.cancel()
        self.timer = threading.Timer(self.interval, self.action)
        self.timer.start()

class ImageHandler(FileSystemEventHandler):
    def __init__(self):
        self.debouncer = Debouncer(interval=10.0, action=self.run_processing)
        self.processing_lock = threading.Lock()

    def on_created(self, event):
        if event.is_directory:
            return
        
        filename = event.src_path
        if not filename.lower().endswith(('.jpg', '.jpeg', '.png')):
            return

        logging.info(f"Detected new file: {filename}")
        self.debouncer.trigger()

    def run_processing(self):
        with self.processing_lock:
            logging.info("Debounce timer expired. Starting trip processing...")
            try:
                # Run for today's date
                today_str = datetime.now().strftime("%Y-%m-%d")
                process_trips(target_date=today_str)
                logging.info("Trip processing complete.")
            except Exception as e:
                logging.error(f"Error during trip processing: {e}")

if __name__ == "__main__":
    if not os.path.exists(WATCH_DIR):
        logging.error(f"Watch directory does not exist: {WATCH_DIR}")
        exit(1)

    logging.info(f"Starting Summit Sync Watcher...")
    logging.info(f"Watching: {WATCH_DIR}")

    event_handler = ImageHandler()
    
    # --- Charging Session Monitor (Background Thread) ---
    def poll_charging_sessions():
        logging.info("Starting background charging monitor (30 min interval)...")
        # Late imports to avoid circular issues
        from lib.tessie import TessieClient
        from lib.database import DatabaseClient
        
        tessie = TessieClient()
        db = DatabaseClient()
        vin = os.environ.get("TESSIE_VIN")

        while True:
            try:
                if vin:
                    now = datetime.now()
                    today_start = datetime(now.year, now.month, now.day)
                    ts_start = int(today_start.timestamp())
                    ts_end = int(now.timestamp())
                    
                    charges = tessie.get_charges(vin, ts_start, ts_end)
                    if charges:
                        if len(charges) > 1:
                            logging.warning(f"!!! ALERT: {len(charges)} CHARGING SESSIONS DETECTED TODAY !!!")
                        
                        for charge in charges:
                            session_id = str(charge.get('id', ''))
                            if not session_id: continue
                            
                            charge_data = {
                                "session_id": session_id,
                                "start_time": datetime.fromtimestamp(charge.get('started_at')) if charge.get('started_at') else None,
                                "end_time": datetime.fromtimestamp(charge.get('finished_at')) if charge.get('finished_at') else None,
                                "location": charge.get('location', 'Unknown'),
                                "start_soc": charge.get('starting_battery'),
                                "end_soc": charge.get('ending_battery'),
                                "energy_added": charge.get('charge_energy_added'),
                                "cost": charge.get('cost', 0.0),
                                "duration": charge.get('duration_minutes', 0.0)
                            }
                            db.save_charge(charge_data)
                else:
                    logging.info("Background Check: No new charging sessions.")
            except Exception as e:
                logging.error(f"Error in background charging monitor: {e}")
            
            time.sleep(1800) # Check every 30 minutes

    charging_thread = threading.Thread(target=poll_charging_sessions, daemon=True)
    charging_thread.start()

    observer = Observer()
    observer.schedule(event_handler, WATCH_DIR, recursive=True)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
