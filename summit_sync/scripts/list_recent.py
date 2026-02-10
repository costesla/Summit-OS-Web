import os
import datetime

def list_files():
    path = r'C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\Pictures\Camera Roll\2026'
    files = []
    for f in os.listdir(path):
        fpath = os.path.join(path, f)
        if os.path.isfile(fpath):
            mtime = os.path.getmtime(fpath)
            files.append((f, mtime))
    
    files.sort(key=lambda x: x[1], reverse=True)
    for f, t in files[:20]:
        print(f"{datetime.datetime.fromtimestamp(t)} | {f}")

if __name__ == "__main__":
    list_files()
