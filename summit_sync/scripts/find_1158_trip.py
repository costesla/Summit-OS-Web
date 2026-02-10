import os
import datetime

def find_trip():
    path = r'C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\Pictures\Camera Roll\2026'
    target_date = "20260130"
    
    print(f"--- Files for {target_date} sorted by Local Time (MST) ---")
    files = []
    for root, dirs, fnames in os.walk(path):
        for f in fnames:
            if target_date in f:
                fpath = os.path.join(root, f)
                # Local system time is MST
                mtime = datetime.datetime.fromtimestamp(os.path.getmtime(fpath))
                files.append((f, mtime))
    
    files.sort(key=lambda x: x[1])
    for f, m in files:
        # Check window around 11:58 AM
        if 11 <= m.hour <= 12:
            print(f"MATCH: {m.strftime('%H:%M:%S')} | {f}")
        else:
            # Still print everything for context but maybe just a subset
            if 9 <= m.hour <= 14:
                print(f"       {m.strftime('%H:%M:%S')} | {f}")

if __name__ == "__main__":
    find_trip()
