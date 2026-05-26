def main():
    path = r"c:\Users\PeterTeehan\OneDrive - COS Tesla LLC\COS Tesla - Website\Summit-OS-Web-master\frontend\apps\dashboard\src\components\DriverDashboard.tsx"
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        print("Standalone DriverDashboard.tsx Statistics:")
        print("- File size:", len(content), "bytes")
        print("- Contains 'teller' (case-insensitive):", 'teller' in content.lower())
        print("- Contains 'ShieldCheck':", 'ShieldCheck' in content)
        print("- Contains 'Security':", 'Security' in content)
        print("- Contains 'TellerConnectButton':", 'TellerConnectButton' in content)
        
    except Exception as e:
        print("Error:", e)

if __name__ == '__main__':
    main()
