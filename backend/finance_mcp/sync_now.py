import asyncio
import sys
import os
import json
from pathlib import Path

# Path Setup
BACKEND = r"C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\COS Tesla - Website\Summit-OS-Web-master\backend"
FINANCE_MCP = os.path.join(BACKEND, "finance_mcp")
if os.path.join(FINANCE_MCP, "src") not in sys.path:
    sys.path.insert(0, os.path.join(FINANCE_MCP, "src"))

from personal_finance_mcp.config import Config
from personal_finance_mcp.db import Database
from personal_finance_mcp.server import _handle_sync

async def main():
    config = Config()
    config.validate_teller()
    db = Database(config.db_path)
    
    print("Syncing bank data...")
    try:
        result = await _handle_sync(config, db)
        print(f"Sync Result: {json.dumps(result, indent=2)}")
    except Exception as e:
        print(f"Sync failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
