import os
import datetime

def find_newest_files():
    path = r'C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\Pictures\Camera Roll\2026'
    
    files = []
    for root, dirs, fnames in os.walk(path):
        for f in fnames:
            fpath = os.path.join(root, f)
            try:
                mtime = datetime.datetime.fromtimestamp(os.path.getmtime(fpath))
                # Focus on files modified in the last hour or matching today's pattern
                files.append((f, mtime, fpath))
            except:
                continue
    
    # Sort by modification time descending
    files.sort(key=lambda x: x[1], reverse=True)
    
    print("--- 15 Most Recently Modified Files ---")
    for f, m, p in files[:15]:
        print(f"{m.strftime('%Y-%m-%d %H:%M:%S')} | {f}")

if __name__ == "__main__":
    find_newest_files()
