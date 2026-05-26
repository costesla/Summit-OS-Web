import sys

def main():
    path = r"c:\Users\PeterTeehan\OneDrive - COS Tesla LLC\COS Tesla - Website\Summit-OS-Web-master\frontend\apps\dashboard\src\components\DriverDashboard.tsx"
    try:
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        print("--- TessieDrivesPanel fare rendering ---")
        for i, line in enumerate(lines):
            # check lines around 460-490
            if 450 <= i + 1 <= 500:
                out = f"{i+1}: {line.strip()}\n"
                sys.stdout.buffer.write(out.encode('utf-8'))
                
    except Exception as e:
        print("Error:", e)

if __name__ == '__main__':
    main()
