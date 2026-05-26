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
        
        cur.execute("SELECT DISTINCT ValidationStatus, COUNT(*) FROM Rides.Rides GROUP BY ValidationStatus")
        print("Distinct ValidationStatus in Rides.Rides:")
        for r in cur.fetchall():
            print(r)
            
        cur.close()
        conn.close()

    except Exception as e:
        print("Error:", e)

if __name__ == '__main__':
    main()
