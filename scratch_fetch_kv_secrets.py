import os
import sys
import json
from dotenv import load_dotenv

# Ensure root backend dir is in PYTHONPATH
script_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.join(os.getcwd(), 'backend')
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# Set KEYVAULT_URL to the production vault URL
os.environ["KEYVAULT_URL"] = "https://summitos-kv.vault.azure.net/"

from services.secret_manager import SecretManager

def main():
    manager = SecretManager()
    
    print("Fetching secrets from production Azure Key Vault...")
    kv_api_key = manager.get_secret("TESSIE_API_KEY")
    kv_vin = manager.get_secret("TESSIE_VIN")
    
    local_api_key = "0mBOWenSqEI1Fv7xCmSTnKpToUQ7Xr65"
    local_vin = "5YJ3E1EA9NF288034"
    
    print("\n--- Key Comparison ---")
    if kv_api_key:
        print(f"Key Vault API Key: {kv_api_key[:6]}... (Length: {len(kv_api_key)})")
        print(f"Local .env API Key: {local_api_key[:6]}... (Length: {len(local_api_key)})")
        print("API Keys match:", kv_api_key == local_api_key)
    else:
        print("Could not retrieve TESSIE_API_KEY from Key Vault.")
        
    if kv_vin:
        print(f"Key Vault VIN: {kv_vin}")
        print(f"Local .env VIN: {local_vin}")
        print("VINs match:", kv_vin == local_vin)
    else:
        print("Could not retrieve TESSIE_VIN from Key Vault.")

if __name__ == "__main__":
    main()
