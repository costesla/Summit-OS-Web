import os

def search_files(directory, query):
    results = []
    query_lower = query.lower()
    for root, dirs, files in os.walk(directory):
        # Skip virtual envs and git folder
        if 'venv' in root or '.git' in root or '.next' in root or 'node_modules' in root:
            continue
        for file in files:
            if not file.endswith(('.py', '.sql', '.json', '.js', '.ts', '.tsx', '.yaml', '.yml', '.md')):
                continue
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
    queries = ["No verified drives", "regen", "Idle-in-drive", "driving time"]
    for q in queries:
        print(f"\nSearching for '{q}':")
        res = search_files(r"c:\Users\PeterTeehan\OneDrive - COS%20Tesla%20LLC\COS%20Tesla%20-%20Website" if os.name == 'nt' else ".", q)
        if not res:
            # Fall back to shorter path if OneDrive name has spaces/special characters
            res = search_files(os.getcwd(), q)
        
        for path, line, content in res[:10]:
            print(f"- {os.path.basename(path)}:{line} | {content}")
        if len(res) > 10:
            print(f"... and {len(res) - 10} more matches")

if __name__ == '__main__':
    main()
