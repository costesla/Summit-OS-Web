import sys
import os
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.database import DatabaseClient

load_dotenv()
db = DatabaseClient()

def find_private_candidates():
    query = "SELECT TripID, Notes, Passenger_FirstName, Earnings_Driver FROM Trips"
    results = db.execute_query_with_results(query)
    
    candidates = []
    names_to_find = ["Esmeralda", "Jacuelyn", "Jackie", "Omar", "Milda"]
    
    for r in results:
        txt = str(r.get('Notes', '')).lower()
        name = str(r.get('Passenger_FirstName', '')).lower()
        
        found_name = None
        for n in names_to_find:
            if n.lower() in txt or n.lower() in name:
                found_name = n
                break
        
        if found_name or "payment from" in txt or "venmo" in txt:
             candidates.append({
                 "id": r['TripID'],
                 "name": r['Passenger_FirstName'] or found_name or "Unknown",
                 "earn": r['Earnings_Driver'],
                 "is_venmo": "venmo" in txt or "payment from" in txt,
                 "snippet": txt[:50]
             })
             
    # Deduplicate by snippet (approx)
    unique_candidates = []
    seen_snippets = set()
    for c in candidates:
        snip = c['snippet'][:30]
        if snip not in seen_snippets:
            unique_candidates.append(c)
            seen_snippets.add(snip)
            
    print(f"Found {len(unique_candidates)} unique private candidates:")
    for c in unique_candidates:
        print(f" > {c['id']} | Name: {c['name']} | Earn: {c['earn']} | Venmo: {c['is_venmo']} | {c['snippet']}")

if __name__ == "__main__":
    find_private_candidates()
