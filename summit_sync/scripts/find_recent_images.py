import os
import datetime

def find_recent_onedrive():
    parent = r'C:\Users\PeterTeehan\OneDrive - COS Tesla LLC'
    now = datetime.datetime.now()
    thirty_mins_ago = now - datetime.timedelta(minutes=30)
    
    print(f"Searching for files modified since {thirty_mins_ago.strftime('%H:%M:%S')} in {parent}...")
    
    found = []
    for root, dirs, fnames in os.walk(parent):
        # Skip node_modules or .git if they exist to keep it fast
        if "node_modules" in root or ".git" in root or ".next" in root:
            continue
            
        for f in fnames:
            if f.lower().endswith(('.jpg', '.png', '.jpeg')):
                fpath = os.path.join(root, f)
                try:
                    mtime = datetime.datetime.fromtimestamp(os.path.getmtime(fpath))
                    if mtime > thirty_mins_ago:
                        found.append((f, mtime, fpath))
                except:
                    continue
    
    found.sort(key=lambda x: x[1], reverse=True)
    for f, m, p in found:
        print(f"{m.strftime('%H:%M:%S')} | {f} | {p}")

if __name__ == "__main__":
    find_recent_onedrive()
