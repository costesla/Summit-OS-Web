import csv
import io
import json
import logging
import datetime

import azure.functions as func

from services.auth_guard import require_function_key, cors_headers
from services.database import DatabaseClient
from services.payment_tracker import PaymentTrackerService
from services.payment_categorizer import categorize_payee

bp = func.Blueprint()


def _cors(req: func.HttpRequest) -> dict:
    return cors_headers(req)


def _json_response(payload: dict, req: func.HttpRequest, status_code: int = 200) -> func.HttpResponse:
    headers = _cors(req)
    headers["Content-Type"] = "application/json"
    return func.HttpResponse(json.dumps(payload, default=str), status_code=status_code, headers=headers)


# ── GET /financials/payments/scorecard ───────────────────────────────────────

@bp.route(route="financials/payments/scorecard", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def payments_scorecard(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_cors(req))
    guard = require_function_key(req)
    if guard:
        return guard

    try:
        date_str = req.params.get("date") or datetime.date.today().isoformat()
        tracker = PaymentTrackerService()
        return _json_response(tracker.get_scorecard(date_str), req)
    except Exception as e:
        logging.error(f"payments_scorecard error: {e}")
        return _json_response({"error": "Internal server error"}, req, 500)


# ── GET /financials/payments/luis/balance ────────────────────────────────────

@bp.route(route="financials/payments/luis/balance", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def payments_luis_balance(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_cors(req))
    guard = require_function_key(req)
    if guard:
        return guard

    try:
        db = DatabaseClient()
        limit_days = int(req.params.get("limit_days", 90))
        return _json_response(db.get_luis_balance_history(limit_days=limit_days), req)
    except Exception as e:
        logging.error(f"payments_luis_balance error: {e}")
        return _json_response({"error": "Internal server error"}, req, 500)


# ── GET /financials/payments/bills/calendar ──────────────────────────────────

@bp.route(route="financials/payments/bills/calendar", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def payments_bill_calendar(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_cors(req))
    guard = require_function_key(req)
    if guard:
        return guard

    try:
        month = req.params.get("month") or datetime.date.today().strftime("%Y-%m")
        db = DatabaseClient()
        return _json_response({"month": month, "obligations": db.get_bill_calendar(month)}, req)
    except Exception as e:
        logging.error(f"payments_bill_calendar error: {e}")
        return _json_response({"error": "Internal server error"}, req, 500)


# ── GET /financials/payments/transactions ────────────────────────────────────

def _query_transactions(req: func.HttpRequest) -> list:
    db = DatabaseClient()
    account = req.params.get("account")
    if account:
        account = account.replace("...", "").strip()
    return db.get_payments(
        account=account or None,
        category=req.params.get("category") or None,
        date_from=req.params.get("from") or None,
        date_to=req.params.get("to") or None,
        anomaly_only=(req.params.get("anomaly") or "").lower() in ("1", "true", "yes"),
        limit=int(req.params.get("limit", 500)),
    )


@bp.route(route="financials/payments/transactions", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def payments_transactions(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_cors(req))
    guard = require_function_key(req)
    if guard:
        return guard

    try:
        return _json_response({"transactions": _query_transactions(req)}, req)
    except Exception as e:
        logging.error(f"payments_transactions error: {e}")
        return _json_response({"error": "Internal server error"}, req, 500)


# ── GET /financials/payments/transactions/export ─────────────────────────────

@bp.route(route="financials/payments/transactions/export", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def payments_transactions_export(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_cors(req))
    guard = require_function_key(req)
    if guard:
        return guard

    try:
        rows = _query_transactions(req)
        buffer = io.StringIO()
        writer = csv.DictWriter(
            buffer,
            fieldnames=["date", "account", "counterparty", "amount", "direction", "category", "anomaly_flag"],
            extrasaction="ignore",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

        headers = _cors(req)
        headers["Content-Type"] = "text/csv"
        headers["Content-Disposition"] = 'attachment; filename="payments_export.csv"'
        return func.HttpResponse(buffer.getvalue(), status_code=200, headers=headers)
    except Exception as e:
        logging.error(f"payments_transactions_export error: {e}")
        return _json_response({"error": "Internal server error"}, req, 500)


# ── GET /financials/luis ──────────────────────────────────────────────────────
# Read-only summary card for the Financials module: month-scoped Good/Bad day
# counts and balance owed. Separate from /financials/payments/luis/balance
# (the older tiered running-balance system) — this one resets every month.

@bp.route(route="financials/luis", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def financials_luis_summary(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_cors(req))
    guard = require_function_key(req)
    if guard:
        return guard

    try:
        db = DatabaseClient()
        month = req.params.get("month") or datetime.date.today().strftime("%Y-%m")
        return _json_response(db.get_luis_month_summary(month), req)
    except Exception as e:
        logging.error(f"financials_luis_summary error: {e}")
        return _json_response({"error": "Internal server error"}, req, 500)


# ── GET /financials/payments/anomalies ────────────────────────────────────────

@bp.route(route="financials/payments/anomalies", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def payments_anomalies(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_cors(req))
    guard = require_function_key(req)
    if guard:
        return guard

    try:
        db = DatabaseClient()
        anomalies = db.get_open_anomalies()
        return _json_response({"count": len(anomalies), "anomalies": anomalies}, req)
    except Exception as e:
        logging.error(f"payments_anomalies error: {e}")
        return _json_response({"error": "Internal server error"}, req, 500)


# ── POST /financials/payments/sync ────────────────────────────────────────────
# On-demand Teller pull via the existing cloud-side BankingClient — used by the
# dashboard's "Sync Now" button. The local nightly job (which uses the Teller
# MCP's finance.db cache) is the primary ingestion path; this is the reachable
# on-demand equivalent since an Azure Function can't invoke a local MCP server.

@bp.route(route="financials/payments/sync", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def payments_sync(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_cors(req))
    guard = require_function_key(req)
    if guard:
        return guard

    try:
        tracker = PaymentTrackerService()
        today = datetime.date.today().isoformat()
        result = tracker.sync_day_via_banking_client(today)
        return _json_response(result, req)
    except Exception as e:
        logging.error(f"payments_sync error: {e}")
        return _json_response({"error": "Internal server error"}, req, 500)


# ── POST /financials/payments/log ─────────────────────────────────────────────

@bp.route(route="financials/payments/log", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def payments_log(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_cors(req))
    guard = require_function_key(req)
    if guard:
        return guard

    try:
        body = req.get_json()
        required = ("date", "account", "direction", "amount")
        missing = [f for f in required if not body.get(f)]
        if missing:
            return _json_response({"error": f"Missing required fields: {', '.join(missing)}"}, req, 400)

        category = body.get("category")
        subcategory = body.get("subcategory")
        anomaly_flag = bool(body.get("anomaly_flag", False))
        anomaly_reason = body.get("anomaly_reason")

        if not category:
            classification = categorize_payee(
                body.get("counterparty") or "",
                float(body["amount"]) if body["direction"] == "inbound" else -float(body["amount"]),
                body["account"],
            )
            category = classification["category"]
            subcategory = subcategory or classification["subcategory"]
            anomaly_flag = anomaly_flag or classification["anomaly_flag"]
            anomaly_reason = anomaly_reason or classification["anomaly_reason"]

        db = DatabaseClient()
        payment_id = db.save_payment({
            "date": body["date"],
            "account": body["account"],
            "direction": body["direction"],
            "counterparty": body.get("counterparty"),
            "amount": abs(float(body["amount"])),
            "category": category,
            "subcategory": subcategory,
            "recurring_flag": bool(body.get("recurring_flag", False)),
            "anomaly_flag": anomaly_flag,
            "anomaly_reason": anomaly_reason,
            "teller_transaction_id": None,
            "notes": body.get("notes"),
        })

        if not payment_id:
            return _json_response({"error": "Failed to save payment"}, req, 500)
        return _json_response({"success": True, "payment_id": payment_id}, req)
    except Exception as e:
        logging.error(f"payments_log error: {e}")
        return _json_response({"error": "Internal server error"}, req, 500)


# ── POST /financials/payments/anomaly/resolve ─────────────────────────────────

@bp.route(route="financials/payments/anomaly/resolve", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def payments_anomaly_resolve(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_cors(req))
    guard = require_function_key(req)
    if guard:
        return guard

    try:
        body = req.get_json()
        payment_id = body.get("payment_id")
        if not payment_id:
            return _json_response({"error": "Missing payment_id"}, req, 400)

        db = DatabaseClient()
        resolved = db.resolve_anomaly(payment_id, resolution_note=body.get("resolution_note"))
        if not resolved:
            return _json_response({"error": "Anomaly not found"}, req, 404)
        return _json_response({"success": True}, req)
    except Exception as e:
        logging.error(f"payments_anomaly_resolve error: {e}")
        return _json_response({"error": "Internal server error"}, req, 500)


# ── POST /financials/payments/luis/reassign ───────────────────────────────────
# Moves a Luis Canales payment to the date it actually covers (e.g. a late
# payment posted the day after a rough day) and recomputes the running
# balance chain from that point forward.

@bp.route(route="financials/payments/luis/reassign", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def payments_luis_reassign(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_cors(req))
    guard = require_function_key(req)
    if guard:
        return guard

    try:
        body = req.get_json()
        payment_id = body.get("payment_id")
        target_date = body.get("target_date")
        if not payment_id or not target_date:
            return _json_response({"error": "Missing payment_id or target_date"}, req, 400)

        tracker = PaymentTrackerService()
        result = tracker.reassign_luis_payment(payment_id, target_date)
        if not result.get("success"):
            return _json_response(result, req, 400)
        return _json_response(result, req)
    except Exception as e:
        logging.error(f"payments_luis_reassign error: {e}")
        return _json_response({"error": "Internal server error"}, req, 500)


# ═════════════════════════════════════════════════════════════════════════════
# Manual Ledger — Jackie & Luis
#
# Manual-entry-only current balances. Amounts cross the wire as STRINGS so a
# JSON float can never round a cent; the server parses them with Decimal.
# Every route requires the same function key as the rest of /financials.
# There is deliberately no delete route — entries are voided.
# ═════════════════════════════════════════════════════════════════════════════

def _actor(req: func.HttpRequest) -> str:
    """Best-effort caller identity for the audit trail (never a secret)."""
    principal = req.headers.get("x-ms-client-principal-name")
    return (principal or "dashboard")[:100]


def _correlation_id(req: func.HttpRequest) -> str | None:
    return (req.headers.get("x-correlation-id") or req.headers.get("x-request-id") or None)


def _serialize_entry(entry: dict) -> dict:
    effective = entry.get("effective_date")
    return {
        "entryId": entry.get("entry_id"),
        "personKey": entry.get("person_key"),
        "entryType": entry.get("entry_type"),
        "amount": str(entry.get("amount")),
        "effectiveDate": effective.isoformat() if hasattr(effective, "isoformat") else effective,
        "note": entry.get("note"),
        "voided": entry.get("voided_at_utc") is not None,
        "revisionNumber": entry.get("revision_number"),
    }


@bp.route(route="financials/manual-ledger", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def manual_ledger_get(req: func.HttpRequest) -> func.HttpResponse:
    """Balance + recent entries for one person, or both when `person` is omitted."""
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_cors(req))
    guard = require_function_key(req)
    if guard:
        return guard

    from services.manual_ledger import (
        ManualLedgerService, PersonKey, ValidationError, parse_as_of, parse_person_key,
    )
    try:
        service = ManualLedgerService()
        requested = req.params.get("person")
        people = [parse_person_key(requested)] if requested else [PersonKey.JACKIE, PersonKey.LUIS]

        # Optional cut-off. The dashboard renders this panel under a date-scoped
        # "BALANCE SHEET" header, so it asks for the closing balance on that day
        # rather than the running total. Absent, the response covers the whole
        # ledger exactly as before — existing callers are unaffected.
        as_of_raw = req.params.get("asOf")
        as_of = parse_as_of(as_of_raw) if as_of_raw else None

        payload = {}
        for person_key in people:
            baseline = service.get_active_baseline(person_key)
            payload[person_key] = {
                "personKey": person_key,
                "activated": baseline is not None,
                "openingBalance": str(baseline["opening_balance"]) if baseline else "0.00",
                "balance": str(service.get_balance(person_key, as_of=as_of)),
                "entries": [_serialize_entry(e)
                            for e in service.list_entries(person_key, as_of=as_of)],
            }
        return _json_response({"people": payload,
                               "asOf": as_of.isoformat() if as_of else None}, req)
    except ValidationError as ve:
        return _json_response({"error": str(ve)}, req, 400)
    except Exception as e:
        logging.error(f"manual_ledger_get error: {e}")
        return _json_response({"error": "Internal server error"}, req, 500)


@bp.route(route="financials/manual-ledger/entry", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def manual_ledger_create(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_cors(req))
    guard = require_function_key(req)
    if guard:
        return guard

    from services.manual_ledger import ManualLedgerService, ValidationError
    try:
        body = req.get_json()
    except ValueError:
        return _json_response({"error": "Invalid JSON body"}, req, 400)

    try:
        service = ManualLedgerService()
        entry = service.create_entry(body, actor=_actor(req), correlation_id=_correlation_id(req))
        balance = service.get_balance(entry["person_key"])
        return _json_response(
            {"success": True, "entry": _serialize_entry(entry), "balance": str(balance)}, req, 201
        )
    except ValidationError as ve:
        return _json_response({"error": str(ve)}, req, 400)
    except Exception as e:
        logging.error(f"manual_ledger_create error: {e}")
        return _json_response({"error": "Internal server error"}, req, 500)


@bp.route(route="financials/manual-ledger/entry/{entry_id}/edit", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def manual_ledger_edit(req: func.HttpRequest) -> func.HttpResponse:
    """Appends a new revision. The prior revision is superseded, never overwritten."""
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_cors(req))
    guard = require_function_key(req)
    if guard:
        return guard

    from services.manual_ledger import ManualLedgerService, ValidationError
    try:
        body = req.get_json()
    except ValueError:
        return _json_response({"error": "Invalid JSON body"}, req, 400)

    entry_id = req.route_params.get("entry_id")
    try:
        service = ManualLedgerService()
        result = service.edit_entry(entry_id, body, actor=_actor(req),
                                    correlation_id=_correlation_id(req))
        balance = service.get_balance(body.get("personKey"))
        return _json_response({"success": True, **result, "balance": str(balance)}, req)
    except ValidationError as ve:
        return _json_response({"error": str(ve)}, req, 400)
    except Exception as e:
        logging.error(f"manual_ledger_edit error: {e}")
        return _json_response({"error": "Internal server error"}, req, 500)


@bp.route(route="financials/manual-ledger/entry/{entry_id}/void", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def manual_ledger_void(req: func.HttpRequest) -> func.HttpResponse:
    """Voids an entry (state transition). Repeat calls are safe no-ops."""
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_cors(req))
    guard = require_function_key(req)
    if guard:
        return guard

    from services.manual_ledger import ManualLedgerService, ValidationError, parse_person_key
    try:
        body = req.get_json()
    except ValueError:
        body = {}

    entry_id = req.route_params.get("entry_id")
    try:
        service = ManualLedgerService()
        result = service.void_entry(entry_id, actor=_actor(req),
                                    reason=(body or {}).get("reason"),
                                    correlation_id=_correlation_id(req))
        person = (body or {}).get("personKey")
        if person:
            result["balance"] = str(service.get_balance(parse_person_key(person)))
        return _json_response({"success": True, **result}, req)
    except ValidationError as ve:
        return _json_response({"error": str(ve)}, req, 400)
    except Exception as e:
        logging.error(f"manual_ledger_void error: {e}")
        return _json_response({"error": "Internal server error"}, req, 500)
