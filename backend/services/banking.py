import os
import requests
import json
import logging
import tempfile
from datetime import datetime

class BankingClient:
    def __init__(self):
        """
        Teller Client that handles Mutual TLS (mTLS) for bank integration.
        Requires TELLER_CERT, TELLER_KEY, and TELLER_TOKEN (Access Token).
        """
        self.base_url = "https://api.teller.io"
        self.cert_str = os.environ.get("TELLER_CERT")
        self.key_str = os.environ.get("TELLER_KEY")
        self.access_token = os.environ.get("TELLER_TOKEN")
        self.default_account_id = os.environ.get("TELLER_ACCOUNT_ID")
        
        if not self.cert_str or not self.key_str:
            logging.warning("Teller mTLS credentials (TELLER_CERT/TELLER_KEY) are missing. Banking will not function.")

    def _get_mtls_session(self):
        """
        Requests uses file-based certificates for mTLS. 
        We write the certs from env-vars to temp files on the fly.
        """
        session = requests.Session()
        cert_path = None
        key_path = None

        if self.cert_str and self.key_str:
            try:
                # Create secure temporary files
                cert_fd, cert_path = tempfile.mkstemp(suffix=".crt")
                key_fd, key_path = tempfile.mkstemp(suffix=".key")
                
                with os.fdopen(cert_fd, 'w') as f:
                    f.write(self.cert_str.replace("\\n", "\n"))
                with os.fdopen(key_fd, 'w') as f:
                    f.write(self.key_str.replace("\\n", "\n"))
                
                session.cert = (cert_path, key_path)
                # Teller uses the access token as the username in Basic Auth
                if self.access_token:
                    session.auth = (self.access_token, "")
                    
            except Exception as e:
                logging.error(f"Failed to initialize mTLS session: {e}")
                
        return session, cert_path, key_path

    def get_accounts(self):
        """Fetches all connected bank accounts."""
        session, c_path, k_path = self._get_mtls_session()
        try:
            logging.info("Fetching Teller accounts...")
            resp = session.get(f"{self.base_url}/accounts")
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logging.error(f"Teller API Error (get_accounts): {e}")
            return []
        finally:
            if c_path and os.path.exists(c_path): os.remove(c_path)
            if k_path and os.path.exists(k_path): os.remove(k_path)

    def get_transactions(self, account_id=None, count=50):
        """Fetches transactions for a specific account."""
        acc_id = account_id or self.default_account_id
        if not acc_id:
            logging.error("No account_id provided for Teller transactions.")
            return []

        session, c_path, k_path = self._get_mtls_session()
        try:
            logging.info(f"Fetching transactions for account: {acc_id}")
            params = {"count": count}
            resp = session.get(f"{self.base_url}/accounts/{acc_id}/transactions", params=params)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logging.error(f"Teller API Error (get_transactions): {e}")
            return []
        finally:
            if c_path and os.path.exists(c_path): os.remove(c_path)
            if k_path and os.path.exists(k_path): os.remove(k_path)
