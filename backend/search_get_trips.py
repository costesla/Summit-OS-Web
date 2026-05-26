def main():
    path = r"c:\Users\PeterTeehan\OneDrive - COS Tesla LLC\COS Tesla - Website\Summit-OS-Web-master\backend\services\database.py"
    try:
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        print("--- get_trips_by_date in database.py ---")
        found = False
        func_lines = []
        for i, line in enumerate(lines):
            if 'def get_trips_by_date' in line:
                found = True
            if found:
                func_lines.append(f"{i+1}: {line.strip()}")
                if 'def ' in line and len(func_lines) > 2:
                    found = False
                    for fl in func_lines[:-1]:
                        print(fl)
                    print("-" * 40)
                    
    except Exception as e:
        print("Error:", e)

if __name__ == '__main__':
    main()
