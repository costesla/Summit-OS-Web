
import subprocess
import json

def check_settings():
    try:
        raw = subprocess.check_output(["az", "functionapp", "config", "appsettings", "list", "-g", "rg-summitos-us2", "-n", "summitsyncfuncus23436"], stderr=subprocess.STDOUT)
        settings = json.loads(raw)
        names = {s['name']: s['value'] for s in settings}
        
        required = [
            "AZURE_VISION_KEY", "AZURE_VISION_ENDPOINT", 
            "TESSIE_API_KEY", "TESSIE_VIN",
            "SQL_CONNECTION_STRING", "AZUREWEBJOBSSTORAGE"
        ]
        
        print("--- Azure App Settings Diagnostic ---")
        for req in required:
            status = "PRESENT" if req in names else "MISSING"
            val = names.get(req, "N/A")
            if val and len(val) > 4:
                val = val[:4] + "..."
            print(f"{req:<25}: {status} ({val})")
            
        # Check ODBC driver in SQL string
        sql_str = names.get("SQL_CONNECTION_STRING", "")
        if "Driver=" in sql_str:
            print(f"\nSQL Driver in use: {sql_str.split('Driver=')[1].split(';')[0]}")
        
    except Exception as e:
        print(f"Error checking settings: {e}")

if __name__ == "__main__":
    check_settings()
