import json
import os

def main():
    try:
        with open('local.settings.json', 'r') as f:
            settings = json.load(f)
            for k, v in settings.get('Values', {}).items():
                os.environ[k] = v

        from services.database import DatabaseClient
        db = DatabaseClient()
        conn = db.get_connection()
        cur = conn.cursor()
        
        print("--- Table List ---")
        cur.execute("SELECT SCHEMA_NAME(schema_id) AS SchemaName, name AS TableName FROM sys.tables ORDER BY SchemaName, TableName")
        tables = cur.fetchall()
        for t in tables:
            print(f"- {t[0]}.{t[1]}")
            
        print("\n--- Views List ---")
        cur.execute("SELECT SCHEMA_NAME(schema_id) AS SchemaName, name AS ViewName FROM sys.views ORDER BY SchemaName, ViewName")
        views = cur.fetchall()
        for v in views:
            print(f"- {v[0]}.{v[1]}")
            
        # Let's inspect the columns of Rides.Rides
        print("\n--- Rides.Rides Columns ---")
        cur.execute("SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = 'Rides' AND TABLE_NAME = 'Rides'")
        for col in cur.fetchall():
            print(f"- {col[0]} ({col[1]})")

        cur.close()
        conn.close()

    except Exception as e:
        print("Error:", e)

if __name__ == '__main__':
    main()
