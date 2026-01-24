
import os
import csv
import pyodbc
import argparse
from datetime import datetime
from dotenv import load_dotenv

# Setup paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(dotenv_path=os.path.join(BASE_DIR, ".env"))

# --- Configuration ---
ONEDRIVE_PATH = r"C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\SummitOS\Daily_Reports"

def export_sales(target_date=None, export_all=False):
    conn_str = os.environ.get("SQL_CONNECTION_STRING")
    if not conn_str:
        print("Error: SQL_CONNECTION_STRING not found in .env")
        return

    try:
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        
        # Get list of dates to process
        dates_to_process = []
        if export_all:
            cursor.execute("SELECT DISTINCT CAST(Timestamp_Offer AS DATE) FROM Trips WHERE Timestamp_Offer IS NOT NULL")
            for row in cursor.fetchall():
                d = row[0]
                if isinstance(d, str):
                    d = datetime.strptime(d, "%Y-%m-%d").date()
                dates_to_process.append(d.strftime("%Y%m%d"))
        elif target_date:
            dates_to_process = [target_date]
        else:
            print("Target date or --all required.")
            return

        os.makedirs(ONEDRIVE_PATH, exist_ok=True)
        
        for date_str in dates_to_process:
            dt = datetime.strptime(date_str, "%Y%m%d")
            sql_date = dt.strftime("%Y-%m-%d")
            
            # Query using the AI-indexed View for consistency with Copilot
            query = """
            SELECT * FROM vSalesAudit 
            WHERE CAST(TripDate AS DATE) = ?
            ORDER BY TripTime ASC
            """
            
            cursor.execute(query, (sql_date,))
            rows = cursor.fetchall()
            if not rows:
                print(f"Skipping {sql_date} (No records)")
                continue

            columns = [column[0] for column in cursor.description]
            filename = f"Sales_Report_{date_str}.csv"
            full_path = os.path.join(ONEDRIVE_PATH, filename)
            
            with open(full_path, mode='w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(columns)
                for row in rows:
                    writer.writerow(list(row))
                    
            print(f"✅ Exported: {filename} ({len(rows)} records)")

    except Exception as e:
        print(f"Export failed: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export daily sales to AI Data Lake (OneDrive).")
    parser.add_argument("--date", type=str, help="Date to export (YYYYMMDD)")
    parser.add_argument("--all", action="store_true", help="Export all historical days")
    args = parser.parse_args()
    
    export_sales(target_date=args.date, export_all=args.all)
