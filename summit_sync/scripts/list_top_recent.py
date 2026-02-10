import os
import datetime

def list_top_recent():
    path = r'C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\Pictures\Camera Roll'
    files = []
    for root, dirs, fnames in os.walk(path):
        for f in fnames:
            if f.lower().endswith(('.jpg', '.png', '.jpeg')):
                fpath = os.path.join(root, f)
                try:
                    mtime = os.path.getmtime(fpath)
                    files.append((f, mtime, fpath))
                except:
                    continue
    
    files.sort(key=lambda x: x[1], reverse=True)
    print("--- 20 Most Recent Screenshots in Camera Roll ---")
    for f, m, p in files[:20]:
        print(f"{datetime.datetime.fromtimestamp(m).strftime('%Y-%m-%d %H:%M:%S')} | {f} | {p}")

if __name__ == "__main__":
    list_top_recent()
