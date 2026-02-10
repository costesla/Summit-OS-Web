import logging
import os
import sys
import json

# Add parent dir to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.database import DatabaseClient
from dotenv import load_dotenv

def inspect_full_schema():
    load_dotenv()
    db = DatabaseClient()
    
    print("--- Current Schema Information ---")
    try:
        # Get columns for Trips table
        query = """
        SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH 
        FROM INFORMATION_SCHEMA.COLUMNS 
        WHERE TABLE_NAME = 'Trips'
        """
        results = db.execute_query_with_results(query)
        
        if results:
            print(json.dumps(results, indent=4, default=str))
        else:
            print("Could not retrieve schema.")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    inspect_full_schema()
