import os

def main():
    base_dir = 'c:/Users/PeterTeehan/OneDrive - COS Tesla LLC/COS Tesla - Website/Summit-OS-Web-master/frontend'
    for root, dirs, files in os.walk(base_dir):
        if 'node_modules' in dirs:
            dirs.remove('node_modules')
        if '.next' in dirs:
            dirs.remove('.next')
        for file in files:
            if file.endswith(('.ts', '.tsx', '.json', '.html')):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    if 'azurewebsites.net' in content:
                        print(f"Found hardcoded URL in {os.path.relpath(filepath, base_dir)}:")
                        lines = content.splitlines()
                        for idx, line in enumerate(lines, 1):
                            if 'azurewebsites.net' in line:
                                print(f"  Line {idx}: {line.strip()}")
                except Exception as e:
                    pass

if __name__ == '__main__':
    main()
