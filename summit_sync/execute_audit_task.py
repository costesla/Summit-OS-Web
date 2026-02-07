
import os
import sys
import struct
import pyodbc
import requests
import json
import logging
import subprocess
from azure.identity import DefaultAzureCredential

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def run_cli_command(command):
    try:
        result = subprocess.run(command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        logging.error(f"CLI Command Failed: {e.stderr}")
        return None

def get_keyvault_secret(vault_name, secret_name):
    logging.info(f"Fetching secret '{secret_name}' from KeyVault '{vault_name}'...")
    cmd = f"az keyvault secret show --vault-name {vault_name} --name {secret_name} --query value -o tsv"
    return run_cli_command(cmd)

def check_environment():
    logging.info("--- Environment Check ---")
    
    # 1. Python Architecture
    bits = struct.calcsize("P") * 8
    logging.info(f"Python Version: {sys.version}")
    logging.info(f"Architecture: {bits}-bit")
    
    # 2. ODBC Drivers
    drivers = [d for d in pyodbc.drivers()]
    logging.info(f"ODBC Drivers Found: {drivers}")
    
    driver_name = None
    if "ODBC Driver 18 for SQL Server" in drivers:
        driver_name = "ODBC Driver 18 for SQL Server"
        logging.info("PASS: ODBC Driver 18 found.")
    elif "ODBC Driver 17 for SQL Server" in drivers:
        driver_name = "ODBC Driver 17 for SQL Server"
        logging.warning("WARN: ODBC Driver 18 not found (Using 17).")
    elif "SQL Server" in drivers:
        driver_name = "SQL Server"
        logging.warning("WARN: Only legacy SQL Server driver found. AAD Auth may fail.")
    else:
        logging.error("FAIL: No suitable SQL Driver found.")
        
    return driver_name

def check_sql(driver_name):
    logging.info("\n--- Azure SQL Check ---")
    
    # Hardcoded Server/DB as found in settings
    server = "summitsqlus23436.database.windows.net"
    database = "SummitMediaDB"
    
    # Construct Connection String for AAD Default
    # Note: Legacy "SQL Server" driver doesn't support Authentication=ActiveDirectoryDefault keyword usually.
    # We will try the token method if using Driver 17/18.
    
    logging.info(f"Target: {server}/{database}")
    
    conn = None
    try:
        if "ODBC Driver" in driver_name:
            logging.info("Attempting Managed Identity (Token) connection...")
            credential = DefaultAzureCredential()
            token = credential.get_token("https://database.windows.net/.default")
            
            token_bytes = token.token.encode("UTF-16-LE")
            token_struct = struct.pack(f"<I{len(token_bytes)}s", len(token_bytes), token_bytes)
            SQL_COPT_SS_ACCESS_TOKEN = 1254
            
            conn_str = f"Driver={{{driver_name}}};Server={server};Database={database};Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
            conn = pyodbc.connect(conn_str, attrs_before={SQL_COPT_SS_ACCESS_TOKEN: token_struct})
        else:
            # Fallback for legacy driver (Likely requires UID/PWD which we don't have, or Integrated Security if on domain)
            logging.info("Attempting Integrated Security/Basic connection (Legacy Driver)...")
            conn_str = f"Driver={{{driver_name}}};Server={server};Database={database};Trusted_Connection=yes;"
            conn = pyodbc.connect(conn_str)

        cursor = conn.cursor()
        
        # Check Tables/Views
        required_objects = ["v_DailyKPIs", "Trips", "WeatherLog", "Compliance"]
        
        cursor.execute("SELECT name, type_desc FROM sys.objects WHERE name IN ('v_DailyKPIs', 'Trips', 'WeatherLog', 'Compliance')")
        found_objects = {row.name: row.type_desc for row in cursor.fetchall()}
        
        for obj in required_objects:
            if obj in found_objects:
                logging.info(f"PASS: Found object '{obj}' ({found_objects[obj]})")
                if obj == "Compliance":
                    cursor.execute("SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'Compliance'")
                    cols = cursor.fetchall()
                    logging.info(f"   -> Compliance Columns: {[c.COLUMN_NAME for c in cols]}")
            else:
                 logging.error(f"FAIL: Missing object '{obj}'")
                 
        conn.close()
        return True
        
    except Exception as e:
        logging.error(f"FAIL: SQL Connection Error: {str(e)}")
        return False

def check_graph():
    logging.info("\n--- Microsoft Graph Check ---")
    
    # Values from summitos-api-settings.json
    tenant_id = "1cd94367-e5ad-4827-90a9-cc4c6124a340"
    client_id = "a7d212ac-dd2b-4910-a62a-b623a8ac250c"
    
    client_secret = get_keyvault_secret("kv-summitos-prod", "OAuthClientSecret")
    
    if not client_secret:
        logging.error("FAIL: Could not retrieve Client Secret from KeyVault.")
        return False

    # Get Token
    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    scope = "https://graph.microsoft.com/.default"
    
    payload = {
        'client_id': client_id,
        'client_secret': client_secret,
        'scope': scope,
        'grant_type': 'client_credentials'
    }
    
    try:
        resp = requests.post(token_url, data=payload)
        resp.raise_for_status()
        token_data = resp.json()
        access_token = token_data.get('access_token')
        logging.info("PASS: Graph Token Acquired")
        
        headers = {'Authorization': f'Bearer {access_token}'}
        user_resp = requests.get("https://graph.microsoft.com/v1.0/users?$top=1", headers=headers)
        if user_resp.status_code == 200:
             logging.info("PASS: Graph API Read Access (Users)")
        else:
             logging.warning(f"WARN: Graph API User Read Failed: {user_resp.status_code}")

        return True
        
    except Exception as e:
         logging.error(f"FAIL: Graph Auth Failed: {e}")
         return False

if __name__ == "__main__":
    logging.info("Starting Mission Control Audit (Advanced Mode)...")
    
    driver_name = check_environment()
    
    sql_ok = False
    if driver_name:
        sql_ok = check_sql(driver_name)
    
    graph_ok = check_graph()
    
    logging.info(f"\nAudit Complete.")
    if sql_ok and graph_ok:
        logging.info("VERDICT: READY TO BUILD")
    else:
        logging.info("VERDICT: ACTION REQUIRED")
