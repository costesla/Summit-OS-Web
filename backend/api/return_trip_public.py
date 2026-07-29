"""
Passenger-facing return-trip routes (Stage 4).

  * POST return-trips/resolve-flight
  * POST return-trips/confirm

**These are deliberately unauthenticated in the Easy Auth sense.** The
passenger has no account (findings §2.2) — the link token IS the credential.
That makes these the most exposed endpoints in the feature, so:

  * the token is never echoed back, never logged, and never put in a query
    string, only ever read from the JSON body;
  * every domain failure answers through `ReturnTripError.to_response()`, whose
    messages are written to be passenger-safe, so provider text and database
    detail cannot leak through an error path;
  * an unexpected exception returns a generic 500 rather than the exception
    text, because an endpoint anyone can reach is the wrong place to discover
    what our stack traces say.

Rate limiting lives in the token service (a per-workflow resolve budget) rather
than per-IP: the cost being defended is billed AeroAPI calls, and the token —
not the IP — is what maps to a workflow and therefore to our bill.
"""
import json
import logging
from datetime import date, datetime, timezone

import azure.functions as func

from services.auth_guard import cors_headers as _get_cors
from services.return_trip.booking_service import ReturnTripBookingService
from services.return_trip.errors import ReturnTripError
from services.return_trip.store import ReturnTripStore
from services.return_trip.tokens import TokenService

bp = func.Blueprint()


def _cors(req: func.HttpRequest) -> dict:
    return _get_cors(req)


def _json(req, body, status=200):
    return func.HttpResponse(json.dumps(body), status_code=status,
                             headers=_cors(req), mimetype="application/json")


def _service() -> ReturnTripBookingService:
    from services.database import DatabaseClient
    factory = DatabaseClient().get_connection
    return ReturnTripBookingService(
        store=ReturnTripStore(connection_factory=factory),
        tokens=TokenService(connection_factory=factory))


def _body(req: func.HttpRequest):
    try:
        return req.get_json(), None
    except ValueError:
        return None, _json(req, {"success": False,
                                 "error": {"code": "InvalidBody",
                                           "message": "Invalid JSON body"}}, 400)


def _handle(req, fn):
    """Run a service call, mapping domain errors to their own status codes.

    ReturnTripError carries its own http_status and a passenger-safe message,
    so the mapping is generic — a new domain error gets correct HTTP behaviour
    without touching this layer.
    """
    try:
        return _json(req, {"success": True, **fn()})
    except ReturnTripError as exc:
        # Domain errors are expected traffic, not incidents: logged at info
        # with the code only, so a passenger mistyping a flight number does not
        # look like a fault.
        logging.info(f"return-trip: {exc.code}")
        return _json(req, exc.to_response(), exc.http_status)
    except Exception:
        logging.exception("return-trip: unhandled error")
        return _json(req, {"success": False,
                           "error": {"code": "InternalError",
                                     "message": "Something went wrong. "
                                                "Please try again.",
                                     "retryable": True}}, 500)


@bp.route(route="return-trips/resolve-flight", methods=["POST", "OPTIONS"],
          auth_level=func.AuthLevel.ANONYMOUS)
def resolve_flight(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_cors(req))

    body, bad = _body(req)
    if bad:
        return bad
    body = body or {}

    token = body.get("token")
    flight_number = body.get("flightNumber")
    raw_date = body.get("serviceDate")
    if not token or not flight_number or not raw_date:
        return _json(req, {"success": False,
                           "error": {"code": "MissingField",
                                     "message": "token, flightNumber and "
                                                "serviceDate are required"}}, 400)
    try:
        service_date = date.fromisoformat(str(raw_date))
    except ValueError:
        return _json(req, {"success": False,
                           "error": {"code": "InvalidServiceDate",
                                     "message": "serviceDate must be "
                                                "YYYY-MM-DD"}}, 400)

    return _handle(req, lambda: _service().resolve_flight(
        token, flight_number=str(flight_number), service_date=service_date))


@bp.route(route="return-trips/confirm", methods=["POST", "OPTIONS"],
          auth_level=func.AuthLevel.ANONYMOUS)
def confirm(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_cors(req))

    body, bad = _body(req)
    if bad:
        return bad
    body = body or {}

    token = body.get("token")
    verification_id = body.get("verificationId")
    if not token or not verification_id:
        return _json(req, {"success": False,
                           "error": {"code": "MissingField",
                                     "message": "token and verificationId "
                                                "are required"}}, 400)

    return _handle(req, lambda: _service().confirm(
        token, verification_id=str(verification_id),
        idempotency_key=body.get("idempotencyKey")))
