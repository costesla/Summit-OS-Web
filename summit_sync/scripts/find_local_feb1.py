import os
import datetime

def find_local_feb1():
    path = r'C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\Pictures\Camera Roll\2026'
    if not os.path.exists(path):
        print(f"Path not found: {path}")
        return

    print(f"--- Files in {path} modified on Feb 1st (Mountain Time) ---")
    
    found = []
    files = os.listdir(path)
    for f in files:
        fpath = os.path.join(path, f)
        mtime = os.path.getmtime(fpath)
        dt = datetime.datetime.fromtimestamp(mtime)
        
        # Check Feb 1st, 2026
        if dt.date() == datetime.date(2026, 2, 1):
            found.append((f, dt))
            
    found.sort(key=lambda x: x[1])
    for f, dt in found:
        print(f"{dt.strftime('%H:%M:%S')} | {f}")

if __name__ == "__main__":
    find_local_feb1()
