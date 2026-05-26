import os

def main():
    directory = r"c:\Users\PeterTeehan\OneDrive - COS Tesla LLC\COS Tesla - Website\Summit-OS-Web-master\frontend\apps\dashboard\src"
    print(f"Searching for 'teller' in {directory}:")
    for root, dirs, files in os.walk(directory):
        for file in files:
            path = os.path.join(root, file)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    for line_num, line in enumerate(f, 1):
                        if 'teller' in line.lower():
                            print(f"{path}:{line_num} | {line.strip()}")
            except Exception as e:
                pass

if __name__ == '__main__':
    main()
