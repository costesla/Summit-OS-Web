from datetime import datetime, timezone

ts = 1779669439
print("UTC time:", datetime.fromtimestamp(ts, timezone.utc))
print("Local time:", datetime.fromtimestamp(ts))
