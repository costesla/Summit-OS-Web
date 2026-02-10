import os
import time
import re
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv
from lib.ocr import OCRClient
from lib.database import DatabaseClient
from lib.tessie import TessieClient
from azure.ai.vision.imageanalysis.models import VisualFeatures

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("feb6_processing_cluster.log"),
        logging.StreamHandler()
    ]
)

# Configuration
WATCH_DIR = r"C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\Pictures\Camera Roll\2026"
TARGET_DATE = "2026-02-06"
CLUSTER_THRESHOLD_SECONDS = 300 # 5 minutes

def get_file_dt(filepath):
    """Extracts timestamp from filename or falls back to creation time."""
    filename = os.path.basename(filepath)
    match = re.search(r"(\d{8})_(\d{6})", filename)
    if match:
        try:
            return datetime.strptime(f"{match.group(1)}{match.group(2)}", "%Y%m%d%H%M%S")
        except ValueError:
            pass
    return datetime.fromtimestamp(os.path.getctime(filepath))

def process_images():
    load_dotenv()
    ocr = OCRClient()
    db = DatabaseClient()
    tessie = TessieClient()
    vin = os.environ.get("TESSIE_VIN")

    logging.info(f"--- Starting Feb 6 Processing V2 (Clustering) ---")

    # 1. Cleanup Existing Data
    logging.info("Step 1: Cleaning up existing Feb 6 data...")
    cleanup_query = "DELETE FROM Trips WHERE Timestamp_Offer >= '2026-02-06 00:00:00' AND Timestamp_Offer < '2026-02-07 00:00:00'"
    try:
        conn = db.get_connection()
        if conn:
            cursor = conn.cursor()
            cursor.execute(cleanup_query)
            conn.commit()
            logging.info(f"Deleted {cursor.rowcount} existing records.")
            conn.close()
        else:
            logging.error("Failed to connect to DB for cleanup.")
            return
    except Exception as e:
        logging.error(f"Cleanup failed: {e}")
        return

    # 2. Collect and Sort Files
    logging.info("Step 2: Scanning and Sorting Files...")
    files_to_process = []
    for root, dirs, files in os.walk(WATCH_DIR):
        for file in files:
            if file.lower().endswith(('.jpg', '.jpeg', '.png')):
                full_path = os.path.join(root, file)
                dt = get_file_dt(full_path)
                
                # Filter for Feb 6 (approx 6am - 4pm based on logs)
                if dt.strftime("%Y-%m-%d") == "2026-02-06":
                     files_to_process.append({"path": full_path, "dt": dt, "filename": file})

    files_to_process.sort(key=lambda x: x["dt"])
    logging.info(f"Found {len(files_to_process)} images for {TARGET_DATE}.")

    # 3. Cluster Images
    logging.info("Step 3: Clustering Images...")
    clusters = []
    current_cluster = []
    
    for file_obj in files_to_process:
        if not current_cluster:
            current_cluster.append(file_obj)
            continue
            
        prev_file = current_cluster[-1]
        time_diff = (file_obj["dt"] - prev_file["dt"]).total_seconds()
        
        if time_diff < CLUSTER_THRESHOLD_SECONDS:
            current_cluster.append(file_obj)
        else:
            clusters.append(current_cluster)
            current_cluster = [file_obj]
            
    if current_cluster:
        clusters.append(current_cluster)
        
    logging.info(f"Created {len(clusters)} clusters/trips.")

    # 4. Process Clusters
    logging.info("Step 4: Processing Clusters...")
    
    for idx, cluster in enumerate(clusters):
        logging.info(f"--- Processing Cluster {idx+1}/{len(clusters)} ({len(cluster)} images) ---")
        
        # Determine Trip Type
        is_private = False
        if len(cluster) > 2:
            is_private = True
            
        # Scan filenames for clues
        for img in cluster:
            if "Venmo" in img['filename'] or "Wallet" in img['filename']:
                is_private = True
        
        trip_data = {
            "timestamp_epoch": cluster[0]["dt"].timestamp(),
            "source_url": f"local://{cluster[0]['filename']} (+{len(cluster)-1} others)",
            "classification": "Private_Trip" if is_private else "Uber_Core",
            "is_cdot_reportable": is_private, 
            # Defaults
            "fare": 0.0,
            "earnings_driver": 0.0,
            "distance_miles": 0.0,
            "duration_minutes": 0.0
        }
        
        # Override classification if single image is Uber Driver
        if len(cluster) == 1 and "Uber Driver" in cluster[0]['filename']:
            trip_data["classification"] = "Uber_Core"
            trip_data["is_cdot_reportable"] = False
            is_private = False

        # Aggregate Text for Private Trips
        aggregated_text = ""
        
        for img in cluster:
            logging.info(f"   OCR Scanning: {img['filename']}")
            try:
                # Read into memory
                with open(img['path'], "rb") as f:
                    file_bytes = f.read()
                
                # Direct call to client to handle bytes (avoiding extract_text_from_stream open() issue)
                raw_text = None
                if ocr.client:
                    try:
                        result = ocr.client.analyze(
                            image_data=file_bytes,
                            visual_features=[VisualFeatures.READ]
                        )
                        raw_text = ocr._parse_analysis_result(result)
                    except Exception as e:
                        logging.error(f"Azure SDK Analyze Error: {e}")
                else:
                    logging.error("OCR Client not initialized")
                    continue

                if not raw_text: continue
                
                aggregated_text += "\n" + raw_text
                
                # If Uber, parse it specifically
                if not is_private:
                    # Check suffix
                    suffix_match = re.search(r"Uber_\d{8}_\d{4}_([A-Z]{2})", img['filename'])
                    suffix = suffix_match.group(1) if suffix_match else "ST"
                    
                    parsed = ocr.parse_ubertrip(raw_text, suffix)
                    trip_data.update(parsed)
                    
                time.sleep(2) # Rate limit
                
            except Exception as e:
                logging.error(f"Error processing {img['filename']}: {e}")

        # Post-Processing for Private Trips
        if is_private:
            # Look for Fare in Aggregated Text
            # Find all currency-like patterns
            prices = re.findall(r"\$(\d{1,3}(?:,\d{3})*\.\d{2})", aggregated_text)
            clean_prices = []
            for p in prices:
                try:
                    val = float(p.replace(',', ''))
                    clean_prices.append(val)
                except: pass
            
            if clean_prices:
                # Heuristic: Fare is usually the largest amount on screen
                trip_data["fare"] = max(clean_prices)
                trip_data["earnings_driver"] = max(clean_prices)
                
            trip_data["notes"] = f"Cluster of {len(cluster)} images. " 
            if "Venmo" in aggregated_text:
                trip_data["payment_method"] = "Venmo"
                
        # Tessie Validation
        if vin:
            logging.info(f"   Validating with Tessie (Epoch: {trip_data['timestamp_epoch']})...")
            drive = tessie.match_drive_to_trip(vin, trip_data['timestamp_epoch'], is_private=is_private)
            if drive:
                logging.info(f"   Tessie Match Found: {drive.get('id')} ({drive.get('distance_miles')} mi)")
                trip_data['tessie_drive_id'] = drive.get('id')
                trip_data['tessie_distance'] = drive.get('distance_miles')
                trip_data['tessie_distance_mi'] = drive.get('distance_miles')
                trip_data['tessie_duration'] = drive.get('duration_minutes')
                trip_data['start_location'] = drive.get('starting_address')
                trip_data['end_location'] = drive.get('ending_address')
                
                # Fill missing info
                if trip_data.get('distance_miles', 0) == 0:
                    trip_data['distance_miles'] = drive.get('distance_miles')
                    trip_data['duration_minutes'] = drive.get('duration_minutes')
            else:
                logging.warning("   No Tessie match.")

        # Save Trip
        trip_data['raw_text'] = aggregated_text[:1000] # Truncate for DB
        logging.info(f"   Saving Trip: {trip_data.get('classification')} - ${trip_data.get('earnings_driver')}")
        db.save_trip(trip_data)

    logging.info("--- Processing Complete ---")

if __name__ == "__main__":
    process_images()
