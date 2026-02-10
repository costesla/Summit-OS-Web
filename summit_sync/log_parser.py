
import re

log_path = r"summit_sync\mission_final_success.txt"

with open(log_path, "r") as f:
    content = f.read()

diagnostics = re.findall(r"--- TELEMETRY ALIGNMENT DIAGNOSTIC ---(.*?)--------------------------------------", content, re.DOTALL)

for i, diag in enumerate(diagnostics[:10]):
    print(f"Match {i+1}:")
    print(diag.strip())
    print("-" * 20)
