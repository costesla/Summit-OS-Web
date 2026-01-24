
import os
import csv
import pyodbc
import json
from dotenv import load_dotenv

# Setup
load_dotenv(dotenv_path='summit_sync/.env')
conn_str = os.environ.get("SQL_CONNECTION_STRING")
export_path = r"C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\SummitOS\Exports\vSalesAudit_2026-01-16_Mismatch.csv"

def execute_task():
    try:
        if not conn_str:
            raise Exception("Missing SQL_CONNECTION_STRING")

        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()

        # EXACT SQL per instructions
        query = """
        SELECT
            TripId,
            TripDate,
            UberMiles,
            TeslaMiles,
            ABS(TeslaMiles - UberMiles) AS DifferenceMiles
        FROM vSalesAudit
        WHERE CAST(TripDate AS DATE) = '2026-01-16'
          AND ABS(TeslaMiles - UberMiles) > 0.25
        ORDER BY DifferenceMiles DESC;
        """

        cursor.execute(query)
        rows = cursor.fetchall()
        columns = [column[0] for column in cursor.description]

        # Ensure directory exists (already handled but safe to check)
        os.makedirs(os.path.dirname(export_path), exist_ok=True)

        with open(export_path, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(columns)
            for row in rows:
                writer.writerow(list(row))

        result = {
            "status": "success",
            "rowCount": len(rows),
            "filePath": export_path
        }
        print(json.dumps(result, indent=2))

    except Exception as e:
        result = {
            "status": "error",
            "message": str(e)
        }
        print(json.dumps(result, indent=2))
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    execute_task()
