import logging
from datetime import datetime
from .banking import BankingClient
from .semantic_ingestion import SemanticIngestionService
from .database import DatabaseClient

class BankingSyncService:
    def __init__(self):
        self.banking = BankingClient()
        self.semantic = SemanticIngestionService()
        self.db = DatabaseClient()

    def sync_recent(self, count=50, since_date=None):
        """
        Pulls latest transactions for ALL connected accounts and vectorizes them for semantic search.
        Filters for 'since_date' (defaults to today) as requested.
        """
        logs = []
        try:
            target_date = since_date or datetime.now().strftime('%Y-%m-%d')
            logs.append(f"START: Banking Sync (Since: {target_date})")
            
            # 1. Fetch all accounts authorized by Teller
            accounts = self.banking.get_accounts()
            if not accounts:
                logs.append("WARN: No accounts found from Teller API.")
                return {"success": False, "error": "No accounts found", "logs": logs}

            logs.append(f"INFO: Found {len(accounts)} accounts.")
            synced_count = 0
            total_tx = 0
            
            # 2. Iterate through each account and get their transactions
            for acc in accounts:
                acc_id = acc.get('id')
                acc_name = acc.get('name', 'Unknown Account')
                
                logs.append(f"SYNC: Fetching transactions for '{acc_name}'...")
                transactions = self.banking.get_transactions(account_id=acc_id, count=count)
                total_tx += len(transactions)
                
                acc_synced = 0
                for tx in transactions:
                    # Filter for target date moving forward
                    tx_date = tx.get('date')
                    if tx_date and tx_date < target_date:
                        continue
                        
                    # 1. Semantic Vectorization
                    success = self.semantic.ingest_teller_transaction(tx)
                    if success:
                        synced_count += 1
                        acc_synced += 1
                    
                    # 2. Database Persistence (for Dashboard)
                    try:
                        amount = float(tx.get('amount', 0))
                        if amount < 0: # It's an expense
                            expense_data = {
                                "id": tx.get('id'),
                                "category": tx.get('category') or tx.get('details', {}).get('category', 'General'),
                                "amount": abs(amount),
                                "note": tx.get('description'),
                                "timestamp": tx.get('date')
                            }
                            self.db.save_manual_expense(expense_data)
                    except Exception as de:
                        logging.error(f"Failed to save banking expense to SQL: {de}")
                
                logs.append(f"INFO: Processed {acc_synced} transactions from '{acc_name}'.")
            
            logs.append(f"DONE: Banking Sync complete ({synced_count} total vectorized).")
            return {
                "success": True,
                "transactions_processed": total_tx,
                "transactions_vectorized": synced_count,
                "accounts_synced": len(accounts),
                "logs": logs
            }
        except Exception as e:
            logs.append(f"ERROR: {str(e)}")
            logging.error(f"Banking Sync Error: {e}")
            return {"success": False, "error": str(e), "logs": logs}
