"""
Return-trip engine, Stage 1: identity, provider abstraction, state machines.

The property this file exists to protect: A FLIGHT NUMBER DOES NOT IDENTIFY A
FLIGHT. UA1234 operates most days, and some idents fly several routes in one
day. Every test below is ultimately about refusing to guess which one the
passenger meant — because a wrong guess produces a booking that looks perfectly
correct in every screen and sends a driver to an airport on the wrong day.

No network and no billable AeroAPI calls: the provider client is a stub
throughout.
"""
import os
import sys
from datetime import date, datetime, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.return_trip import (  # noqa: E402
    AeroApiFlightProvider, FlightProviderUnavailable, FlightStatus,
    InvalidFlightNumber, InvalidServiceDate, InvalidStateTransition,
    OccurrenceQuery, TelemetryState, WorkflowState, assert_transition,
    assert_transition_telemetry, can_transition, parse_flight_ident,
    parse_service_date, summarize_candidates, telemetry_state_for,
)
from services.return_trip.flight_provider import (  # noqa: E402
    occurrence_from_aeroapi, occurrence_matches_service_date,
)
from services.return_trip.flight_types import FlightTelemetry  # noqa: E402
from services.return_trip.states import (  # noqa: E402
    TELEMETRY_TERMINAL, WORKFLOW_TERMINAL, _WORKFLOW_TRANSITIONS,
    can_transition_telemetry,
)


# ── fixtures ─────────────────────────────────────────────────────────────────
def _airport(iata, tz="America/Denver", name=None):
    return {"code_iata": iata, "code_icao": "K" + iata, "city": iata,
            "name": name or f"{iata} Airport", "timezone": tz}


def _leg(fa_id, origin, dest, sched_out, sched_in, *, tz_out="America/Chicago",
         tz_in="America/Denver", **over):
    leg = {
        "fa_flight_id": fa_id,
        "ident": "UAL1234", "ident_iata": "UA1234", "ident_icao": "UAL1234",
        "operator": "UAL", "operator_iata": "UA",
        "origin": _airport(origin, tz_out), "destination": _airport(dest, tz_in),
        "scheduled_out": sched_out, "scheduled_in": sched_in,
        "estimated_out": None, "estimated_in": None,
        "actual_out": None, "actual_in": None,
        "status": "Scheduled", "cancelled": False, "diverted": False,
        "aircraft_type": "B738",
    }
    leg.update(over)
    return leg


class _StubClient:
    """Stands in for FlightAwareClient. Records calls; never touches network."""

    def __init__(self, candidates=None, by_id=None, raises=None):
        self._candidates = candidates if candidates is not None else []
        self._by_id = by_id or {}
        self._raises = raises
        self.calls = []

    def flight_candidates(self, ident, cache_ttl=None, *,
                          expected_destination=None, dest_country=None):
        self.calls.append(("candidates", ident, expected_destination, cache_ttl))
        if self._raises:
            raise self._raises
        if expected_destination:
            exp = expected_destination.upper()
            return [f for f in self._candidates
                    if exp in {f["destination"].get("code_iata"),
                               f["destination"].get("code_icao")}]
        return list(self._candidates)

    def flight_by_fa_id(self, fa_id, cache_ttl=None):
        self.calls.append(("by_id", fa_id, None, cache_ttl))
        if self._raises:
            raise self._raises
        return self._by_id.get(fa_id)


def _provider(**kw):
    return AeroApiFlightProvider(client=_StubClient(**kw))


# ── flight identity ──────────────────────────────────────────────────────────
class TestFlightIdent:
    @pytest.mark.parametrize("raw,expected", [
        ("UA1234", "UA1234"),
        ("ua1234", "UA1234"),
        ("UA 1234", "UA1234"),
        ("  ua-1234 ", "UA1234"),
        ("UAL1234", "UAL1234"),      # ICAO form
        ("B61234", "B61234"),        # IATA code ending in a digit (JetBlue)
        ("9W123", "9W123"),          # IATA code starting with a digit
        ("UA0045", "UA45"),          # providers don't zero-pad
        ("AA100A", "AA100A"),        # operational suffix
    ])
    def test_accepts_what_passengers_actually_type(self, raw, expected):
        assert parse_flight_ident(raw).normalized == expected

    @pytest.mark.parametrize("raw,carrier,number", [
        ("UA1234", "UA", "1234"),
        ("UAL1234", "UAL", "1234"),
        ("B61234", "B6", "1234"),
        ("U21234", "U2", "1234"),
    ])
    def test_the_carrier_never_swallows_a_digit_of_the_number(self, raw, carrier, number):
        # A greedy [A-Z0-9]{2,3} carrier class parses UA1234 as UA1/234 and
        # then looks up a flight that doesn't exist. Pin the split explicitly.
        ident = parse_flight_ident(raw)
        assert (ident.carrier, ident.number) == (carrier, number)

    def test_keeps_the_original_for_the_audit_trail(self):
        # If a lookup later proves to have resolved the wrong leg, we need to
        # know what was ENTERED, not what we made of it.
        ident = parse_flight_ident("  ua-1234 ")
        assert ident.raw == "  ua-1234 "
        assert ident.normalized == "UA1234"

    def test_splits_carrier_from_number(self):
        ident = parse_flight_ident("UA1234")
        assert (ident.carrier, ident.number) == ("UA", "1234")
        assert not ident.is_icao_style
        assert parse_flight_ident("UAL1234").is_icao_style

    @pytest.mark.parametrize("raw", [
        None, "", "   ",
        "1234",            # no carrier
        "99123",           # two digits is not a carrier code
        "UNITED1234",      # four-character carrier
        "UA",              # no number
        "UA12345",         # five digits
        "UA0",             # zero is not a flight
        "UA0000",
        "DROP TABLE",
        "UA1234!!",
        "U" * 40,          # over the length cap
    ])
    def test_rejects_rather_than_guessing(self, raw):
        with pytest.raises(InvalidFlightNumber):
            parse_flight_ident(raw)

    def test_length_cap_applies_before_separators_are_stripped(self):
        # Otherwise padding could smuggle an over-length ident past the check.
        with pytest.raises(InvalidFlightNumber):
            parse_flight_ident("U A - 1 2 3 4 " + " " * 20)


class TestServiceDate:
    def test_accepts_iso_dates(self):
        today = date(2026, 7, 28)
        assert parse_service_date("2026-08-01", today=today) == date(2026, 8, 1)

    def test_accepts_date_objects(self):
        today = date(2026, 7, 28)
        assert parse_service_date(date(2026, 8, 1), today=today) == date(2026, 8, 1)

    @pytest.mark.parametrize("raw", [
        None, "", "not-a-date", "08/01/2026", "2026-13-01", "2026-02-30",
    ])
    def test_rejects_unparseable(self, raw):
        with pytest.raises(InvalidServiceDate):
            parse_service_date(raw, today=date(2026, 7, 28))

    def test_rejects_dates_outside_a_sane_window(self):
        today = date(2026, 7, 28)
        with pytest.raises(InvalidServiceDate):
            parse_service_date("2020-01-01", today=today)
        with pytest.raises(InvalidServiceDate):
            parse_service_date("2099-01-01", today=today)

    def test_tolerates_yesterday(self):
        # A red-eye that departed late local time is still "today" to a
        # passenger filling the form at 1am.
        today = date(2026, 7, 28)
        assert parse_service_date("2026-07-27", today=today) == date(2026, 7, 27)


# ── occurrence resolution ────────────────────────────────────────────────────
class TestOccurrenceResolution:
    def _query(self, service_date=date(2026, 8, 1), **kw):
        return OccurrenceQuery(ident_normalized="UA1234",
                               service_date=service_date, **kw)

    def test_resolves_a_single_dated_occurrence(self):
        legs = [_leg("UAL1234-1", "ORD", "COS",
                     "2026-08-01T18:00:00Z", "2026-08-01T21:00:00Z")]
        result = _provider(candidates=legs).resolve_flight_occurrence(self._query())

        assert len(result) == 1
        occ = result[0]
        assert occ.provider_flight_id == "UAL1234-1"
        assert occ.flight_number == "UA1234"
        assert occ.departure.iata == "ORD"
        assert occ.arrival.iata == "COS"
        assert occ.status is FlightStatus.SCHEDULED

    def test_the_same_flight_number_on_another_day_is_excluded(self):
        # The core bug this whole design exists to prevent.
        legs = [
            _leg("UAL1234-jul31", "ORD", "COS",
                 "2026-07-31T18:00:00Z", "2026-07-31T21:00:00Z"),
            _leg("UAL1234-aug1", "ORD", "COS",
                 "2026-08-01T18:00:00Z", "2026-08-01T21:00:00Z"),
            _leg("UAL1234-aug2", "ORD", "COS",
                 "2026-08-02T18:00:00Z", "2026-08-02T21:00:00Z"),
        ]
        result = _provider(candidates=legs).resolve_flight_occurrence(self._query())
        assert [o.provider_flight_id for o in result] == ["UAL1234-aug1"]

    def test_two_routes_on_the_same_day_both_come_back(self):
        # Ambiguity is REPORTED, never resolved by picking one.
        legs = [
            _leg("UAL1234-a", "ORD", "COS",
                 "2026-08-01T14:00:00Z", "2026-08-01T17:00:00Z"),
            _leg("UAL1234-b", "DEN", "AUS",
                 "2026-08-01T22:00:00Z", "2026-08-02T01:00:00Z"),
        ]
        result = _provider(candidates=legs).resolve_flight_occurrence(self._query())
        assert len(result) == 2

    def test_candidates_are_ordered_by_departure(self):
        legs = [
            _leg("late", "DEN", "AUS", "2026-08-01T22:00:00Z", "2026-08-02T01:00:00Z"),
            _leg("early", "ORD", "COS", "2026-08-01T14:00:00Z", "2026-08-01T17:00:00Z"),
        ]
        result = _provider(candidates=legs).resolve_flight_occurrence(self._query())
        assert [o.provider_flight_id for o in result] == ["early", "late"]

    def test_the_arrival_guard_excludes_the_wrong_airport(self):
        legs = [
            _leg("to-cos", "ORD", "COS", "2026-08-01T18:00:00Z", "2026-08-01T21:00:00Z"),
            _leg("to-den", "ORD", "DEN", "2026-08-01T19:00:00Z", "2026-08-01T22:00:00Z"),
        ]
        result = _provider(candidates=legs).resolve_flight_occurrence(
            self._query(expected_arrival_code="COS"))
        assert [o.provider_flight_id for o in result] == ["to-cos"]

    def test_a_flight_to_the_wrong_airport_yields_nothing(self):
        # Better an empty result the caller turns into a clear error than a
        # booking to collect someone from an airport they never reach.
        legs = [_leg("to-den", "ORD", "DEN",
                     "2026-08-01T18:00:00Z", "2026-08-01T22:00:00Z")]
        result = _provider(candidates=legs).resolve_flight_occurrence(
            self._query(expected_arrival_code="COS"))
        assert result == []

    def test_no_matching_flight_is_empty_not_an_error(self):
        assert _provider(candidates=[]).resolve_flight_occurrence(self._query()) == []

    def test_provider_failure_is_retryable_never_flight_not_found(self):
        # Telling a passenger their real flight doesn't exist because AeroAPI
        # blipped would send them to fix a problem that isn't theirs.
        provider = AeroApiFlightProvider(
            client=_StubClient(raises=RuntimeError("connection reset")))
        with pytest.raises(FlightProviderUnavailable) as exc:
            provider.resolve_flight_occurrence(self._query())
        assert exc.value.retryable is True
        assert exc.value.http_status == 502

    def test_cache_ttl_reaches_the_client(self):
        # AeroAPI bills per call; the polling path relies on this being honoured.
        client = _StubClient(candidates=[])
        AeroApiFlightProvider(client=client).resolve_flight_occurrence(
            self._query(), cache_ttl=300)
        assert client.calls[0][3] == 300


class TestServiceDateTimezones:
    """Service date is the DEPARTURE date in the ORIGIN's local time."""

    def test_a_late_local_departure_is_not_pushed_into_the_next_day(self):
        # 23:30 on Aug 1 in Denver is 05:30 Aug 2 UTC. The airline — and the
        # passenger's ticket — call it the 1st.
        leg = _leg("night", "DEN", "ORD",
                   "2026-08-02T05:30:00Z", "2026-08-02T09:00:00Z",
                   tz_out="America/Denver")
        occ = occurrence_from_aeroapi(leg)
        assert occurrence_matches_service_date(occ, date(2026, 8, 1))
        assert not occurrence_matches_service_date(occ, date(2026, 8, 2))

    def test_an_early_local_departure_is_not_pulled_back_a_day(self):
        leg = _leg("morning", "ORD", "COS",
                   "2026-08-01T12:00:00Z", "2026-08-01T15:00:00Z",
                   tz_out="America/Chicago")
        occ = occurrence_from_aeroapi(leg)
        assert occurrence_matches_service_date(occ, date(2026, 8, 1))

    def test_without_a_timezone_we_widen_rather_than_drop(self):
        # An unplaceable leg becomes a candidate the passenger can rule out;
        # a wrongly-excluded one is a dead end with no recourse.
        leg = _leg("no-tz", "ORD", "COS",
                   "2026-08-02T02:00:00Z", "2026-08-02T05:00:00Z",
                   tz_out=None, tz_in=None)
        occ = occurrence_from_aeroapi(leg)
        assert occ.availability.has_timezones is False
        assert occurrence_matches_service_date(occ, date(2026, 8, 1))
        assert occurrence_matches_service_date(occ, date(2026, 8, 2))
        assert not occurrence_matches_service_date(occ, date(2026, 8, 5))

    def test_a_garbage_timezone_degrades_instead_of_raising(self):
        leg = _leg("bad-tz", "ORD", "COS",
                   "2026-08-01T18:00:00Z", "2026-08-01T21:00:00Z",
                   tz_out="Not/AZone")
        occ = occurrence_from_aeroapi(leg)
        assert occurrence_matches_service_date(occ, date(2026, 8, 1))


class TestOccurrenceMapping:
    def test_unavailable_fields_are_null_and_declared(self):
        # "Not published yet" and "our plan doesn't return it" must not be
        # dressed up as data.
        leg = _leg("plain", "ORD", "COS",
                   "2026-08-01T18:00:00Z", "2026-08-01T21:00:00Z")
        occ = occurrence_from_aeroapi(leg)
        assert occ.estimated_arrival_utc is None
        assert occ.arrival_gate is None
        assert occ.availability.has_estimated_times is False
        assert occ.availability.has_gates is False
        assert occ.to_public()["estimatedArrivalAt"] is None
        assert occ.to_public()["dataAvailability"]["gates"] is False

    def test_available_fields_are_declared_too(self):
        leg = _leg("rich", "ORD", "COS",
                   "2026-08-01T18:00:00Z", "2026-08-01T21:00:00Z",
                   estimated_in="2026-08-01T21:25:00Z", gate_destination="B14",
                   terminal_destination="B")
        occ = occurrence_from_aeroapi(leg)
        assert occ.availability.has_estimated_times is True
        assert occ.availability.has_gates is True
        assert occ.arrival_gate == "B14"

    def test_best_arrival_prefers_actual_then_estimated_then_scheduled(self):
        sched = _leg("s", "ORD", "COS", "2026-08-01T18:00:00Z", "2026-08-01T21:00:00Z")
        assert occurrence_from_aeroapi(sched).best_arrival_utc == \
            datetime(2026, 8, 1, 21, tzinfo=timezone.utc)

        est = dict(sched, estimated_in="2026-08-01T21:30:00Z")
        assert occurrence_from_aeroapi(est).best_arrival_utc == \
            datetime(2026, 8, 1, 21, 30, tzinfo=timezone.utc)

        act = dict(est, actual_in="2026-08-01T21:18:00Z")
        assert occurrence_from_aeroapi(act).best_arrival_utc == \
            datetime(2026, 8, 1, 21, 18, tzinfo=timezone.utc)

    def test_a_codeshare_is_flagged_not_hidden(self):
        # The ticket says one airline, the aircraft belongs to another. The
        # passenger has to recognise the flight we show them.
        leg = _leg("cs", "ORD", "COS", "2026-08-01T18:00:00Z", "2026-08-01T21:00:00Z",
                   ident_iata="AC1234", ident="ACA1234",
                   operator="UAL", operator_iata="UA")
        occ = occurrence_from_aeroapi(leg)
        assert occ.is_codeshare
        assert occ.marketing_carrier == "AC"
        assert occ.operating_carrier == "UA"
        assert occ.to_public()["operatedBy"] is not None

    def test_same_carrier_is_not_a_codeshare(self):
        leg = _leg("direct", "ORD", "COS",
                   "2026-08-01T18:00:00Z", "2026-08-01T21:00:00Z")
        assert occurrence_from_aeroapi(leg).is_codeshare is False

    @pytest.mark.parametrize("over,expected", [
        ({}, FlightStatus.SCHEDULED),
        ({"actual_out": "2026-08-01T18:05:00Z"}, FlightStatus.ACTIVE),
        ({"actual_out": "2026-08-01T18:05:00Z",
          "actual_in": "2026-08-01T21:02:00Z"}, FlightStatus.LANDED),
        ({"cancelled": True}, FlightStatus.CANCELLED),
        ({"diverted": True}, FlightStatus.DIVERTED),
        # Flags beat display text: a cancelled flight is cancelled even if the
        # status string still says something else.
        ({"cancelled": True, "status": "En Route"}, FlightStatus.CANCELLED),
    ])
    def test_status_mapping(self, over, expected):
        leg = _leg("s", "ORD", "COS", "2026-08-01T18:00:00Z",
                   "2026-08-01T21:00:00Z", **over)
        assert occurrence_from_aeroapi(leg).status is expected

    def test_a_leg_without_an_id_is_dropped(self):
        leg = _leg("x", "ORD", "COS", "2026-08-01T18:00:00Z", "2026-08-01T21:00:00Z")
        leg["fa_flight_id"] = None
        assert occurrence_from_aeroapi(leg) is None

    def test_malformed_input_does_not_raise(self):
        assert occurrence_from_aeroapi(None) is None
        assert occurrence_from_aeroapi({}) is None
        assert occurrence_from_aeroapi({"fa_flight_id": "x"}) is not None

    def test_candidate_summaries_carry_no_more_than_needed(self):
        legs = [_leg("a", "ORD", "COS", "2026-08-01T18:00:00Z", "2026-08-01T21:00:00Z")]
        occs = [occurrence_from_aeroapi(l) for l in legs]
        summary = summarize_candidates(occs)[0]
        assert set(summary) == {
            "verificationCandidateId", "flightNumber", "departureAirport",
            "arrivalAirport", "scheduledDepartureAt", "scheduledArrivalAt",
            "operatedBy",
        }


class TestTelemetry:
    def test_status_lookup_uses_the_dated_id_not_the_ident(self):
        # Re-resolving an ident would have to disambiguate again — and pay for
        # it. fa_flight_id names exactly one operation.
        leg = _leg("UAL1234-aug1", "ORD", "COS",
                   "2026-08-01T18:00:00Z", "2026-08-01T21:00:00Z",
                   actual_in="2026-08-01T20:55:00Z", gate_destination="B14")
        client = _StubClient(by_id={"UAL1234-aug1": leg})
        tel = AeroApiFlightProvider(client=client).get_flight_status("UAL1234-aug1")

        assert client.calls[0][0] == "by_id"
        assert tel.status is FlightStatus.LANDED
        assert tel.arrival_gate == "B14"
        assert tel.is_terminal

    def test_unknown_id_returns_none(self):
        assert AeroApiFlightProvider(client=_StubClient()).get_flight_status("nope") is None

    def test_provider_failure_is_retryable(self):
        provider = AeroApiFlightProvider(client=_StubClient(raises=OSError("boom")))
        with pytest.raises(FlightProviderUnavailable):
            provider.get_flight_status("UAL1234-aug1")

    def test_unchanged_snapshots_are_deduplicated(self):
        # Each stored snapshot can trigger a calendar push; AeroAPI charges for
        # each poll. Only material change is worth acting on.
        a = FlightTelemetry(provider="p", provider_flight_id="1",
                            status=FlightStatus.ACTIVE,
                            estimated_arrival_utc=datetime(2026, 8, 1, 21, tzinfo=timezone.utc))
        same_later = FlightTelemetry(provider="p", provider_flight_id="1",
                                     status=FlightStatus.ACTIVE,
                                     estimated_arrival_utc=datetime(2026, 8, 1, 21, tzinfo=timezone.utc),
                                     retrieved_at_utc=datetime(2030, 1, 1, tzinfo=timezone.utc))
        assert same_later.materially_differs_from(a) is False
        assert a.materially_differs_from(None) is True

    def test_an_eta_change_counts_as_material(self):
        a = FlightTelemetry(provider="p", provider_flight_id="1",
                            status=FlightStatus.ACTIVE,
                            estimated_arrival_utc=datetime(2026, 8, 1, 21, tzinfo=timezone.utc))
        b = FlightTelemetry(provider="p", provider_flight_id="1",
                            status=FlightStatus.ACTIVE,
                            estimated_arrival_utc=datetime(2026, 8, 1, 21, 40, tzinfo=timezone.utc))
        assert b.materially_differs_from(a) is True


# ── state machines ───────────────────────────────────────────────────────────
class TestWorkflowStates:
    def test_the_happy_path_is_legal_end_to_end(self):
        path = [
            WorkflowState.REMINDER_SCHEDULED, WorkflowState.REMINDER_DISPATCHING,
            WorkflowState.REMINDER_SENT, WorkflowState.FLIGHT_VERIFICATION_PENDING,
            WorkflowState.FLIGHT_VERIFIED, WorkflowState.CONFIRMATION_PROCESSING,
            WorkflowState.CONFIRMED,
        ]
        for current, target in zip(path, path[1:]):
            assert_transition(current, target)

    def test_verification_cannot_be_skipped(self):
        # The whole point of the workflow: no booking without a verified flight.
        with pytest.raises(InvalidStateTransition):
            assert_transition(WorkflowState.REMINDER_SENT, WorkflowState.CONFIRMED)
        with pytest.raises(InvalidStateTransition):
            assert_transition(WorkflowState.REMINDER_SCHEDULED, WorkflowState.CONFIRMED)

    def test_a_confirmed_workflow_cannot_be_re_confirmed(self):
        # Double-tap and webhook redelivery both land here.
        with pytest.raises(InvalidStateTransition):
            assert_transition(WorkflowState.CONFIRMED, WorkflowState.CONFIRMED)
        with pytest.raises(InvalidStateTransition):
            assert_transition(WorkflowState.CONFIRMED,
                              WorkflowState.CONFIRMATION_PROCESSING)

    def test_a_confirmed_workflow_can_still_be_cancelled(self):
        assert_transition(WorkflowState.CONFIRMED, WorkflowState.CANCELED)

    def test_terminal_states_are_dead_ends(self):
        for terminal in (WorkflowState.EXPIRED, WorkflowState.CANCELED):
            for target in WorkflowState:
                assert not can_transition(terminal, target)

    def test_a_failed_dispatch_can_be_retried_without_resending(self):
        # Releasing the claim returns it to the queue; it must not jump to SENT.
        assert_transition(WorkflowState.REMINDER_DISPATCHING,
                          WorkflowState.REMINDER_SCHEDULED)

    def test_a_wrong_flight_number_can_be_corrected(self):
        assert_transition(WorkflowState.FLIGHT_VERIFICATION_PENDING,
                          WorkflowState.FLIGHT_VERIFICATION_PENDING)
        assert_transition(WorkflowState.FLIGHT_VERIFIED,
                          WorkflowState.FLIGHT_VERIFICATION_PENDING)

    def test_a_mid_transaction_failure_rolls_back_to_verified(self):
        assert_transition(WorkflowState.CONFIRMATION_PROCESSING,
                          WorkflowState.FLIGHT_VERIFIED)

    def test_every_state_can_reach_a_terminal_state(self):
        # No state may trap a workflow forever.
        for state in WorkflowState:
            if state in WORKFLOW_TERMINAL:
                continue
            reachable, frontier = set(), [state]
            while frontier:
                s = frontier.pop()
                for nxt in _WORKFLOW_TRANSITIONS.get(s, frozenset()):
                    if nxt not in reachable:
                        reachable.add(nxt)
                        frontier.append(nxt)
            assert reachable & WORKFLOW_TERMINAL, f"{state} cannot terminate"


class TestTelemetryStates:
    def test_a_provider_outage_never_traps_a_flight(self):
        # UNKNOWN means "we couldn't see", not "the flight is gone". Every real
        # state must remain reachable, or an outage would strand a booking.
        for target in (TelemetryState.SCHEDULED, TelemetryState.ACTIVE,
                       TelemetryState.LANDED, TelemetryState.CANCELED,
                       TelemetryState.DIVERTED):
            assert_transition_telemetry(TelemetryState.UNKNOWN, target)

    def test_landing_does_not_end_monitoring_by_itself(self):
        # A gate can still be assigned after touchdown.
        assert_transition_telemetry(TelemetryState.LANDED,
                                    TelemetryState.MONITORING_COMPLETE)
        assert TelemetryState.LANDED not in TELEMETRY_TERMINAL

    def test_a_diverted_flight_still_lands_somewhere(self):
        # The passenger still needs collecting — from a different airport.
        assert_transition_telemetry(TelemetryState.DIVERTED, TelemetryState.LANDED)

    def test_monitoring_complete_is_the_end(self):
        for target in TelemetryState:
            assert not can_transition_telemetry(
                TelemetryState.MONITORING_COMPLETE, target)

    def test_a_landed_flight_cannot_go_back_to_scheduled(self):
        with pytest.raises(InvalidStateTransition):
            assert_transition_telemetry(TelemetryState.LANDED,
                                        TelemetryState.SCHEDULED)

    @pytest.mark.parametrize("flight_status,expected", [
        (FlightStatus.SCHEDULED, TelemetryState.SCHEDULED),
        (FlightStatus.ACTIVE, TelemetryState.ACTIVE),
        (FlightStatus.LANDED, TelemetryState.LANDED),
        (FlightStatus.CANCELLED, TelemetryState.CANCELED),
        (FlightStatus.DIVERTED, TelemetryState.DIVERTED),
        (FlightStatus.UNKNOWN, TelemetryState.UNKNOWN),
    ])
    def test_observed_status_maps_onto_the_machine(self, flight_status, expected):
        assert telemetry_state_for(flight_status) is expected


# ── error contract ───────────────────────────────────────────────────────────
class TestErrorResponses:
    def test_responses_carry_no_internals(self):
        from services.return_trip import FlightNotFound
        body = FlightNotFound(correlation_id="abc-123").to_response()
        assert body["success"] is False
        assert body["error"]["code"] == "FlightNotFound"
        assert body["correlationId"] == "abc-123"
        serialized = str(body).lower()
        for leak in ("traceback", "select ", "api_key", "password", "aeroapi.flightaware"):
            assert leak not in serialized

    def test_an_invalid_token_is_indistinguishable_from_a_missing_one(self):
        # Otherwise the endpoint becomes an oracle for probing valid links.
        from services.return_trip import InvalidOrExpiredToken
        a = InvalidOrExpiredToken().to_response()["error"]["message"]
        b = InvalidOrExpiredToken("This booking link is no longer valid.") \
            .to_response()["error"]["message"]
        assert a == b

    def test_ambiguity_carries_the_candidates(self):
        from services.return_trip import AmbiguousFlightOccurrence
        err = AmbiguousFlightOccurrence([{"verificationCandidateId": "x"}])
        body = err.to_response()
        assert err.http_status == 409
        assert body["error"]["candidates"] == [{"verificationCandidateId": "x"}]

    def test_only_dependency_failures_are_retryable(self):
        from services.return_trip import (
            BookingDependencyUnavailable, FlightNotFound,
            FlightProviderUnavailable, InvalidFlightNumber as IFN,
        )
        assert FlightProviderUnavailable().retryable is True
        assert BookingDependencyUnavailable().retryable is True
        assert IFN().retryable is False
        assert FlightNotFound().retryable is False
