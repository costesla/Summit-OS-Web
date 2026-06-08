import os
import sys
import json
import time
import requests
import pyodbc
from datetime import datetime, timedelta, timezone

# Load environment variables from backend/local.settings.json
backend_dir = os.path.join(os.getcwd(), 'backend')
settings_path = os.path.join(backend_dir, 'local.settings.json')
if os.path.exists(settings_path):
    with open(settings_path, 'r') as f:
        settings = json.load(f)
        for k, v in settings.get('Values', {}).items():
            os.environ[k] = v

conn_str = os.environ.get("SQL_CONNECTION_STRING")
api_key = "0mBOWenSqEI1Fv7xCmSTnKpToUQ7Xr65"
vin = "7SAYGDEEXRF075302"

if not conn_str or not api_key or not vin:
    print("Error: Missing SQL_CONNECTION_STRING, TESSIE_API_KEY, or TESSIE_VIN.")
    sys.exit(1)

def get_connection():
    return pyodbc.connect(conn_str)

def format_ts(ts, tz):
    if not ts: return None
    return datetime.fromtimestamp(ts, tz).strftime('%Y-%m-%d %H:%M:%S')

def classify_tag(tag):
    if not tag: return 'Untagged'
    t = tag.lower()
    if 'charging session' in t or 'charge session' in t:
        return f'Private:{tag}'
    if t in ('uber picture', 'uber photo'):
        return f'Private:{tag}'
    if 'uber' in t:
        return 'Uber_Dropoff'
    if 'jackie' in t:
        return 'Jackie'
    if 'esmeralda' in t:
        return 'Esmeralda'
    return f'Private:{tag}'

def scan_and_import():
    tz_mdt = timezone(timedelta(hours=-6))
    conn = get_connection()
    cursor = conn.cursor()

    print("====================================================")
    print("HISTORICAL TESSIE ARCHIVE BULK IMPORTER")
    print("====================================================")
    
    # 1. Establish the archive search window (e.g. 2 years ago up to the start of our DB logs)
    end_dt = datetime(2026, 2, 1) # Stop at February 2026 (since we have data from Jan 28, 2026)
    start_dt = end_dt - timedelta(days=365) # Go back 1 year initially (adjust as needed)
    
    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp())
    
    print(f"Scanning archive gap:")
    print(f"  -> From: {start_dt.strftime('%Y-%m-%d')}")
    print(f"  -> To:   {end_dt.strftime('%Y-%m-%d')}")
    print("Connecting to Tessie API...")

    # Fetch drives paged back
    drives_imported = 0
    charges_imported = 0
    page = 1
    page_size = 250
    
    # Fetch Drives
    while True:
        url = f"https://api.tessie.com/{vin}/drives"
        headers = {"Authorization": f"Bearer {api_key}"}
        params = {
            "from": start_ts,
            "to": end_ts,
            "limit": page_size,
            "page": page
        }
        
        print(f"Requesting Page {page} of historic drives...")
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            print(f"Error calling Tessie API: {resp.status_code}")
            break
            
        data = resp.json()
        results = data.get("results", [])
        if not results:
            print("No more historic drives found in this window.")
            break
            
        print(f"Found {len(results)} drives on page {page}. Ingesting into database...")
        
        for d in results:
            drive_id = f"TESSIE-{d.get('id')}"
            t_start = d.get('started_at')
            t_end = d.get('ended_at')
            
            start_time = format_ts(t_start, tz_mdt)
            end_time = format_ts(t_end, tz_mdt)
            dist = d.get('distance') or d.get('distance_miles') or d.get('odometer_distance', 0)
            duration = d.get('duration_minutes', 0)
            p_loc = d.get('starting_location', 'Unknown')
            d_loc = d.get('ending_location', 'Unknown')
            s_soc = d.get('starting_battery')
            e_soc = d.get('ending_battery')
            energy = d.get('energy_used')
            eff = d.get('efficiency')
            tag = d.get('tag') or ''
            classification = classify_tag(tag)
            t_type = "Uber" if "uber" in tag.lower() else "Private"
            
            # Simple merge insert
            merge_query = """
            MERGE INTO Rides.Rides AS target
            USING (SELECT ? AS RideID) AS source
            ON (target.RideID = source.RideID)
            WHEN NOT MATCHED THEN
                INSERT (
                    RideID, TripType, Timestamp_Start, Pickup_Location, Dropoff_Location,
                    Distance_mi, Duration_min, Tessie_DriveID, Tessie_Distance,
                    Fare, Tip, Driver_Earnings, Platform_Cut,
                    Start_SOC, End_SOC, Energy_Used_kWh, Efficiency_Wh_mi,
                    Source_URL, Classification, Sidecar_Artifact_JSON, CreatedAt
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0.0, 0.0, 0.0, 0.0, ?, ?, ?, ?, '', ?, ?, GETDATE());
            """
            
            params_merge = (
                drive_id,
                drive_id, t_type, start_time, p_loc, d_loc,
                dist, duration, drive_id, dist,
                s_soc, e_soc, energy, eff,
                classification, json.dumps(d)
            )
            
            cursor.execute(merge_query, params_merge)
            drives_imported += 1
            
        conn.commit()
        
        if len(results) < page_size:
            break
            
        page += 1
        time.sleep(0.5) # limit api hammer

    print(f"\nHistorical drives ingestion complete! Imported: {drives_imported} drives.")

    # Fetch Charges
    page = 1
    while True:
        url = f"https://api.tessie.com/{vin}/charges"
        headers = {"Authorization": f"Bearer {api_key}"}
        params = {
            "from": start_ts,
            "to": end_ts,
            "limit": page_size,
            "page": page
        }
        
        print(f"Requesting Page {page} of historic charges...")
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            print(f"Error calling Tessie charges API: {resp.status_code}")
            break
            
        data = resp.json()
        results = data.get("results", [])
        if not results:
            print("No more historic charges found in this window.")
            break
            
        print(f"Found {len(results)} charges on page {page}. Ingesting into database...")
        
        for c in results:
            sid = str(c.get('id'))
            s_time = format_ts(c.get('started_at') or c.get('starting_at'), tz_mdt)
            e_time = format_ts(c.get('ended_at') or c.get('ending_at'), tz_mdt)
            energy = c.get('energy_added', 0)
            cost = c.get('cost', 0)
            loc = c.get('location', 'Unknown')
            
            merge_charge = """
            MERGE INTO Rides.ChargingSessions AS target
            USING (SELECT ? AS SessionID) AS source
            ON (target.SessionID = source.SessionID)
            WHEN NOT MATCHED THEN
                INSERT (SessionID, Start_Time, End_Time, Location_Name, Energy_Added_kWh, Cost, LastUpdated)
                VALUES (?, ?, ?, ?, ?, ?, GETDATE());
            """
            cursor.execute(merge_charge, (sid, sid, s_time, e_time, loc, energy, cost))
            charges_imported += 1
            
        conn.commit()
        
        if len(results) < page_size:
            break
            
        page += 1
        time.sleep(0.5)

    print(f"Historical charges ingestion complete! Imported: {charges_imported} sessions.")
    cursor.close()
    conn.close()

if __name__ == "__main__":
    scan_and_import()
