"""
Return-trip rebooking engine.

Stage 1 (this package, so far): the provider-agnostic foundation — flight
identity, normalized flight types, the provider interface and its AeroAPI
adapter, typed domain errors, and the two state machines.

Persistence, the reminder scheduler, the token service, and the HTTP routes
build on these and land in later stages. See docs/return-trip-engine-findings.md
for what already exists in this repo and which of the original prompt's
assumptions had to change.
"""
from .errors import (
    AmbiguousFlightOccurrence, BookingDependencyUnavailable,
    FlightDoesNotMatchReturnRoute, FlightNotFound, FlightProviderUnavailable,
    InvalidFlightNumber, InvalidOrExpiredToken, InvalidServiceDate,
    InvalidStateTransition, RateLimitExceeded, ReturnBookingAlreadyExists,
    ReturnLinkExpired, ReturnTripError,
)
from .flight_ident import FlightIdent, parse_flight_ident, parse_service_date
from .flight_provider import (
    AeroApiFlightProvider, FlightDataProvider, default_provider,
)
from .flight_types import (
    Airport, DataAvailability, FlightOccurrence, FlightStatus, FlightTelemetry,
    OccurrenceQuery, summarize_candidates,
)
from .states import (
    TelemetryState, WorkflowState, assert_transition,
    assert_transition_telemetry, can_transition, can_transition_telemetry,
    is_workflow_terminal, telemetry_state_for,
)

__all__ = [
    "AeroApiFlightProvider", "Airport", "AmbiguousFlightOccurrence",
    "BookingDependencyUnavailable", "DataAvailability", "FlightDataProvider",
    "FlightDoesNotMatchReturnRoute", "FlightIdent", "FlightNotFound",
    "FlightOccurrence", "FlightProviderUnavailable", "FlightStatus",
    "FlightTelemetry", "InvalidFlightNumber", "InvalidOrExpiredToken",
    "InvalidServiceDate", "InvalidStateTransition", "OccurrenceQuery",
    "RateLimitExceeded", "ReturnBookingAlreadyExists", "ReturnLinkExpired",
    "ReturnTripError", "TelemetryState", "WorkflowState", "assert_transition",
    "assert_transition_telemetry", "can_transition", "can_transition_telemetry",
    "default_provider", "is_workflow_terminal", "parse_flight_ident",
    "parse_service_date", "summarize_candidates", "telemetry_state_for",
]
