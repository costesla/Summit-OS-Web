import json
import os
import datetime
import pytz
from collections import defaultdict

# Mountain Time — automatically handles MST (UTC-7) and MDT (UTC-6)
_MT = pytz.timezone("America/Denver")

def _utc_to_mt(utc_dt: datetime.datetime) -> datetime.datetime:
    """Convert a naive UTC datetime to aware Mountain Time (handles DST)."""
    return pytz.utc.localize(utc_dt).astimezone(_MT)

def _ts_to_mt(unix_ts: float) -> datetime.datetime:
    """Convert a UNIX timestamp to aware Mountain Time datetime."""
    return datetime.datetime.fromtimestamp(unix_ts, tz=pytz.utc).astimezone(_MT)

def classify_drive(tag, location):
    tag_lower = (tag or "").lower()
    loc_lower = (location or "").lower()
    
    meals = ["ihop", "mcdonalds", "starbucks", "dunkin", "taco bell", "burger king", "wendy's", "subway", "chipotle", "panera", "carl's jr", "dutch bros", "coffee", "grocery", "king soopers", "safeway", "walmart"]
    maintenance = ["quickquack", "car wash", "supercharge", "service", "tesla service", "tire", "maintenance", "autozone"]
    personal = ["park", "gym", "museum", "home", "residence", "private"]
    
    for m in meals:
        if m in tag_lower or m in loc_lower:
            return "Meal Stop"
            
    for maint in maintenance:
        if maint in tag_lower or maint in loc_lower:
            return "Maintenance"
            
    for p in personal:
        if p in tag_lower or p in loc_lower:
            return "Personal"
            
    return "Business"

def main():
    try:
        # Load local settings for DB connection
        settings_path = 'local.settings.json'
        if os.path.exists(settings_path):
            with open(settings_path, 'r') as f:
                settings = json.load(f)
                for k, v in settings.get('Values', {}).items():
                    os.environ[k] = v

        from services.database import DatabaseClient
        db = DatabaseClient()
        conn = db.get_connection()
        cur = conn.cursor()
        
        # 1. Fetch rides from DB
        print("Querying Rides.Rides...")
        cur.execute("""
            SELECT RideID, TripType, Classification, Distance_mi, Duration_min, 
                   Tessie_DriveID, Start_SOC, End_SOC, Energy_Used_kWh, Efficiency_Wh_mi, 
                   Timestamp_Start, Pickup_Location, Dropoff_Location, Sidecar_Artifact_JSON
            FROM Rides.Rides 
            WHERE CAST(Timestamp_Start AS DATE) = '2026-05-18' 
            ORDER BY Timestamp_Start
        """)
        rows = cur.fetchall()
        print(f"Found {len(rows)} rides in database.")
        
        # 2. Map to raw_drives structure
        raw_drives = []
        for row in rows:
            ride_id = row[0]
            trip_type = row[1]
            classification = row[2]
            distance_mi = float(row[3] or 0)
            duration_min = float(row[4] or 0)
            tessie_drive_id = row[5]
            start_soc = float(row[6] or 0)
            end_soc = float(row[7] or 0)
            energy_used_kwh = float(row[8] or 0)
            efficiency_wh_mi = float(row[9] or 0)
            timestamp_start = row[10]
            pickup_location = row[11] or "Unknown"
            dropoff_location = row[12] or "Unknown"
            sidecar_json = row[13]
            
            # Load sidecar if available
            sidecar = {}
            if sidecar_json:
                try:
                    sidecar = json.loads(sidecar_json)
                except:
                    pass
            
            # Reconstruct tag
            tag = classification
            if classification == 'Uber_Dropoff' or classification == 'Uber_Matched':
                tag = 'uber'
            elif classification == 'Jackie':
                tag = 'Jackie'
            elif classification == 'Esmeralda':
                tag = 'Esmeralda'
            elif classification and classification.startswith('Private:'):
                tag = classification[len('Private:'):]
            elif not tag:
                tag = 'Uncategorized'
                
            # Localize timestamp to Mountain Time to get UNIX timestamp
            dt_start_mt = _MT.localize(timestamp_start)
            started_at = int(dt_start_mt.timestamp())
            
            # Handle ended_at
            ended_at = None
            if "Timestamp_End" in sidecar:
                try:
                    dt_end_mt = _MT.localize(datetime.datetime.strptime(sidecar["Timestamp_End"], "%Y-%m-%d %H:%M:%S"))
                    ended_at = int(dt_end_mt.timestamp())
                except:
                    pass
            if not ended_at:
                ended_at = started_at + int(duration_min * 60)
                
            # average speed in kph
            avg_speed_kph = 0.0
            if duration_min > 0 and distance_mi > 0:
                avg_speed_mph = distance_mi / (duration_min / 60)
                avg_speed_kph = avg_speed_mph / 0.621371
                
            drive_id = tessie_drive_id
            if not drive_id:
                if ride_id.startswith("TESSIE-"):
                    drive_id = ride_id[len("TESSIE-"):]
                else:
                    drive_id = ride_id
                    
            d = {
                "id": drive_id,
                "tag": tag,
                "started_at": started_at,
                "ended_at": ended_at,
                "distance": distance_mi,
                "distance_miles": distance_mi,
                "odometer_distance": distance_mi,
                "energy_used": energy_used_kwh,
                "autopilot_distance": 0.0,
                "max_speed": 0.0,
                "average_speed": avg_speed_kph,
                "starting_location": pickup_location,
                "ending_location": dropoff_location,
                "starting_battery": start_soc,
                "ending_battery": end_soc
            }
            raw_drives.append(d)
            
        print(f"Mapped {len(raw_drives)} mock raw drives.")
        
        # 3. Process grouping/blending logic
        grouped = defaultdict(list)
        suffixes_to_strip = [
            " en route", " enroute", " - en route",
            " pickup", " pick up", " pickup", " - pickup", "pickup", "pick up",
            " dropoff", " drop off", " drop-off", " - dropoff", "dropoff", "drop off",
            " arrival", " - arrival", " arrival",
            " stop ", " stop-", " stop"
        ]
        
        tag_filter = ""
        tag_lower = tag_filter.lower()
        
        for d in raw_drives:
            raw_tag = str(d.get("tag") or "Uncategorized")
            if tag_filter and tag_lower not in raw_tag.lower():
                continue
                
            base_tag = raw_tag
            tag_l = base_tag.lower()
            
            changed = True
            while changed:
                changed = False
                for s in suffixes_to_strip:
                    if tag_l.endswith(s):
                        idx = tag_l.rfind(s)
                        base_tag = base_tag[:idx]
                        tag_l = base_tag.lower()
                        changed = True
                        break
            
            base_tag = base_tag.strip()
            
            start_ts = d.get("started_at", 0)
            start_dt_mst = _ts_to_mt(start_ts) if start_ts else None
            date_str = start_dt_mst.strftime("%Y-%m-%d") if start_dt_mst else "Unknown"
            
            if raw_tag == "Uncategorized":
                group_key = f"{d.get('id')}|Uncategorized"
            else:
                group_key = f"{date_str}|{base_tag.strip()}"
                
            grouped[group_key].append(d)
            
        processed = []
        for key, drives in grouped.items():
            drives.sort(key=lambda x: x.get("started_at", 0))
            first = drives[0]
            last = drives[-1]
            
            total_dist = sum(float(d.get("distance") or 0) for d in drives)
            total_energy = sum(float(d.get("energy_used") or 0) for d in drives)
            total_autopilot = sum(float(d.get("autopilot_distance") or 0) for d in drives)
            
            start_ts = first.get("started_at", 0)
            start_dt_mst = _ts_to_mt(start_ts) if start_ts else None
            
            max_speed_kph = max((float(d.get("max_speed") or 0) for d in drives), default=0)
            if total_dist > 0:
                weighted_speed_sum = sum((float(d.get("average_speed") or 0) * float(d.get("distance") or 0)) for d in drives)
                avg_speed_kph = weighted_speed_sum / total_dist
            else:
                avg_speed_kph = sum(float(d.get("average_speed") or 0) for d in drives) / len(drives)

            efficiency = round((total_energy * 1000) / total_dist, 1) if total_dist > 0 else None
            base_tag_for_class = key.split("|")[1] if "|" in key else "Uncategorized"
            classification = classify_drive(base_tag_for_class, last.get("ending_location"))

            processed.append({
                "date": start_dt_mst.strftime("%Y-%m-%d") if start_dt_mst else None,
                "time_mst": start_dt_mst.strftime("%H:%M") if start_dt_mst else None,
                "tag": base_tag_for_class,
                "classification": classification,
                "leg_count": len(drives),
                "is_blended": len(drives) > 1,
                "distance_miles": round(total_dist, 2),
                "average_speed_mph": round(avg_speed_kph * 0.621371, 1),
                "max_speed_mph": round(max_speed_kph * 0.621371, 1),
                "energy_used_kwh": round(total_energy, 2),
                "efficiency_wh_mi": efficiency,
                "autopilot_miles": round(total_autopilot, 2),
                "start": first.get("starting_location"),
                "end": last.get("ending_location"),
                "starting_battery": first.get("starting_battery"),
                "ending_battery": last.get("ending_battery"),
                "duration_minutes": round((last.get("ended_at", 0) - first.get("started_at", 0)) / 60, 1) if first.get("started_at") and last.get("ended_at") else 0,
                "tessie_drive_id": first.get("id")
            })

        processed.sort(key=lambda x: (x['date'], x['time_mst']), reverse=True)
        print(f"\nProcessed {len(processed)} blended/classified missions:")
        for idx, mission in enumerate(processed[:10], 1):
            print(f"{idx}. Date: {mission['date']} | Time: {mission['time_mst']} | Tag: {mission['tag']} | Class: {mission['classification']} | Legs: {mission['leg_count']} | Dist: {mission['distance_miles']} mi | Start: {mission['start'][:40]} | End: {mission['end'][:40]}")
            
        cur.close()
        conn.close()

    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
