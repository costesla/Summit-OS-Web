
import os
import pyodbc
from dotenv import load_dotenv
import textwrap

# Setup
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
load_dotenv(dotenv_path=env_path)
conn_str = os.environ.get("SQL_CONNECTION_STRING")

def view_data():
    if not conn_str:
        print("SQL_CONNECTION_STRING not found.")
        return

    try:
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        
        # Query New Schema with Validation Columns
        query = """
        SELECT TOP 20 
            TripID, TripType, Platform_Emoji, 
            Uber_Distance, Tessie_Distance,
            Rider_Payment, Earnings_Driver, 
            CreatedAt 
        FROM Trips 
        ORDER BY CreatedAt DESC
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        
        print("\n--- Summit Sync Cross-Validation (Uber vs Tesla) ---\n")
        print(f"{'TripID':<15} | {'Type':<8} | {'Uber':<6} | {'Tesla':<6} | {'Var':<5} | {'Pay':<10} | {'Earn':<10}")
        print("-" * 95)
        
        if not rows:
            print("No records found.")
            
        for row in rows:
            tid = str(row.TripID)[:15]
            ttype = str(row.TripType)
            emoji = row.Platform_Emoji if row.Platform_Emoji else " "
            
            u_dist = row.Uber_Distance if row.Uber_Distance is not None else 0
            t_dist = row.Tessie_Distance if row.Tessie_Distance is not None else 0
            
            # Formatting
            u_str = f"{u_dist:>5.1f}" if ttype == 'Uber' else " N/A "
            t_str = f"{t_dist:>5.1f}" if t_dist > 0 else " --- "
            
            variance = t_dist - u_dist if ttype == 'Uber' and t_dist > 0 else 0
            v_str = f"{variance:>+5.1f}" if ttype == 'Uber' and t_dist > 0 else " --- "
            
            pay = f"${row.Rider_Payment:.2f}" if row.Rider_Payment else "$0.00"
            earn = f"${row.Earnings_Driver:.2f}" if row.Earnings_Driver else "$0.00"
            
            try:
                print(f"{tid:<15} | {ttype:<8} | {u_str:<6} | {t_str:<6} | {v_str:<5} | {pay:<10} | {earn:<10} {emoji}")
            except UnicodeEncodeError:
                print(f"{tid:<15} | {ttype:<8} | {u_str:<6} | {t_str:<6} | {v_str:<5} | {pay:<10} | {earn:<10}")
            
        print("\n-------------------------------------------")

    except Exception as e:
        print(f"Error querying DB: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    view_data()
