import os
import time
import logging
import re
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
from lib.ocr import OCRClient
from lib.database import DatabaseClient
from lib.tessie import TessieClient

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("process_trips_v2.log"),
        logging.StreamHandler()
    ]
)


# Configuration
WATCH_DIR = r"C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\Pictures\Camera Roll\2026"
TARGET_DATE = "2026-02-06" # Default, can be made dynamic later

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

# Client Configuration
CLIENT_CONFIG = {
    "Jackie": {
        "name": "Jackie",
        "venmo_sender": "Jacquelyn", # Matches "@Jacquelyn-Heslep"
        "is_bundle": True,
        "rate_flat": 100.00 # Fallback or sanity check? Not needed if we parse Venmo.
    },
    "Esmeralda": {
        "name": "Esmeralda",
        "venmo_sender": "Esmeralda", 
        "is_bundle": False
    }
}

def process_trips(target_date=None):
    load_dotenv()
    ocr = OCRClient()
    db = DatabaseClient()
    tessie = TessieClient()
    vin = os.environ.get("TESSIE_VIN")

    if not vin:
        logging.error("TESSIE_VIN not found in environment.")
        return

    # Use provided date or default to today
    if target_date is None:
        target_date = datetime.now().strftime("%Y-%m-%d")

    logging.info(f"--- Starting Trip Processing V2 (Tessie Anchor) for {target_date} ---")

    # 1. Fetch Drives
    start_dt = datetime.strptime(f"{target_date} 00:00:00", "%Y-%m-%d %H:%M:%S")
    end_dt = datetime.strptime(f"{target_date} 23:59:59", "%Y-%m-%d %H:%M:%S")

    logging.info(f"Fetching Tessie drives for {target_date}...")
    try:
        drives = tessie.get_drives(vin, int(start_dt.timestamp()), int(end_dt.timestamp()))
    except Exception as e:
        logging.error(f"Failed to fetch drives: {e}")
        return

    logging.info(f"Found {len(drives)} drives.")
    if not drives:
        logging.info("No drives found. Exiting.")
        return

    # Sort by start time
    drives.sort(key=lambda x: x.get('started_at', 0))

    # Identify "Last Drive" for Bundle Clients
    last_drive_indices = {}
    for i, drive in enumerate(drives):
        tag = drive.get('tag')
        if tag:
            # Check if tag matches a client (case-insensitive?)
            # Tessie tags might be "Jackie" or "Work, Jackie"
            for client_key, config in CLIENT_CONFIG.items():
                if client_key.lower() in tag.lower():
                    last_drive_indices[client_key] = i

    # 2. Index Local Images
    logging.info("Indexing local images...")
    images = []
    for f in os.listdir(WATCH_DIR):
        if f.lower().endswith(('.jpg', '.jpeg', '.png')):
            full_path = os.path.join(WATCH_DIR, f)
            dt = get_file_dt(full_path)
            # Filter loosely for the target date to avoid scanning thousands of files
            # Allow items from next day early morning if trip went over midnight
            img_date = dt.strftime("%Y-%m-%d")
            
            if img_date == target_date or img_date == (start_dt + timedelta(days=1)).strftime("%Y-%m-%d"):
                images.append({"filename": f, "dt": dt, "path": full_path})
    
    # Sort images by time
    images.sort(key=lambda x: x['dt'])
    logging.info(f"Found {len(images)} potential images.")
    if len(images) > 0:
        logging.info(f"Sample Image: {images[0]['filename']} @ {images[0]['dt']}")
        logging.info(f"Sample Image (Last): {images[-1]['filename']} @ {images[-1]['dt']}")

    # 4. Process Each Drive
    for i, drive in enumerate(drives):
        conn = db.get_connection() # Check DB connectivity
        if not conn:
            logging.error("DB Connection failed. Aborting.")
            return
        conn.close()

        drive_id = drive.get('id')
        start_ts = drive.get('started_at')
        end_ts = drive.get('ended_at')
        drive_tag = drive.get('tag')
        
        if not start_ts or not end_ts:
            logging.warning(f"Skipping Drive {drive_id} - Missing timestamps")
            continue

        drive_start = datetime.fromtimestamp(start_ts)
        drive_end = datetime.fromtimestamp(end_ts)
        
        logging.info(f"\n[Drive #{i+1}] ID: {drive_id} | {drive_tag} | {drive_start.strftime('%H:%M')} - {drive_end.strftime('%H:%M')}")

        # Determine Client Context
        client_config = None
        if drive_tag:
            for key, config in CLIENT_CONFIG.items():
                if key.lower() in drive_tag.lower():
                    client_config = config
                    break

        matched_images = []
        
        # Window: Start - 20 mins to End + 30 mins
        window_start = drive_start - timedelta(minutes=20)
        window_end = drive_end + timedelta(minutes=30)
        
        candidates = [img for img in images if window_start <= img['dt'] <= window_end]
        logging.info(f"   Candidates for Drive {drive_id} (Window {window_start.strftime('%H:%M')} - {window_end.strftime('%H:%M')}): {len(candidates)}")
        
        for img in candidates:
            # Check if this drive is the *best* match for this image among ALL drives in the batch.
            best_drive = None
            min_diff = float('inf')
            
            for d in drives:
                d_end_ts = d.get('ended_at')
                d_start_ts = d.get('started_at')
                
                if not d_end_ts or not d_start_ts: continue

                d_end = datetime.fromtimestamp(d_end_ts)
                diff = abs((img['dt'] - d_end).total_seconds())
                
                # Check if d is even a candidate (start-20 to end+30)
                d_start = datetime.fromtimestamp(d_start_ts)
                d_win_start = d_start - timedelta(minutes=20)
                d_win_end = d_end + timedelta(minutes=30)
                
                if d_win_start <= img['dt'] <= d_win_end:
                    if diff < min_diff:
                        min_diff = diff
                        best_drive = d

            # If the best drive is THIS drive, claim it.
            if best_drive and str(best_drive.get('id')) == str(drive_id):
                matched_images.append(img)
                logging.info(f"   Matched {img['filename']} to Drive {drive_id} (Diff: {min_diff:.1f}s)")
        
        logging.info(f"   Matched {len(matched_images)} images (deduplicated).")

        # Default Trip Data
        trip_data = {
            "trip_id": str(drive_id),
            "tessie_drive_id": str(drive_id),
            "timestamp_epoch": start_ts,
            "timestamp_pickup_epoch": start_ts,
            "timestamp_dropoff_epoch": end_ts,
            "tessie_distance": drive.get('distance', drive.get('odometer_distance', 0)),
            "tessie_distance_mi": drive.get('distance', drive.get('odometer_distance', 0)),
            "tessie_duration": (end_ts - start_ts) / 60,
            "distance_miles": drive.get('distance', drive.get('odometer_distance', 0)),
            "duration_minutes": (end_ts - start_ts) / 60,
            "start_location": drive.get('starting_location', drive.get('starting_address', 'Unknown')),
            "end_location": drive.get('ending_location', drive.get('ending_address', 'Unknown')),
            "classification": "Uber_Core",
            "is_cdot_reportable": False,
            "fare": 0.0,
            "earnings_driver": 0.0,
            "source_url": f"tessie_drive_{drive_id}",
            "raw_text": "",
            "start_soc": drive.get('starting_battery'),
            "end_soc": drive.get('ending_battery'),
            "energy_used": drive.get('energy_used'),
            "efficiency_wh_mi": None
        }
        
        # Calculate efficiency if we have the data
        distance = trip_data.get('distance_miles', 0)
        energy = trip_data.get('energy_used')
        if distance and distance > 0 and energy:
            trip_data['efficiency_wh_mi'] = (energy * 1000) / distance

        # Apply Client Logic
        if client_config:
            trip_data["classification"] = "Private_Trip"
            trip_data["passenger_firstname"] = client_config["name"]
            trip_data["is_cdot_reportable"] = True
            logging.info(f"   Identified Client: {client_config['name']}")
            logging.info("Saving Private Trip: " + str(drive_id))

        # OCR Scanning
        matched_images.sort(key=lambda x: x['dt'], reverse=True)
        found_financials = False
        aggregated_text = ""
        
        scan_count = 0
        for img in matched_images:
            if scan_count >= 5 and found_financials: break
            if scan_count >= 5: break

            logging.info(f"   OCR Scanning: {img['filename']}")
            try:
                with open(img['path'], "rb") as f:
                    file_bytes = f.read()
                
                if ocr.client:
                    result = ocr.client.analyze(image_data=file_bytes, visual_features=['read'])
                    text = ocr._parse_analysis_result(result)
                    time.sleep(3) # Rate limit protection
                else:
                    text = ""
            except Exception as e:
                logging.error(f"OCR Failed for {img['filename']}: {e}")
                text = ""
            
            if not text: continue
            
            aggregated_text += f"\n--- {img['filename']} ---\n{text}"
            scan_count += 1
            
            # 1. Check for Uber Financials
            
            # A. Try Detailed Parse (New Format)
            detailed = ocr.parse_uber_detailed(text)
            if detailed.get("is_detailed") and detailed.get("driver_earnings", 0) > 0:
                 logging.info(f"   Found Detailed Uber Data: ${detailed.get('driver_earnings')}")
                 found_financials = True
                 
                 trip_data.update({
                     "classification": "Uber_Core",
                     "earnings_driver": detailed.get("driver_earnings", 0),
                     "fare": detailed.get("rider_payment", 0),
                     "tip": detailed.get("tip", 0),
                     "uber_cut": detailed.get("uber_service_fee", 0),
                     "uber_distance_mi": detailed.get("distance_miles", 0),
                     "uber_duration_min": detailed.get("duration_minutes", 0)
                 })
                 
                 # Fee Calculation
                 if detailed.get("insurance_fees", 0) > 0:
                     trip_data["insurance_fees"] = detailed.get("insurance_fees")
                 else:
                     # Fallback
                     rem = trip_data["fare"] - trip_data["earnings_driver"] - trip_data["uber_cut"] - trip_data["tip"]
                     if rem > 0: trip_data["insurance_fees"] = rem

            # B. Fallback to Basic Parse (Old Format)
            if not found_financials:
                parsed = ocr.parse_ubertrip(text)
                if parsed.get("driver_total", 0) > 0 or parsed.get("rider_payment", 0) > 0:
                    logging.info(f"   Found Basic Uber Financials: ${parsed.get('driver_total')}")
                    found_financials = True
                    trip_data.update({
                        "classification": "Uber_Core",
                        "fare": parsed.get("rider_payment", 0),
                        "earnings_driver": parsed.get("driver_total", 0),
                        "tip": parsed.get("tip", 0),
                        "uber_cut": parsed.get("uber_cut", 0),
                        "insurance_fees": parsed.get("insurance_fees", 0),
                        "uber_distance_mi": parsed.get("distance_miles", 0),
                        "uber_duration_min": parsed.get("duration_minutes", 0)
                    })
            
            # Comparison Logic (Uber vs Tessie)
            if found_financials:
                 actual_dist = trip_data.get('tessie_distance_mi', 0)
                 actual_dur = trip_data.get('tessie_duration', 0)
                 paid_dist = trip_data.get('uber_distance_mi', 0)
                 paid_dur = trip_data.get('uber_duration_min', 0)
                 
                 if actual_dist is None: actual_dist = 0
                 if paid_dist is None: paid_dist = 0
                 
                 discrepancy_dist = actual_dist - paid_dist
                 
                 metrics = {
                     "comparison": {
                         "actual_miles": actual_dist,
                         "paid_miles": paid_dist,
                         "diff_miles": round(discrepancy_dist, 2),
                         "actual_minutes": round(actual_dur, 1),
                         "paid_minutes": paid_dur,
                         "platform_cut_percent": round((trip_data['fare'] - trip_data['earnings_driver']) / trip_data['fare'] * 100, 1) if trip_data['fare'] > 0 else 0
                     }
                 }
                 trip_data['sidecar_json'] = json.dumps(metrics)
                 
                 if discrepancy_dist > 0.5:
                     logging.warning(f"   [Audit Alert] Unpaid Miles: {discrepancy_dist:.2f} mi")
            
            # 2. Check for Venmo (Private Trip)
            venmo_data = ocr.parse_venmo(text)
            if venmo_data.get("amount") > 0:
                sender = venmo_data.get("sender", "")
                
                is_match = False
                if client_config:
                    if client_config['venmo_sender'].lower() in sender.lower():
                        is_match = True
                else:
                    is_match = True

                if is_match:
                    logging.info(f"   Found Venmo Payment from {sender}: ${venmo_data.get('amount')}")
                    trip_data["earnings_driver"] = venmo_data.get("amount")
                    trip_data["classification"] = "Private_Trip"
                    trip_data["payment_method"] = "Venmo"
                    found_financials = True
                    
                    if client_config and client_config['is_bundle']:
                        bundle_revenue[client_config['name']] = venmo_data.get("amount")


        trip_data["raw_text"] = aggregated_text[:2000]

        # Bundle Logic: Late Assignment
        if client_config and client_config['is_bundle']:
            is_last_drive = (last_drive_indices.get(client_config['name']) == i)
            
            if is_last_drive and trip_data["earnings_driver"] == 0:
                logging.info(f"   [Bundle] Last trip for {client_config['name']} - Scanning for late payment...")
                late_window_start = drive_end
                late_window_end = datetime.strptime(f"{target_date} 23:59:59", "%Y-%m-%d %H:%M:%S")
                
                late_images = [img for img in images if late_window_start <= img['dt'] <= late_window_end]
                
                for img in late_images:
                    logging.info(f"   [Bundle] Scanning late image: {img['filename']}")
                    try:
                        with open(img['path'], "rb") as f:
                            file_bytes = f.read()
                        if ocr.client:
                            result = ocr.client.analyze(image_data=file_bytes, visual_features=['read'])
                            text = ocr._parse_analysis_result(result)
                            time.sleep(3)
                            
                            v_data = ocr.parse_venmo(text)
                            if v_data.get("amount") > 0 and client_config['venmo_sender'].lower() in v_data.get("sender", "").lower():
                                logging.info(f"   [Bundle] Found Late Venmo: ${v_data.get('amount')}")
                                trip_data["earnings_driver"] = v_data.get("amount")
                                trip_data["payment_method"] = "Venmo (Bundle)"
                                break
                    except Exception: pass

        
        # 7. Final Classification Logic
        if not found_financials and trip_data["classification"] == "Uber_Core":
             if trip_data["distance_miles"] < 0.5:
                 trip_data["classification"] = "Personal_Movement"
             else:
                 trip_data["classification"] = "Uber_Unknown_Financials"

        trip_data['source_url'] = f"tessie:{drive_id} + {len(matched_images)} imgs"

        # 8. Save to DB
        logging.info(f"   Saving Trip {drive_id}: {trip_data['classification']} | Dist: {trip_data['distance_miles']} mi | Earn: ${trip_data['earnings_driver']}")
        try:
            db.save_trip(trip_data)
        except Exception as e:
            logging.error(f"Failed to save trip: {e}")


    # 9. Post-Process Bundle Payments (Venmo)
    logging.info("\n--- Processing Bundle Payments (Venmo) ---")
    
    for client_key, config in CLIENT_CONFIG.items():
        if not config.get("is_bundle"):
            continue
            
        # Find all drives tagged with this client
        client_drives = [d for d in drives if d.get('tag') and client_key.lower() in d.get('tag').lower()]
        
        if not client_drives:
            continue
            
        logging.info(f"Found {len(client_drives)} drives for {client_key}")
        
        # Scan images for Venmo payments from this client
        venmo_sender = config.get("venmo_sender", "")
        total_payment = 0.0
        venmo_screenshots = []
        
        for img in images:
            filename = img['filename'].lower()
            if 'venmo' in filename:
                try:
                    text = ocr.extract_text_from_stream(img['path'])
                    venmo_data = ocr.parse_venmo(text)
                    
                    sender = venmo_data.get('sender', '')
                    amount = venmo_data.get('amount', 0.0)
                    
                    if venmo_sender.lower() in sender.lower() and amount > 0:
                        # Check if we've already counted this payment (duplicate screenshot)
                        if not any(v['amount'] == amount and v['sender'] == sender for v in venmo_screenshots):
                            total_payment += amount
                            venmo_screenshots.append(venmo_data)
                            logging.info(f"   Found Venmo payment: ${amount} from {sender}")
                except Exception as e:
                    logging.error(f"Error parsing Venmo screenshot {img['filename']}: {e}")
        
        if total_payment > 0 and len(client_drives) > 0:
            num_trips = len(client_drives)
            
            # Calculate per-trip amounts
            total_tip = 10.00  # Fixed tip amount
            total_fare = total_payment - total_tip
            fare_per_trip = total_fare / num_trips
            tip_per_trip = total_tip / num_trips
            
            logging.info(f"Allocating ${total_payment:.2f} across {num_trips} trips:")
            logging.info(f"  Fare per trip: ${fare_per_trip:.2f}")
            logging.info(f"  Tip per trip: ${tip_per_trip:.2f}")
            
            # Update each drive in the database
            conn = db.get_connection()
            cursor = conn.cursor()
            
            for drive in client_drives:
                drive_id = drive.get('id')
                try:
                    query = """
                    UPDATE Trips
                    SET 
                        Fare = ?,
                        Tip = ?,
                        Earnings_Driver = ?,
                        Payment_Method = 'Venmo',
                        Passenger_FirstName = ?,
                        TripType = 'Private',
                        LastUpdated = GETDATE()
                    WHERE TripID = ?
                    """
                    
                    cursor.execute(query, (
                        fare_per_trip,
                        tip_per_trip,
                        fare_per_trip + tip_per_trip,
                        client_key,
                        str(drive_id)
                    ))
                    conn.commit()
                    logging.info(f"   Updated Trip {drive_id} with Venmo payment")
                    
                except Exception as e:
                    logging.error(f"Error updating Trip {drive_id}: {e}")
            
            conn.close()

    logging.info("--- Processing Complete ---")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        target_date = sys.argv[1]
        process_trips(target_date)
    else:
        process_trips()
