import os
import datetime

def list_latest():
    path = r'C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\Pictures\Camera Roll\2026'
    today = datetime.date(2026, 1, 30)
    
    files = []
    for root, dirs, fnames in os.walk(path):
        for f in fnames:
            fpath = os.path.join(root, f)
            mtime = datetime.datetime.fromtimestamp(os.path.getmtime(fpath))
            if mtime.date() == today:
                files.append((f, mtime))
    
    files.sort(key=lambda x: x[1])
    print(f"Total files found for {today}: {len(files)}")
    print("--- Latest 30 files ---")
    for f, m in files[-30:]:
        print(f"{m.strftime('%H:%M:%S')} | {f}")

if __name__ == "__main__":
    list_latest()
