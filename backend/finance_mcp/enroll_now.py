import asyncio
import shutil
import subprocess
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

# The cloud-side BankingClient (backend/services/banking.py) reads TELLER_TOKEN
# via SecretManager, which falls back to a plain Function App setting when no
# Key Vault is configured (KEYVAULT_URL isn't set on summitos-api). Pushing the
# token here — via the `az` CLI, using your already-logged-in local Azure
# session — is what makes the cloud safety-net sync and on-demand "Sync Now"
# button actually have a token to use. Requires `az login` once beforehand.
FUNCTION_APP_NAME = "summitos-api"
RESOURCE_GROUP = "rg-summitos-prod"


def push_token_to_function_app(access_token: str) -> bool:
    # On Windows, `az` is an az.CMD shim — subprocess.run needs the resolved
    # path (shutil.which) rather than the bare command name, or it raises
    # FileNotFoundError even when `az` works fine from an interactive shell.
    az_path = shutil.which("az")
    if not az_path:
        print("az CLI not found on PATH — skipping cloud push. Run `az login` and install the Azure CLI to enable this step.")
        return False

    print(f"Pushing token to {FUNCTION_APP_NAME} Function App settings via az CLI...")
    try:
        result = subprocess.run(
            [
                az_path, "functionapp", "config", "appsettings", "set",
                "--name", FUNCTION_APP_NAME,
                "--resource-group", RESOURCE_GROUP,
                "--settings", f"TELLER_TOKEN={access_token}",
            ],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0:
            print(f"SUCCESS! TELLER_TOKEN updated on {FUNCTION_APP_NAME}.")
            return True
        print(f"Failed to update Function App setting:\n{result.stderr}")
        return False
    except FileNotFoundError:
        print("az CLI not found — skipping cloud push. Run `az login` and install the Azure CLI to enable this step.")
        return False
    except Exception as e:
        print(f"Error running az CLI: {e}")
        return False


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
            push_token_to_function_app(access_token)
        else:
            print("Error: Enrollment completed but missing required data.")

    except Exception as e:
        print(f"Enrollment failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
