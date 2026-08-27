"""
Typed domain errors for the return-trip workflow.

Every error that can reach a passenger goes through here, for one reason: the
return-booking link is an UNAUTHENTICATED surface. Anyone with the URL — or a
guess at it — gets whatever these responses say. So the safe payload is built
here, once, rather than being assembled ad hoc at each route.

`to_response()` is deliberately narrow: a stable machine-readable code, a
sentence a passenger can act on, and the correlation id that ties the request
to the structured log. Never a stack trace, a SQL fragment, a provider payload,
or anything that reveals whether a given workflow exists.

`retryable` is the other load-bearing field. Provider downtime during lookup is
a "try again in a moment"; provider downtime AFTER confirmation must never
invalidate a booking that already exists in our database. Callers branch on
this flag rather than on the status code, so that distinction can't be lost in
translation.
"""
from typing import Any, Optional


class ReturnTripError(Exception):
    """Base for every domain error the return-trip workflow can raise."""

    code: str = "ReturnTripError"
    http_status: int = 500
    # Safe to show a passenger. Subclasses override; never interpolate
    # provider text or database detail into it.
    default_message: str = "Something went wrong. Please try again."
    # True when the SAME request can reasonably be retried unchanged.
    retryable: bool = False

    def __init__(self, message: Optional[str] = None, *,
                 correlation_id: Optional[str] = None, **details: Any):
        self.message = message or self.default_message
        self.correlation_id = correlation_id
        # Structured, already-safe extras (e.g. candidate flights). Anything
        # put here WILL be serialised to the client — keep it PII-free.
        self.details = details
        super().__init__(self.message)

    def to_response(self) -> dict:
        body: dict = {
            "success": False,
            "error": {"code": self.code, "message": self.message,
                      "retryable": self.retryable},
        }
        if self.correlation_id:
            body["correlationId"] = self.correlation_id
        if self.details:
            body["error"].update(self.details)
        return body


# ── 4xx: the request itself ──────────────────────────────────────────────────
class InvalidFlightNumber(ReturnTripError):
    code = "InvalidFlightNumber"
    http_status = 400
    default_message = ("That doesn't look like a flight number. Use the airline "
                       "code and number, for example UA1234.")


class InvalidServiceDate(ReturnTripError):
    code = "InvalidServiceDate"
    http_status = 400
    default_message = "Enter the date your return flight departs, as YYYY-MM-DD."


class InvalidOrExpiredToken(ReturnTripError):
    """Deliberately indistinguishable from a token that never existed — an
    attacker must not be able to probe for valid workflow links."""
    code = "InvalidOrExpiredToken"
    http_status = 401
    default_message = "This booking link is no longer valid."


class FlightNotFound(ReturnTripError):
    code = "FlightNotFound"
    http_status = 404
    default_message = ("We couldn't find that flight on that date. Check the "
                       "number and the departure date, then try again.")


class ReturnBookingAlreadyExists(ReturnTripError):
    code = "ReturnBookingAlreadyExists"
    http_status = 409
    default_message = "A return trip is already booked for this journey."


class AmbiguousFlightOccurrence(ReturnTripError):
    """More than one leg matched. We never guess — the passenger picks.

    `candidates` must already be passenger-safe summaries, not raw provider
    objects.
    """
    code = "AmbiguousFlightOccurrence"
    http_status = 409
    default_message = ("That flight number operates more than one route that "
                       "day. Please choose the correct one.")

    def __init__(self, candidates, **kw):
        super().__init__(candidates=list(candidates), **kw)


class ReturnLinkExpired(ReturnTripError):
    code = "ReturnLinkExpired"
    http_status = 410
    default_message = ("This booking link has expired. Contact us and we'll "
                       "send a new one.")


class FlightDoesNotMatchReturnRoute(ReturnTripError):
    code = "FlightDoesNotMatchReturnRoute"
    http_status = 422
    default_message = ("That flight doesn't arrive at the airport we're "
                       "collecting you from. Check the flight number.")


class RateLimitExceeded(ReturnTripError):
    code = "RateLimitExceeded"
    http_status = 429
    default_message = "Too many attempts. Please wait a moment and try again."
    retryable = True


# ── 5xx: our dependencies, not the passenger ─────────────────────────────────
class FlightProviderUnavailable(ReturnTripError):
    """The flight data provider failed. Retryable BEFORE confirmation only —
    after a booking exists, provider downtime must never invalidate it."""
    code = "FlightProviderUnavailable"
    http_status = 502
    default_message = ("We can't reach the flight service right now. Please "
                       "try again in a moment.")
    retryable = True


class BookingDependencyUnavailable(ReturnTripError):
    code = "BookingDependencyUnavailable"
    http_status = 503
    default_message = ("We can't complete your booking right now. Please try "
                       "again in a moment.")
    retryable = True


class InvalidStateTransition(ReturnTripError):
    """Raised by the state machines. Never surfaced verbatim to a passenger —
    it means our own code tried an illegal move."""
    code = "InvalidStateTransition"
    http_status = 500
    default_message = "Something went wrong. Please try again."
