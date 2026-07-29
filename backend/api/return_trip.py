"""
Return-trip HTTP + timer surface (Stage 3).

Three entry points:

  * POST return-trip/complete   — the driver taps "trip complete"
  * safety-net timer            — arms the returns nobody confirmed
  * reminder timer              — queues reminders that have come due

**On authentication.** Owner-gated via Easy Auth, following `api/push.py`: the
SWA linked-backend proxy forwards `x-ms-client-principal` for an authenticated
session, and `/driver-dashboard*` is already restricted to `authenticated` in
`staticwebapp.config.json`. Absent or unparseable principal is a 401, so a
direct hit on summitos-api gets nothing.

Deliberately NOT a function key. This endpoint is called from the browser, and
this repository is public — a key shipped to the client would be a published
secret. `auth_guard.require_function_key` is also unsuitable on its own merits
here: it fails OPEN when `AZURE_FUNCTION_KEY` is unset, and an unset
environment variable must not be the difference between "authenticated" and
"anyone on the internet". This endpoint mutates workflow state and ultimately
causes mail to reach a customer.

Note the surrounding convention is weaker than this: `operations.py` imports
`require_function_key` but applies it to exactly one of its routes, leaving the
rest anonymous. That gap is real and is called out in the PR — it is not fixed
here, because changing live endpoints the dashboard depends on is its own
change with its own blast radius.
"""
import base64
import json
import logging
from datetime import datetime, timezone

import azure.functions as func

from services.auth_guard import cors_headers as _get_cors
from services.return_trip.completion import (
    CompletionOutcome, complete_outbound_trip, sweep_unconfirmed,
)
from services.return_trip.reminder_worker import run_once as run_reminder_pass
from services.return_trip.store import ReturnTripStore

bp = func.Blueprint()


def _cors(req: func.HttpRequest) -> dict:
    return _get_cors(req)


def _principal(req: func.HttpRequest):
    """Parse the SWA-forwarded Easy Auth principal; None if absent/invalid.

    Same shape as `api/push.py`. Absent is indistinguishable from invalid on
    purpose — both mean "not an authenticated session", and reporting which
    would tell an anonymous caller something about the header format.
    """
    header = req.headers.get("x-ms-client-principal")
    if not header:
        return None
    try:
        data = json.loads(base64.b64decode(header).decode("utf-8"))
        return data if (data.get("userId") or data.get("userDetails")) else None
    except Exception:
        return None


def _store_and_conn():
    from services.database import DatabaseClient
    factory = DatabaseClient().get_connection
    return ReturnTripStore(connection_factory=factory), factory


@bp.route(route="return-trip/complete", methods=["POST", "OPTIONS"],
          auth_level=func.AuthLevel.ANONYMOUS)
def complete_trip(req: func.HttpRequest) -> func.HttpResponse:
    """Driver confirms an outbound trip finished.

    `auth_level=ANONYMOUS` is the platform-level setting the rest of this app
    uses; the real gate is the Easy Auth principal, which fails closed.
    """
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_cors(req))

    if not _principal(req):
        logging.warning("Rejected return-trip completion: no authenticated session")
        return func.HttpResponse(
            json.dumps({"success": False, "error": "Unauthorized"}),
            status_code=401, headers=_cors(req), mimetype="application/json")

    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"success": False, "error": "Invalid JSON body"}),
            status_code=400, headers=_cors(req), mimetype="application/json")

    booking_id = (body or {}).get("bookingId")
    if not booking_id:
        return func.HttpResponse(
            json.dumps({"success": False, "error": "bookingId is required"}),
            status_code=400, headers=_cors(req), mimetype="application/json")

    try:
        store, factory = _store_and_conn()
        outcome = complete_outbound_trip(
            booking_id, store=store, connection_factory=factory,
            correlation_id=(body or {}).get("correlationId"))
    except Exception:
        logging.exception(f"Return-trip completion failed for {booking_id}")
        return func.HttpResponse(
            json.dumps({"success": False, "error": "Completion failed"}),
            status_code=500, headers=_cors(req), mimetype="application/json")

    # ARMED and ALREADY_ACTIVE are both 200: the driver tapping twice, or a
    # retried request, is not an error to show them. The outcome is returned
    # so the caller can tell the difference without having to infer it.
    return func.HttpResponse(
        json.dumps({"success": True, "outcome": outcome,
                    "returnArmed": outcome == CompletionOutcome.ARMED}),
        status_code=200, headers=_cors(req), mimetype="application/json")


@bp.timer_trigger(schedule="0 15 * * * *", arg_name="timer",
                  run_on_startup=False, use_monitor=False)
def return_trip_safety_net(timer: func.TimerRequest) -> None:
    """Hourly: arm returns for departures the driver never confirmed."""
    started = datetime.now(timezone.utc).isoformat()
    logging.info(f"Return-trip safety net starting at {started}")
    try:
        store, factory = _store_and_conn()
        counts = sweep_unconfirmed(store=store, connection_factory=factory)
    except Exception:
        # Logged at exception, not swallowed into a success path — the whole
        # point of this feature is that a missed return leaves a trace.
        logging.exception("Return-trip safety net failed")
        return
    logging.info(f"Return-trip safety net: {counts}")


@bp.timer_trigger(schedule="0 */5 * * * *", arg_name="timer",
                  run_on_startup=False, use_monitor=False)
def return_trip_reminders(timer: func.TimerRequest) -> None:
    """Every five minutes: queue reminders that have come due.

    Frequent because the reminder's value is time-sensitive and each pass is
    cheap — one indexed claim query that usually returns nothing.
    """
    try:
        store, _ = _store_and_conn()
        result = run_reminder_pass(store=store)
    except Exception:
        logging.exception("Return-trip reminder pass failed")
        return
    if result["claimed"]:
        logging.info(f"Return-trip reminders: {result}")
