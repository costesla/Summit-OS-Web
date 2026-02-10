import os
from dotenv import load_dotenv

def verify_connection():
    load_dotenv()
    conn_str = os.environ.get("SQL_CONNECTION_STRING")
    
    if not conn_str:
        print("Error: SQL_CONNECTION_STRING not found.")
        return

    # Parse simplistic connection string (Driver={...};Server=...;Database=...)
    parts = conn_str.split(';')
    server = "Unknown"
    database = "Unknown"
    
    for part in parts:
        if part.lower().startswith('server='):
            server = part.split('=')[1]
        if part.lower().startswith('database='):
            database = part.split('=')[1]
            
    print(f"Server:   {server}")
    print(f"Database: {database}")

    if "summitsqlus23436" in server and "SummitMediaDB" in database:
        print("\nSUCCESS: Connection points to the correct Azure SQL Database.")
    else:
        print("\nWARNING: Connection does not match expected SummitMediaDB on summitsqlus23436.")

if __name__ == "__main__":
    verify_connection()
