import os

def main():
    dashboard_path = 'c:/Users/PeterTeehan/OneDrive - COS Tesla LLC/COS Tesla - Website/Summit-OS-Web-master/frontend/apps/dashboard/src/components/DriverDashboard.tsx'
    if not os.path.exists(dashboard_path):
        print("Dashboard file not found at:", dashboard_path)
        return

    with open(dashboard_path, 'r', encoding='utf-8') as f:
        content = f.read()

    lines = content.splitlines()
    print("Scanning DriverDashboard.tsx...")

    # 1. Look for dangerouslySetInnerHTML
    for idx, line in enumerate(lines, 1):
        if "dangerouslySetInnerHTML" in line:
            print(f"[XSS POTENTIAL] Line {idx}: {line.strip()}")

    # 2. Look for target="_blank" without rel="noopener noreferrer"
    for idx, line in enumerate(lines, 1):
        if 'target="_blank"' in line and 'noopener' not in line:
            print(f"[TABNABBING VULNERABILITY] Line {idx}: {line.strip()}")

    # 3. Look for hardcoded keys / endpoints
    for idx, line in enumerate(lines, 1):
        if "http://" in line:
            print(f"[INSECURE HTTP] Line {idx}: {line.strip()}")
        if "azurewebsites.net" in line:
            print(f"[HARDCODED BACKEND] Line {idx}: {line.strip()}")
        if "localStorage.set" in line or "localStorage.get" in line:
            print(f"[LOCAL STORAGE] Line {idx}: {line.strip()}")

    # 4. Check for eval / unsafe code
    for idx, line in enumerate(lines, 1):
        if "eval(" in line:
            print(f"[EVAL UNSAFE] Line {idx}: {line.strip()}")

if __name__ == '__main__':
    main()
