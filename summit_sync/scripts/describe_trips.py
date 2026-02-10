
import os
import sys
from dotenv import load_dotenv
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from lib.database import DatabaseClient

load_dotenv()
db = DatabaseClient()

def describe():
    sql = "SELECT COLUMN_NAME, IS_NULLABLE, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'Trips'"
    res = db.execute_query_with_results(sql)
    for r in res:
        print(f"{r['COLUMN_NAME']:<25} | {r['IS_NULLABLE']:<10} | {r['DATA_TYPE']}")

if __name__ == "__main__":
    describe()
