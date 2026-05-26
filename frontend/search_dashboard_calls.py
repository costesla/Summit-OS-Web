import re

def main():
    path = r"c:\Users\PeterTeehan\OneDrive - COS Tesla LLC\COS Tesla - Website\Summit-OS-Web-master\frontend\src\components\DriverDashboard.tsx"
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        print("--- Fetch URLs in DriverDashboard.tsx ---")
        matches = re.findall(r'fetch\([^\n]+\)', content)
        for m in matches[:15]:
            print(m)
            
        print("\n--- Endpoint references in DriverDashboard.tsx ---")
        endpoints = re.findall(r'["\'](/api/[a-zA-Z0-9_/.-]+)["\']', content)
        for ep in set(endpoints):
            print("-", ep)
            
    except Exception as e:
        print("Error:", e)

if __name__ == '__main__':
    main()
