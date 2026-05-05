import asyncio
import sys
import os
from pathlib import Path

# Path Setup
BACKEND = r"C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\COS Tesla - Website\Summit-OS-Web-master\backend"
FINANCE_MCP = os.path.join(BACKEND, "finance_mcp")
if os.path.join(FINANCE_MCP, "src") not in sys.path:
    sys.path.insert(0, os.path.join(FINANCE_MCP, "src"))

from personal_finance_mcp.config import Config
from personal_finance_mcp.db import Database
from personal_finance_mcp.enroll.handler import run_enrollment

async def main():
    config = Config()
    config.validate_teller()
    db = Database(config.db_path)
    
    print(f"Starting enrollment server on port {config.enroll_port}...")
    print(f"Waiting for you to connect your account at: http://localhost:{config.enroll_port}")
    print("(This script will wait until you finish in your browser)")
    
    try:
        enrollment_data = await run_enrollment(
            config.teller_app_id, config.enroll_port
        )
        
        access_token = enrollment_data.get("accessToken")
        enrollment = enrollment_data.get("enrollment", {})
        institution = enrollment_data.get("institution", {})
        
        if access_token and enrollment.get("id"):
            db.save_enrollment(
                enrollment_id=enrollment["id"],
                access_token=access_token,
                institution=institution.get("name", "Unknown"),
            )
            print("SUCCESS! Account connected and saved to database.")
        else:
            print("Error: Enrollment completed but missing required data.")
            
    except Exception as e:
        print(f"Enrollment failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
