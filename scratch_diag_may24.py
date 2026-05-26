import os, json, pyodbc

backend_dir = os.path.join(os.getcwd(), 'backend')
with open(os.path.join(backend_dir, 'local.settings.json')) as f:
    for k, v in json.load(f).get('Values', {}).items():
        os.environ[k] = v

conn = pyodbc.connect(os.environ["SQL_CONNECTION_STRING"])
cursor = conn.cursor()

# The 5 records with numeric timestamp IDs are duplicates of May 23rd data
# but stamped as May 24th. Delete them.
print("=== Deleting duplicate numeric-ID expense records for May 24th ===")
cursor.execute("""
    DELETE FROM Rides.ManualExpenses
    WHERE CAST(Timestamp AS DATE) = '2026-05-24'
    AND ExpenseID NOT LIKE 'EXP-%'
""")
print(f"Deleted {cursor.rowcount} duplicate record(s)")
conn.commit()

print("\n=== Final May 24th expenses ===")
cursor.execute("""
    SELECT ExpenseID, Category, Amount, Timestamp
    FROM Rides.ManualExpenses
    WHERE CAST(Timestamp AS DATE) = '2026-05-24'
    ORDER BY Timestamp
""")
rows = cursor.fetchall()
total = 0
for r in rows:
    print(f"  {r[0]} | {str(r[1]):20s} | ${r[2]:.2f} | {r[3]}")
    total += r[2]
print(f"\nTotal: ${total:.2f} across {len(rows)} expense(s)")

cursor.close()
conn.close()
