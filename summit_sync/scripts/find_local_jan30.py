import os
import datetime

def find_local_screenshots():
    path = r'C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\Pictures\Camera Roll\2026'
    if not os.path.exists(path):
        print(f"Path not found: {path}")
        return

    print(f"--- Files in {path} modified on Jan 30 (Mountain Time) ---")
    
    found = []
    files = os.listdir(path)
    for f in files:
        fpath = os.path.join(path, f)
        mtime = os.path.getmtime(fpath)
        dt = datetime.datetime.fromtimestamp(mtime)
        
        # Check Jan 30th
        if dt.date() == datetime.date(2026, 1, 30):
            found.append((f, dt))
            
    found.sort(key=lambda x: x[1])
    for f, dt in found:
        print(f"{dt.strftime('%H:%M:%S')} | {f}")

if __name__ == "__main__":
    find_local_screenshots()
