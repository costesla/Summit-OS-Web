import requests
import time
import sys

endpoints = [
    {"name": "ping", "url": "https://summitos-api.azurewebsites.net/api/ping"},
    {"name": "vehicle/status", "url": "https://summitos-api.azurewebsites.net/api/copilot/vehicle/status"},
    {"name": "charging/live", "url": "https://summitos-api.azurewebsites.net/api/copilot/charging/live"},
    {"name": "trips/latest", "url": "https://summitos-api.azurewebsites.net/api/copilot/trips/latest?days=7"},
    {"name": "metrics/daily", "url": "https://summitos-api.azurewebsites.net/api/copilot/metrics/daily?start_date=2026-05-01&end_date=2026-05-18"},
    {"name": "metrics/summary", "url": "https://summitos-api.azurewebsites.net/api/copilot/metrics/summary?days=30"},
    {"name": "tessie/drives", "url": "https://summitos-api.azurewebsites.net/api/copilot/tessie/drives?days=7"},
    {"name": "tessie/day-summary", "url": "https://summitos-api.azurewebsites.net/api/copilot/tessie/day-summary"},
    {"name": "openapi.json", "url": "https://summitos-api.azurewebsites.net/api/copilot/openapi.json"}
]

print("--- Initiating SummitOS API Validation via Python ---")
for ep in endpoints:
    start_time = time.time()
    try:
        resp = requests.get(ep["url"], timeout=15)
        elapsed = time.time() - start_time
        if resp.status_code == 200:
            print(f"[PASS] {ep['name']:<20} - Status 200 - Time: {elapsed:.2f}s")
        else:
            print(f"[FAIL] {ep['name']:<20} - Status {resp.status_code} - Time: {elapsed:.2f}s")
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"[FAIL] {ep['name']:<20} - Error: {type(e).__name__} - Time: {elapsed:.2f}s")

print("--- Validation Complete ---")
