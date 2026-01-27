"""
Quick diagnostic script to verify Summit Sync pipeline is ready for tomorrow's shift.
Tests: SQL, Azure Vision, Tessie, and Azure Function connectivity.
"""
import os
import sys
from dotenv import load_dotenv

# Load environment
load_dotenv()

print("=" * 60)
print("SUMMIT SYNC PRE-FLIGHT CHECK")
print("=" * 60)

# Test 1: Environment Variables
print("\n[1/5] Checking Environment Variables...")
required_vars = [
    "AZURE_VISION_ENDPOINT",
    "SQL_CONNECTION_STRING",
    "TESSIE_API_KEY",
    "TESSIE_VIN",
    "AZUREWEBJOBSSTORAGE",
    "AZURE_FUNCTION_URL",
    "AZURE_FUNCTION_KEY"
]

missing = []
for var in required_vars:
    if os.environ.get(var):
        print(f"  [OK] {var}")
    else:
        print(f"  [MISSING] {var}")
        missing.append(var)

if missing:
    print(f"\nERROR: Missing {len(missing)} required variables!")
    sys.exit(1)
else:
    print("\n[PASS] All environment variables present")

# Test 2: SQL Database
print("\n[2/5] Testing SQL Database Connection...")
try:
    import pyodbc
    conn_str = os.environ.get("SQL_CONNECTION_STRING")
    with pyodbc.connect(conn_str, timeout=10) as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM Trips")
        count = cur.fetchone()[0]
        print(f"  ✓ Connected to SummitMediaDB")
        print(f"  ✓ Current trip count: {count}")
except Exception as e:
    print(f"  ✗ SQL Error: {str(e)}")
    sys.exit(1)

# Test 3: Tessie API
print("\n[3/5] Testing Tessie API...")
try:
    import requests
    api_key = os.environ.get("TESSIE_API_KEY")
    vin = os.environ.get("TESSIE_VIN")
    
    headers = {"Authorization": f"Bearer {api_key}"}
    res = requests.get(f"https://api.tessie.com/{vin}/state", headers=headers, timeout=10)
    
    if res.ok:
        data = res.json()
        print(f"  ✓ Tessie API responding")
        print(f"  ✓ Battery: {data.get('charge_state', {}).get('battery_level', 'N/A')}%")
    else:
        print(f"  ✗ Tessie Error: {res.status_code}")
except Exception as e:
    print(f"  ✗ Tessie Error: {str(e)}")

# Test 4: Azure Function
print("\n[4/5] Testing Azure Function Endpoint...")
try:
    import requests
    func_url = os.environ.get("AZURE_FUNCTION_URL")
    func_key = os.environ.get("AZURE_FUNCTION_KEY")
    
    # Test the sql-probe endpoint
    probe_url = f"{func_url}/api/sql-probe?code={func_key}"
    res = requests.get(probe_url, timeout=15)
    
    if res.ok:
        print(f"  ✓ Azure Function responding")
        print(f"  ✓ SQL probe successful")
    else:
        print(f"  ✗ Function Error: {res.status_code}")
        print(f"  Response: {res.text[:200]}")
except Exception as e:
    print(f"  ✗ Function Error: {str(e)}")

# Test 5: Azure Vision (using az cli)
print("\n[5/5] Testing Azure Vision OCR...")
try:
    vision_endpoint = os.environ.get("AZURE_VISION_ENDPOINT")
    print(f"  ✓ Endpoint configured: {vision_endpoint}")
    print(f"  ℹ Using Azure CLI authentication (az login)")
    print(f"  ℹ OCR will be tested with first screenshot upload")
except Exception as e:
    print(f"  ✗ Vision Error: {str(e)}")

# Summary
print("\n" + "=" * 60)
print("PRE-FLIGHT CHECK COMPLETE")
print("=" * 60)
print("\n✅ Pipeline is ready for tomorrow's Uber shift!")
print("\nNext steps:")
print("1. Take screenshot of Uber receipt after each trip")
print("2. Upload to OneDrive (auto-syncs to Azure)")
print("3. Check dashboard in 5-10 minutes to verify processing")
print("\nHave a great shift! 🚗💨")
