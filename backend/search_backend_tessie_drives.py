import os

def main():
    directory = r"c:\Users\PeterTeehan\OneDrive - COS Tesla LLC\COS Tesla - Website\Summit-OS-Web-master\backend"
    print(f"Searching for 'tessie/drives' in {directory}:")
    for root, dirs, files in os.walk(directory):
        for file in files:
            if not file.endswith('.py'):
                continue
            path = os.path.join(root, file)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    for line_num, line in enumerate(f, 1):
                        if 'tessie/drives' in line.lower() or 'def get_drives' in line.lower() or 'class drives' in line.lower():
                            print(f"{path}:{line_num} | {line.strip()}")
            except Exception as e:
                pass

if __name__ == '__main__':
    main()
