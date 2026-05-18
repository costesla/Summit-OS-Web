"""
services/secret_manager.py
--------------------------
Azure Key Vault integration via Managed Identity (no secrets in code).
Usage: SecretManager().get_secret("MY_SECRET_NAME")

Production:  Managed Identity on the Function App → Key Vault access policy
Development: Falls back to environment variable with the same name
"""

import os
import logging
from functools import lru_cache
from typing import Optional

# Only import Azure SDK classes if available (avoids dev-env import errors)
try:
    from azure.identity import ManagedIdentityCredential, DefaultAzureCredential
    from azure.keyvault.secrets import SecretClient
    AZURE_SDK_AVAILABLE = True
except ImportError:
    AZURE_SDK_AVAILABLE = False
    logging.warning("azure-identity / azure-keyvault-secrets not installed. Key Vault disabled.")


KEYVAULT_URL = os.environ.get("KEYVAULT_URL")  # e.g. https://summitos-kv.vault.azure.net/

_kv_client: Optional["SecretClient"] = None


def _get_kv_client() -> Optional["SecretClient"]:
    """Lazily create and cache the Key Vault client."""
    global _kv_client
    if _kv_client is not None:
        return _kv_client
    if not AZURE_SDK_AVAILABLE or not KEYVAULT_URL:
        return None
    try:
        # DefaultAzureCredential tries: Managed Identity → VS Code → Azure CLI
        credential = DefaultAzureCredential()
        _kv_client = SecretClient(vault_url=KEYVAULT_URL, credential=credential)
        logging.info(f"Key Vault client initialised: {KEYVAULT_URL}")
        return _kv_client
    except Exception as e:
        logging.error(f"Failed to initialise Key Vault client: {e}")
        return None


class SecretManager:
    """
    Retrieves secrets from Azure Key Vault with env-var fallback.

    Priority:
      1. Azure Key Vault (production, via Managed Identity)
      2. Environment variable (local dev / Azure App Settings)
    """

    def get_secret(self, name: str) -> Optional[str]:
        """
        Retrieve a secret by name.

        Key Vault secret names use hyphens (e.g. SQL-CONNECTION-STRING)
        while environment variables use underscores (SQL_CONNECTION_STRING).
        This method normalises automatically.
        """
        kv_name = name.replace("_", "-")
        client = _get_kv_client()
        if client:
            try:
                secret = client.get_secret(kv_name)
                if secret.value:
                    logging.debug(f"Secret '{name}' retrieved from Key Vault.")
                    return secret.value
            except Exception as e:
                logging.warning(f"Key Vault miss for '{kv_name}': {e}. Falling back to env.")

        # Fallback: environment variable
        value = os.environ.get(name)
        if value:
            logging.debug(f"Secret '{name}' retrieved from environment.")
        else:
            logging.error(f"Secret '{name}' not found in Key Vault or environment.")
        return value

    def set_secret(self, name: str, value: str) -> bool:
        """Write/update a secret in Key Vault (e.g. rotating a Teller token)."""
        kv_name = name.replace("_", "-")
        client = _get_kv_client()
        if not client:
            logging.error("Key Vault client unavailable — cannot write secret.")
            return False
        try:
            client.set_secret(kv_name, value)
            logging.info(f"Secret '{kv_name}' updated in Key Vault.")
            return True
        except Exception as e:
            logging.error(f"Failed to write secret '{kv_name}' to Key Vault: {e}")
            return False


# ── Convenience singleton ────────────────────────────────────────────────────
_manager: Optional[SecretManager] = None

def get_secret(name: str) -> Optional[str]:
    """Module-level helper: get_secret('OPENAI_API_KEY')"""
    global _manager
    if _manager is None:
        _manager = SecretManager()
    return _manager.get_secret(name)
