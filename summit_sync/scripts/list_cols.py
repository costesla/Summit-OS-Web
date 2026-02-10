import sys
import os
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.database import DatabaseClient

load_dotenv()
db = DatabaseClient()

def list_columns():
    query = "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'Trips'"
    results = db.execute_query_with_results(query)
    for r in results:
        print(r['COLUMN_NAME'])

if __name__ == "__main__":
    list_columns()
