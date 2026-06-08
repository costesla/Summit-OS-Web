import requests, datetime, pytz, os, json, pyodbc

backend_dir = os.path.join(os.getcwd(), 'backend')
with open(os.path.join(backend_dir, 'local.settings.json')) as f:
    for k, v in json.load(f).get('Values', {}).items():
        os.environ[k] = v

MT  = pytz.timezone('America/Denver')
KEY = 'uZEcFjEipPP1SVmT6i6sTsMtNI5S7pvd'
VIN = '7SAYGDEEXRF075302'

# 1. Fetch all June 1 drives from Tessie API
from_ts = int(MT.localize(datetime.datetime(2026,6,1,0,0,0)).timestamp())
to_ts   = int(MT.localize(datetime.datetime(2026,6,2,4,0,0)).timestamp())

drives = []
page = 1
while True:
    batch = requests.get(f'https://api.tessie.com/{VIN}/drives',
        headers={'Authorization': f'Bearer {KEY}'},
        params={'from': from_ts, 'to': to_ts, 'limit': 100, 'page': page},
        timeout=20).json().get('results', [])
    drives.extend(batch)
    if len(batch) < 100: break
    page += 1

print(f'Fetched {len(drives)} drives from Tessie API')

def tessie_tag_to_classification(tag):
    if not tag:
        return 'Untagged'
    t = tag.lower()
    if 'uber' in t:
        return 'Uber_Pickup' if 'en route' in t else 'Uber_Dropoff'
    if t.startswith('jackie'):
        return 'Jackie'
    if t.startswith('esmeralda'):
        return 'Esmeralda'
    if t.startswith('lauren'):
        return 'Lauren'
    if t.startswith('ryan'):
        return f'Private:{tag}'
    return f'Private:{tag}'

# 2. Update DB
conn = pyodbc.connect(os.environ['SQL_CONNECTION_STRING'])
cursor = conn.cursor()

updated = 0
for d in drives:
    drive_id = str(d.get('id') or '')
    tag      = d.get('tag') or ''
    cls      = tessie_tag_to_classification(tag)
    rid      = f'TESSIE-{drive_id}'

    cursor.execute("SELECT RideID FROM Rides.Rides WHERE RideID = ?", (rid,))
    if not cursor.fetchone():
        print(f'  SKIP (not in DB): {rid}')
        continue

    cursor.execute("""
        UPDATE Rides.Rides
        SET Classification = ?, LastUpdated = GETUTCDATE()
        WHERE RideID = ?
    """, (cls, rid))
    start = datetime.datetime.fromtimestamp(d['started_at'], MT).strftime('%H:%M') if d.get('started_at') else '?'
    print(f'  {start}  {rid}  [{tag}] -> {cls}')
    updated += 1

conn.commit()
print(f'\nDone. {updated} records updated.')
cursor.close()
conn.close()
