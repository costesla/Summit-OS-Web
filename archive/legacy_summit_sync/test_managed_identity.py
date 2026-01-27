import os
import logging
from lib.database import DatabaseClient

# Configure basic logging
logging.basicConfig(level=logging.INFO)

def test_managed_identity():
    print("🚀 Testing Managed Identity SQL Connection...")
    
    # Check Env Vars
    server = os.environ.get("SQL_SERVER_NAME")
    db_name = os.environ.get("SQL_DATABASE_NAME")
    print(f"Server: {server}")
    print(f"Database: {db_name}")
    
    if not server or not db_name:
        print("❌ ERROR: SQL_SERVER_NAME or SQL_DATABASE_NAME not set correctly.")
        return

    db = DatabaseClient()
    conn = db.get_connection()
    
    if conn:
        print("✅ Connection established!")
        
        cursor = conn.cursor()
        
        # 1. Test Read Access
        try:
            print("📖 Testing READ access...")
            cursor.execute("SELECT TOP 1 TripID, TripType FROM Trips ORDER BY CreatedAt DESC")
            row = cursor.fetchone()
            print(f"✅ Success! Read trip: {row[0] if row else 'No trips found'}")
        except Exception as e:
            print(f"❌ Read failed: {e}")
            
        # 2. Test Write Protection
        try:
            print("🔒 Testing WRITE protection (Expect Failure)...")
            cursor.execute("INSERT INTO Trips (TripID) VALUES ('TEST_WRITE_PROTECT')")
            print("❌ ERROR: Write succeeded! This IS A SECURITY RISK.")
        except Exception as e:
            if "permission was denied" in str(e) or "read-only" in str(e):
                print(f"✅ Success! Write denied as expected: {e}")
            else:
                print(f"⚠️ Write failed, but maybe not due to permissions: {e}")
                
        conn.close()
    else:
        print("❌ Connection failed completely.")

if __name__ == "__main__":
    test_managed_identity()
