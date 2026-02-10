import os
import time
import shutil
import logging
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# --- Configuration ---
SOURCE_DIR = os.environ.get("PERSONAL_ONEDRIVE_PATH", r"C:\Users\PeterTeehan\OneDrive\Pictures\Camera Roll")
DEST_DIR = os.environ.get("BUSINESS_ONEDRIVE_PATH", r"C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\Pictures\Camera Roll\2026")
ALLOWED_EXTENSIONS = ('.jpg', '.jpeg', '.png')

# Logging Setup
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bridge.log"),
        logging.StreamHandler()
    ]
)

class BridgeHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return
        self.process_file(event.src_path)

    def process_file(self, file_path):
        if not file_path.lower().endswith(ALLOWED_EXTENSIONS):
            return

        # Give the OS a moment to finish writing the file
        time.sleep(2)

        try:
            filename = os.path.basename(file_path)
            dest_path = os.path.join(DEST_DIR, filename)

            if not os.path.exists(dest_path):
                logging.info(f"New file detected: {filename}. Copying to business account...")
                shutil.copy2(file_path, dest_path)
                logging.info(f"Successfully bridged: {filename}")
            else:
                logging.debug(f"File already exists in destination: {filename}")
        except Exception as e:
            logging.error(f"Failed to bridge {file_path}: {e}")

def initial_sync(target_date="20260201"):
    """
    Scans the source directory for files matching a specific date and copies them if missing.
    """
    logging.info(f"Starting initial scan for files containing '{target_date}'...")
    if not os.path.exists(SOURCE_DIR):
        logging.error(f"Source directory not found: {SOURCE_DIR}")
        return

    if not os.path.exists(DEST_DIR):
        os.makedirs(DEST_DIR, exist_ok=True)
        logging.info(f"Created destination directory: {DEST_DIR}")

    count = 0
    for root, _, files in os.walk(SOURCE_DIR):
        for file in files:
            if target_date in file and file.lower().endswith(ALLOWED_EXTENSIONS):
                source_path = os.path.join(root, file)
                dest_path = os.path.join(DEST_DIR, file)

                if not os.path.exists(dest_path):
                    try:
                        shutil.copy2(source_path, dest_path)
                        logging.info(f"Synced existing file: {file}")
                        count += 1
                    except Exception as e:
                        logging.error(f"Error syncing {file}: {e}")
    
    logging.info(f"Initial sync complete. Copied {count} files.")

if __name__ == "__main__":
    import sys
    
    # Simple argument parsing
    run_watcher = "--initial-only" not in sys.argv
    target_date = "20260201" # Default
    
    # Check for custom date
    for arg in sys.argv:
        if arg.startswith("--date="):
            target_date = arg.split("=")[1]

    logging.info("=== OneDrive Personal-to-Business Bridge Starting ===")
    logging.info(f"Source: {SOURCE_DIR}")
    logging.info(f"Destination: {DEST_DIR}")

    # Run initial sync
    initial_sync(target_date)

    if run_watcher:
        # Start watching for new files
        event_handler = BridgeHandler()
        observer = Observer()
        observer.schedule(event_handler, SOURCE_DIR, recursive=True)
        observer.start()

        logging.info("Watcher started. Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()
    else:
        logging.info("Initial sync complete. --initial-only specified, exiting.")
