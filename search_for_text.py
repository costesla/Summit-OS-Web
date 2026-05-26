import os

def search_files(directory, query):
    results = []
    query_lower = query.lower()
    for root, dirs, files in os.walk(directory):
        if 'venv' in root or '.git' in root or '.next' in root or 'node_modules' in root:
            continue
        for file in files:
            path = os.path.join(root, file)
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    for line_num, line in enumerate(f, 1):
                        if query_lower in line.lower():
                            results.append((path, line_num, line.strip()))
            except Exception:
                pass
    return results

def main():
    q = "dashboard"
    print(f"Searching for '{q}':")
    res = search_files(".", q)
    for path, line, content in res[:40]:
        print(f"- {path}:{line} | {content}")

if __name__ == '__main__':
    main()
