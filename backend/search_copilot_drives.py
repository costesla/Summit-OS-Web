def main():
    path = r"c:\Users\PeterTeehan\OneDrive - COS Tesla LLC\COS Tesla - Website\Summit-OS-Web-master\backend\api\copilot.py"
    try:
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        print("--- copilot/tessie/drives references in copilot.py ---")
        for i, line in enumerate(lines):
            if 'tessie/drives' in line.lower() or 'drives' in line.lower():
                # print 5 lines before and after if it is the route
                if 'tessie/drives' in line.lower():
                    print(f"--- ROUTE FOUND AT LINE {i+1} ---")
                    for j in range(max(0, i-5), min(len(lines), i+15)):
                        print(f"{j+1}: {lines[j].strip()}")
                    
    except Exception as e:
        print("Error:", e)

if __name__ == '__main__':
    main()
