import sys

def main():
    # Force output encoding to UTF-8
    sys.stdout.reconfigure(encoding='utf-8')
    path = r"c:\Users\PeterTeehan\OneDrive - COS Tesla LLC\COS Tesla - Website\Summit-OS-Web-master\frontend\src\components\DriverDashboard.tsx"
    try:
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        print("--- Auth Logic near /.auth/me ---")
        for i, line in enumerate(lines):
            if '/.auth/me' in line:
                start = max(0, i - 15)
                end = min(len(lines), i + 35)
                for idx in range(start, end):
                    print(f"{idx+1}: {lines[idx]}", end="")
                print()
                
    except Exception as e:
        print("Error:", e)

if __name__ == '__main__':
    main()
