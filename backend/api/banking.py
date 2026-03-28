import logging
import json
import azure.functions as func
import os
import datetime
from services.banking import BankingClient

bp = func.Blueprint()

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization, x-functions-key"
}

def copilot_response(payload):
    response_body = {"success": True}
    if isinstance(payload, dict):
        response_body.update(payload)
    return func.HttpResponse(
        json.dumps(response_body),
        mimetype="application/json",
        headers=CORS_HEADERS
    )

@bp.route(route="copilot/banking/accounts", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def copilot_banking_accounts(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS": return func.HttpResponse(status_code=204, headers=CORS_HEADERS)
    
    try:
        banking = BankingClient()
        accounts = banking.get_accounts()
        
        # Simple formatting for Copilot
        formatted = []
        for acc in accounts:
            formatted.append({
                "account_id": acc.get("id"),
                "name": acc.get("name"),
                "type": acc.get("type"),
                "subtype": acc.get("subtype"),
                "currency": acc.get("currency_code"),
                "institution": acc.get("institution", {}).get("name")
            })
            
        return copilot_response({"accounts": formatted})
    except Exception as e:
        logging.error(f"Banking API Error: {e}")
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500)

@bp.route(route="copilot/banking/transactions", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def copilot_banking_transactions(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS": return func.HttpResponse(status_code=204, headers=CORS_HEADERS)
    
    try:
        account_id = req.params.get("account_id")
        count = int(req.params.get("limit", 20))
        
        banking = BankingClient()
        txs = banking.get_transactions(account_id=account_id, count=count)
        
        # Simple formatting for Copilot
        formatted = []
        for t in txs:
            formatted.append({
                "transaction_id": t.get("id"),
                "date": t.get("date"),
                "description": t.get("description"),
                "amount": float(t.get("amount") or 0),
                "type": t.get("type"),
                "status": t.get("status"),
                "category": t.get("details", {}).get("category")
            })
            
        return copilot_response({"count": len(formatted), "transactions": formatted})
    except Exception as e:
        logging.error(f"Banking API Error: {e}")
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500)
