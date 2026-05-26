import os

def main():
    dashboard_path = 'c:/Users/PeterTeehan/OneDrive - COS Tesla LLC/COS Tesla - Website/Summit-OS-Web-master/frontend/apps/dashboard/src/components/DriverDashboard.tsx'
    if not os.path.exists(dashboard_path):
        return

    with open(dashboard_path, 'r', encoding='utf-8') as f:
        content = f.read()

    lines = content.splitlines()
    print("Searching for fetch in DriverDashboard.tsx...")

    for idx, line in enumerate(lines, 1):
        if "fetch(" in line or "x-functions-key" in line or "Authorization" in line or "AZURE_BASE" in line:
            print(f"Line {idx}: {line.strip()}")

if __name__ == '__main__':
    main()
