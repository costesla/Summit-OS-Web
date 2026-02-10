import os
import re
from datetime import datetime

# Path to images
WATCH_DIR = r"C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\Pictures\Camera Roll\2026"

def analyze_timestamps():
    print(f"Scanning {WATCH_DIR}...")
    
    files = []
    for f in os.listdir(WATCH_DIR):
        if not f.endswith(('.jpg', '.png')):
            continue
            
        # Extract timestamp from filename: Screenshot_20260206_110650...
        # Format: YYYYMMDD_HHMMSS
        match = re.search(r"(\d{8})_(\d{6})", f)
        if match:
            date_str = match.group(1)
            time_str = match.group(2)
            
            # Filter for Feb 6 only
            if date_str != "20260206":
                continue
                
            dt = datetime.strptime(f"{date_str}{time_str}", "%Y%m%d%H%M%S")
            files.append({"filename": f, "dt": dt})

    # Sort by time
    files.sort(key=lambda x: x["dt"])
    
    # Analyze gaps
    print(f"\nFound {len(files)} images for Feb 6.")
    print("-" * 60)
    
    clusters = []
    current_cluster = []
    
    for i, file_obj in enumerate(files):
        if not current_cluster:
            current_cluster.append(file_obj)
            continue
            
        prev_file = current_cluster[-1]
        time_diff = (file_obj["dt"] - prev_file["dt"]).total_seconds()
        
        # If gap is small (e.g. < 180 seconds / 3 mins), group them
        if time_diff < 180:
            current_cluster.append(file_obj)
        else:
            clusters.append(current_cluster)
            current_cluster = [file_obj]
            
    if current_cluster:
        clusters.append(current_cluster)
        
    # Print Clusters
    total_images_in_clusters = 0
    private_trip_count = 0
    uber_trip_count = 0
    
    for idx, cluster in enumerate(clusters):
        start_time = cluster[0]["dt"].strftime("%H:%M:%S")
        duration = (cluster[-1]["dt"] - cluster[0]["dt"]).total_seconds()
        count = len(cluster)
        total_images_in_clusters += count
        
        # Guess Type
        start_fname = cluster[0]['filename']
        trip_type = "UNKNOWN"
        if count == 1:
            trip_type = "Uber (Likely)"
            uber_trip_count += 1
        elif count >= 4:
            trip_type = "Private (Likely - ~5 cards)"
            private_trip_count += 1
        else:
            trip_type = "Ambiguous"
            
        print(f"Cluster {idx+1}: {start_time} (Dur: {duration}s) - {count} images - {trip_type}")
        for item in cluster:
            print(f"   - {item['filename']}")
        print("")

    print("-" * 60)
    print(f"Total Clusters: {len(clusters)}")
    print(f"Estimated Private Trips: {private_trip_count}")
    print(f"Estimated Uber Trips: {uber_trip_count}")
    print(f"Total Images: {total_images_in_clusters}")

if __name__ == "__main__":
    analyze_timestamps()
