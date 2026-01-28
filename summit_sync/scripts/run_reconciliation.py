import os
import sys
import logging
from dotenv import load_dotenv

# Add parent dir to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.reconciliation import ReconciliationEngine

# Setup
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
load_dotenv(dotenv_path=env_path)
logging.basicConfig(level=logging.INFO)

# Verification Patch for local testing
conn_str = os.environ.get("SQL_CONNECTION_STRING", "")
if "Driver=" not in conn_str:
    print("Adding Legacy SQL Server Driver to connection string...")
    # SQL Server (Legacy) - Might fail with AD Auth
    os.environ["SQL_CONNECTION_STRING"] = "Driver={SQL Server};" + conn_str

def run():
    print("Starting Local Reconciliation Test...")
    engine = ReconciliationEngine()
    engine.reconcile_private_trips(days_back=30) # Look back 30 days for testing
    print("Test Complete")

if __name__ == "__main__":
    run()
