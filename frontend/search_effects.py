import sys

def main():
    path = r"c:\Users\PeterTeehan\OneDrive - COS Tesla LLC\COS Tesla - Website\Summit-OS-Web-master\frontend\src\components\DriverDashboard.tsx"
    try:
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        print("--- useEffect blocks in DriverDashboard.tsx ---")
        in_effect = False
        bracket_count = 0
        effect_lines = []
        for i, line in enumerate(lines):
            if 'useeffect' in line.lower():
                in_effect = True
                bracket_count = 0
                effect_lines = []
            
            if in_effect:
                effect_lines.append(f"{i+1}: {line.strip()}")
                bracket_count += line.count('{') - line.count('}')
                if bracket_count == 0 and ');' in line:
                    in_effect = False
                    for el in effect_lines:
                        sys.stdout.buffer.write((el + "\n").encode('utf-8'))
                    sys.stdout.buffer.write(("-" * 40 + "\n").encode('utf-8'))
                    
    except Exception as e:
        print("Error:", e)

if __name__ == '__main__':
    main()
