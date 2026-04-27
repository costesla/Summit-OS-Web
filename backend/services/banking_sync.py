import logging
from datetime import datetime
from .banking import BankingClient
from .semantic_ingestion import SemanticIngestionService

class BankingSyncService:
    def __init__(self):
        self.banking = BankingClient()
        self.semantic = SemanticIngestionService()

    def sync_recent(self, count=50, since_date=None):
        """
        Pulls latest transactions for ALL connected accounts and vectorizes them for semantic search.
        Filters for 'since_date' (defaults to today) as requested.
        """
        try:
            target_date = since_date or datetime.now().strftime('%Y-%m-%d')
            logging.info(f"Starting Banking Sync (last {count} transactions, since {target_date})...")
            
            # 1. Fetch all accounts authorized by Teller
            accounts = self.banking.get_accounts()
            if not accounts:
                logging.warning("No accounts found from Teller API.")
                return {"success": False, "error": "No accounts found"}

            synced_count = 0
            total_tx = 0
            
            # 2. Iterate through each account and get their transactions
            for acc in accounts:
                acc_id = acc.get('id')
                acc_name = acc.get('name', 'Unknown Account')
                
                logging.info(f"Fetching for Account: {acc_name} ({acc_id})")
                transactions = self.banking.get_transactions(account_id=acc_id, count=count)
                total_tx += len(transactions)
                
                for tx in transactions:
                    # Filter for target date moving forward
                    tx_date = tx.get('date')
                    if tx_date and tx_date < target_date:
                        continue
                        
                    success = self.semantic.ingest_teller_transaction(tx)
                    if success:
                        synced_count += 1
            
            logging.info(f"Banking Sync Complete: {synced_count} transactions vectorized (from {len(accounts)} accounts).")
            return {
                "success": True,
                "transactions_processed": total_tx,
                "transactions_vectorized": synced_count,
                "accounts_synced": len(accounts)
            }
        except Exception as e:
            logging.error(f"Banking Sync Error: {e}")
            return {"success": False, "error": str(e)}
