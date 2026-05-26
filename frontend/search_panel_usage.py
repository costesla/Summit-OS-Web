def main():
    path = r"c:\Users\PeterTeehan\OneDrive - COS Tesla LLC\COS Tesla - Website\Summit-OS-Web-master\frontend\apps\dashboard\src\components\DriverDashboard.tsx"
    try:
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        print("--- UberTripsPanel usage in STANDALONE DriverDashboard.tsx ---")
        for i, line in enumerate(lines):
            if 'ubertripspanel' in line.lower():
                print(f"{i+1}: {line.strip()}")
                
    except Exception as e:
        print("Error:", e)

if __name__ == '__main__':
    main()
