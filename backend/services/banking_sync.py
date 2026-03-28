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
        Pulls latest transactions and vectorizes them for semantic search.
        Filters for 'since_date' (defaults to today) as requested.
        """
        try:
            target_date = since_date or datetime.now().strftime('%Y-%m-%d')
            logging.info(f"Starting Banking Sync (last {count} transactions, since {target_date})...")
            transactions = self.banking.get_transactions(count=count)
            
            synced_count = 0
            for tx in transactions:
                # Filter for target date moving forward
                tx_date = tx.get('date')
                if tx_date and tx_date < target_date:
                    continue
                    
                success = self.semantic.ingest_teller_transaction(tx)
                if success:
                    synced_count += 1
            
            logging.info(f"Banking Sync Complete: {synced_count} transactions vectorized.")
            return {
                "success": True,
                "transactions_processed": len(transactions),
                "transactions_vectorized": synced_count
            }
        except Exception as e:
            logging.error(f"Banking Sync Error: {e}")
            return {"success": False, "error": str(e)}
