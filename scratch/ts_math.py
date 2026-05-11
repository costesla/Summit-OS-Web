"""
The screenshots have filename: Screenshot_20260504_172506
strptime gives: 2026-05-04 17:25:06 (naive)
.timestamp() on Windows/mountain time converts to epoch as if it were local time
Then we stored that epoch value directly.
When the backend converts: datetime.utcfromtimestamp(epoch) - 7h gives MST time.
So if the file was 17:25 local (MST), the epoch is 17:25 local MST.
utcfromtimestamp would give 17:25+7 = 00:25 UTC next day... 
wait, let me just check what the current SQL values are after the +7 fix.
"""
import pyodbc
conn = pyodbc.connect('Driver={ODBC Driver 18 for SQL Server};Server=tcp:summitsqlus23436.database.windows.net,1433;Database=SummitMediaDB;Uid=summitadmin;Pwd=Summ1tSync2026!Azure;Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;')
cur = conn.cursor()
cur.execute("""
    SELECT TOP 5 RideID, Timestamp_Start, Driver_Earnings, Source_URL
    FROM Rides.Rides
    WHERE Driver_Earnings > 0
    ORDER BY Timestamp_Start
""")
for r in cur.fetchall():
    print(r[0], r[1], r[2], r[3][:80] if r[3] else None)

# The screenshot filename is: Screenshot_20260504_172506_Uber Driver.jpg
# If strptime gives 2026-05-04 17:25:06 as naive, and then .timestamp() is called:
# On a machine in UTC-6, timestamp() treats it as UTC-6, so epoch = 17:25:06 + 6h offset = 23:25:06 UTC
# Then save that as Timestamp_Start naively... it would be stored as is.
# Actually the sync script does: t_obj = datetime.strptime(...); timestamp_epoch = t_obj.timestamp()
# Then db.save_trip({"timestamp_epoch": timestamp_epoch})
# In save_trip, it likely does: datetime.fromtimestamp(timestamp_epoch) or datetime.utcfromtimestamp()

import datetime
fn_time = "20260504 172506"
t_obj = datetime.datetime.strptime(fn_time, "%Y%m%d %H%M%S")
epoch = t_obj.timestamp()
print(f"\nFilename time: {t_obj}")
print(f"Epoch: {epoch}")
print(f"utcfromtimestamp: {datetime.datetime.utcfromtimestamp(epoch)}")
print(f"fromtimestamp (local): {datetime.datetime.fromtimestamp(epoch)}")
