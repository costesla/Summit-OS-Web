import os
import logging
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

class SecretManager:
    """
    Unified Secret Retrieval Service.
    Priority: os.environ -> Azure Key Vault (kv-summitos-prod)
    """
    def __init__(self):
        self.vault_url = "https://kv-summitos-prod.vault.azure.net/"
        self._credential = None
        self._client = None
        self._cache = {}

    @property
    def client(self):
        if not self._client:
            try:
                if not self._credential:
                    self._credential = DefaultAzureCredential()
                self._client = SecretClient(vault_url=self.vault_url, credential=self._credential)
            except Exception as e:
                logging.debug(f"Failed to initialize Key Vault client: {e}")
        return self._client

    def get_secret(self, name: str, default: str = None) -> str:
        # 1. Check local environment first
        val = os.environ.get(name)
        if val and not val.startswith("@Microsoft.KeyVault") and "your_" not in val:
            return val

        # 2. Check Cache
        if name in self._cache:
            return self._cache[name]

        # 3. Check Azure Key Vault
        if self.client:
            try:
                # Key Vault secret names are slightly different (case-insensitive usually, but often CamelCase)
                # We map common ENV_VARS to Key Vault Secret Names
                kv_name = self._map_to_kv_name(name)
                secret = self.client.get_secret(kv_name)
                self._cache[name] = secret.value
                return secret.value
            except Exception as e:
                logging.debug(f"Secret '{name}' (KV: {self._map_to_kv_name(name)}) not found in Key Vault or access denied: {e}")

        return default

    def set_secret(self, name: str, value: str) -> bool:
        """Sets a secret in Azure Key Vault."""
        if not self.client:
            logging.error(f"Cannot set secret '{name}': Key Vault client not initialized.")
            return False

        try:
            kv_name = self._map_to_kv_name(name)
            self.client.set_secret(kv_name, value)
            self._cache[name] = value  # Update cache
            logging.info(f"Successfully updated secret '{kv_name}' in Key Vault.")
            return True
        except Exception as e:
            logging.error(f"Failed to set secret '{name}' in Key Vault: {e}")
            return False

    def _map_to_kv_name(self, env_name: str) -> str:
        """Maps ENV_VAR_NAME to SecretName used in kv-summitos-prod."""
        mapping = {
            "TESSIE_API_KEY": "TessieApiKey",
            "TESSIE_VIN": "TessieVIN",
            "TELLER_CERT": "TellerCert",
            "TELLER_KEY": "TellerKey",
            "TELLER_TOKEN": "TellerToken",
            "TELLER_ACCOUNT_ID": "TellerAccountID",
            "OPENAI_API_KEY": "OpenAIApiKey",
            "SQL_CONNECTION_STRING": "SqlConnectionProd"
        }
        return mapping.get(env_name, env_name.replace("_", ""))
