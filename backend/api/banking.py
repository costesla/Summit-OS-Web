import logging
import json
import azure.functions as func
import os
import datetime
from services.banking import BankingClient
from services.banking_sync import BankingSyncService
from services.auth_guard import require_function_key, cors_headers

bp = func.Blueprint()


def _cors(req: func.HttpRequest) -> dict:
    return cors_headers(req)


def copilot_response(payload, req: func.HttpRequest):
    response_body = {"success": True}
    if isinstance(payload, dict):
        response_body.update(payload)
    return func.HttpResponse(
        json.dumps(response_body),
        mimetype="application/json",
        headers=_cors(req)
    )


# ── /copilot/banking/accounts ────────────────────────────────────────────────
# SECURED: requires Azure Function key

@bp.route(route="copilot/banking/accounts", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def copilot_banking_accounts(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_cors(req))

    guard = require_function_key(req)
    if guard:
        return guard

    try:
        banking = BankingClient()
        accounts = banking.get_accounts()

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

        return copilot_response({"accounts": formatted}, req)
    except Exception as e:
        logging.error(f"Banking accounts error: {e}")
        return func.HttpResponse(
            json.dumps({"error": "Internal server error"}),
            status_code=500,
            headers=_cors(req)
        )


# ── /copilot/banking/transactions ────────────────────────────────────────────
# SECURED: requires Azure Function key

@bp.route(route="copilot/banking/transactions", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def copilot_banking_transactions(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_cors(req))

    guard = require_function_key(req)
    if guard:
        return guard

    try:
        account_id = req.params.get("account_id")
        count = int(req.params.get("limit", 20))

        banking = BankingClient()
        txs = banking.get_transactions(account_id=account_id, count=count)

        formatted = []
        for t in txs:
            formatted.append({
                "transaction_id": t.get("id"),
                "date": t.get("date"),
                "description": t.get("description"),
                "counterparty": t.get("details", {}).get("counterparty", {}).get("name") or t.get("description"),
                "amount": float(t.get("amount") or 0),
                "type": t.get("type"),
                "status": t.get("status"),
                "category": t.get("details", {}).get("category")
            })

        return copilot_response({"count": len(formatted), "transactions": formatted}, req)
    except Exception as e:
        logging.error(f"Banking transactions error: {e}")
        return func.HttpResponse(
            json.dumps({"error": "Internal server error"}),
            status_code=500,
            headers=_cors(req)
        )


# ── /copilot/banking/sync ─────────────────────────────────────────────────────
# SECURED: requires Azure Function key

@bp.route(route="copilot/banking/sync", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def copilot_banking_sync(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_cors(req))

    guard = require_function_key(req)
    if guard:
        return guard

    try:
        count = int(req.params.get("limit", 50))
        since_date = req.params.get("since_date")
        sync_service = BankingSyncService()
        result = sync_service.sync_recent(count=count, since_date=since_date)
        return copilot_response(result, req)
    except Exception as e:
        logging.error(f"Banking sync error: {e}")
        return func.HttpResponse(
            json.dumps({"error": "Internal server error"}),
            status_code=500,
            headers=_cors(req)
        )


# ── /copilot/banking/token ────────────────────────────────────────────────────
# HIGHLY SENSITIVE: requires Azure Function key
# Writes a secret to Key Vault — must never be anonymous

@bp.route(route="copilot/banking/token", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def copilot_banking_token(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_cors(req))

    guard = require_function_key(req)
    if guard:
        return guard

    try:
        from services.secret_manager import SecretManager

        body = req.get_json()
        token = body.get("token")

        if not token:
            return func.HttpResponse(
                json.dumps({"error": "Missing token"}),
                status_code=400,
                headers=_cors(req)
            )

        sm = SecretManager()
        success = sm.set_secret("TELLER_TOKEN", token)

        if success:
            return copilot_response({"message": "Teller token updated successfully in Key Vault"}, req)
        else:
            return func.HttpResponse(
                json.dumps({"error": "Failed to update Key Vault"}),
                status_code=500,
                headers=_cors(req)
            )

    except Exception as e:
        logging.error(f"Banking token update error: {e}")
        return func.HttpResponse(
            json.dumps({"error": "Internal server error"}),
            status_code=500,
            headers=_cors(req)
        )
