from lib.tessie import TessieClient
from lib.database import DatabaseClient
from dotenv import load_dotenv
from datetime import datetime
import os

load_dotenv()
t = TessieClient()
db = DatabaseClient()
vin = os.environ.get('TESSIE_VIN')

# May 20, 2026
# Let's query from 2026-05-20 00:00:00 to 2026-05-20 23:59:59 in local time.
# Since the server/API uses timestamps, let's look at the whole day + some timezone buffers.
start = datetime.strptime('2026-05-20 00:00:00', '%Y-%m-%d %H:%M:%S')
end = datetime.strptime('2026-05-20 23:59:59', '%Y-%m-%d %H:%M:%S')

print(f"--- TESSIE API CHARGES FOR 2026-05-20 ---")
try:
    charges = t.get_charges(vin, int(start.timestamp()), int(end.timestamp()))
    print(f"Found {len(charges)} charging sessions on Tessie API:")
    for i, charge in enumerate(charges, 1):
        started = datetime.fromtimestamp(charge.get('started_at', 0))
        ended = datetime.fromtimestamp(charge.get('ended_at', 0))
        print(f"#{i}: ID: {charge.get('id')}")
        print(f"  Started: {started} | Ended: {ended}")
        print(f"  Location: {charge.get('location')}")
        print(f"  Energy Added: {charge.get('energy_added')} kWh | Cost: ${charge.get('cost')}")
except Exception as e:
    print(f"Tessie Error: {e}")

print(f"\n--- DATABASE CHARGES (dbo.ChargingSessions / Rides.ChargingSessions) FOR 2026-05-20 ---")
try:
    # Query Rides.ChargingSessions or ChargingSessions
    db_charges = db.execute_query_with_results(
        "SELECT * FROM Rides.ChargingSessions WHERE CAST(Start_Time AS DATE) = '2026-05-20'"
    )
    print(f"Found {len(db_charges)} charging sessions in Rides.ChargingSessions:")
    for i, charge in enumerate(db_charges, 1):
        print(f"#{i}: SessionID: {charge.get('SessionID')}")
        print(f"  Start_Time: {charge.get('Start_Time')} | End_Time: {charge.get('End_Time')}")
        print(f"  Location_Name: {charge.get('Location_Name')}")
        print(f"  Energy_Added_kWh: {charge.get('Energy_Added_kWh')} | Cost: ${charge.get('Cost')}")
        
    db_charges_dbo = db.execute_query_with_results(
        "SELECT * FROM ChargingSessions WHERE CAST(Start_Time AS DATE) = '2026-05-20'"
    )
    print(f"\nFound {len(db_charges_dbo)} charging sessions in dbo.ChargingSessions:")
    for i, charge in enumerate(db_charges_dbo, 1):
        print(f"#{i}: SessionID: {charge.get('SessionID')}")
        print(f"  Start_Time: {charge.get('Start_Time')} | End_Time: {charge.get('End_Time')}")
except Exception as e:
    print(f"DB Error: {e}")
