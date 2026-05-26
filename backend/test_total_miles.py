import requests

def main():
    url = "https://summitos-api.azurewebsites.net/api/copilot/tessie/day-summary?date=2026-05-17"
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            total_miles = data.get("total_miles")
            drive_count = data.get("drive_count")
            print("API total_miles:", total_miles)
            print("API drive_count:", drive_count)
            
            drives = data.get("drives", [])
            calculated_sum = sum(float(d.get("distance_miles") or 0) for d in drives)
            print("Sum of individual drive distance_miles:", calculated_sum)
            
            # Print tag breakdown
            breakdown = {}
            for d in drives:
                tag = d.get("tag") or "Untagged"
                dist = float(d.get("distance_miles") or 0)
                breakdown[tag] = breakdown.get(tag, 0) + dist
            
            print("\nBreakdown by tag:")
            for tag, dist in sorted(breakdown.items(), key=lambda x: x[1], reverse=True):
                print(f"- {tag}: {dist:.2f} mi")
                
        else:
            print("Failed to fetch. Status:", resp.status_code)
    except Exception as e:
        print("Error:", e)

if __name__ == '__main__':
    main()
