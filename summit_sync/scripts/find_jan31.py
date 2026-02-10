import os
import datetime

def find_jan31_files():
    path = r'C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\Pictures\Camera Roll\2026'
    target_date = "20260131"
    
    print(f"--- Files for {target_date} in {path} ---")
    files = []
    if not os.path.exists(path):
        print("Path does not exist!")
        # Try broader search
        parent = r'C:\Users\PeterTeehan\OneDrive - COS Tesla LLC'
        print(f"Searching parent: {parent}")
        for root, dirs, fnames in os.walk(parent):
            if "Camera Roll" in root:
                for f in fnames:
                    if target_date in f:
                        print(f"FOUND: {os.path.join(root, f)}")
        return

    for root, dirs, fnames in os.walk(path):
        for f in fnames:
            if target_date in f:
                fpath = os.path.join(root, f)
                mtime = datetime.datetime.fromtimestamp(os.path.getmtime(fpath))
                files.append((f, mtime, fpath))
    
    files.sort(key=lambda x: x[1])
    for f, m, p in files:
        print(f"{m.strftime('%Y-%m-%d %H:%M:%S')} | {f}")

if __name__ == "__main__":
    find_jan31_files()
