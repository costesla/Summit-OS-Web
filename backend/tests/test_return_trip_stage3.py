"""
Return-trip completion + reminder scheduling (stage 3).

The two things worth proving here are the arming predicate and what happens
after a claim.

**The predicate**, because it is the whole feature's blast radius. We arm on
airport DEPARTURES — a FlightNumber with no ExpectedDest — so that the return
leg is an inbound flight we can track. Getting this backwards would send return
reminders to people who just flew home and have nothing to return from, and
nothing about the resulting row would look wrong. Several tests below exist
only to pin the null check that separates the two directions.

**What happens after a claim**, because `claim_due_reminders` moves a row into
ReminderDispatching and no other run will touch it. Every exit from that state
has to be explicit, or a passenger's reminder sits in a state nothing retries.

Connections are faked, same as stage 1/2. These prove the logic and the SQL's
shape, not that SQL Server accepts it.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.return_trip import completion as completion_mod  # noqa: E402
from services.return_trip import reminder_worker as worker_mod  # noqa: E402
from services.return_trip.completion import (  # noqa: E402
    CompletionOutcome, SAFETY_NET_HOURS, complete_outbound_trip,
    departure_metadata, find_unconfirmed, sweep_unconfirmed,
)
from services.return_trip.reminder_worker import (  # noqa: E402
    REMINDER_EVENT, dispatch_one, run_once,
)
from services.return_trip.states import WorkflowState  # noqa: E402
from services.return_trip.store import Workflow  # noqa: E402

NOW = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)


class _Cursor:
    def __init__(self, rows=None):
        self.executed = []
        self._rows = list(rows or [])

    def execute(self, sql, params=None):
        self.executed.append((" ".join(sql.split()), params))

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def fetchall(self):
        rows, self._rows = self._rows, []
        return rows

    def close(self):
        pass


class _Conn:
    def __init__(self, cursor):
        self._cursor = cursor
        self.closed = False

    def cursor(self):
        return self._cursor

    def close(self):
        self.closed = True


def _factory(rows=None):
    cur = _Cursor(rows)
    return (lambda: _Conn(cur)), cur


class _FakeStore:
    """Records what the service asked the store to do."""

    def __init__(self, *, create_returns="workflow", workflow=None,
                 claimed=None, transition_ok=True, enqueue_raises=None):
        self._create_returns = create_returns
        self._workflow = workflow
        self._claimed = list(claimed or [])
        self._transition_ok = transition_ok
        self._enqueue_raises = enqueue_raises
        self.created = []
        self.audits = []
        self.transitions = []
        self.enqueued = []

    def create_workflow(self, **kw):
        self.created.append(kw)
        if self._create_returns is None:
            return None
        return Workflow(workflow_id="wf-1",
                        outbound_booking_id=kw["outbound_booking_id"],
                        status=kw.get("status"), version=1)

    def audit(self, workflow_id, event_type, **kw):
        self.audits.append((workflow_id, event_type, kw))

    def get_workflow(self, workflow_id):
        return self._workflow

    def claim_due_reminders(self, *, now=None, limit=10):
        return self._claimed

    def transition(self, workflow_id, **kw):
        self.transitions.append((workflow_id, kw))
        return self._transition_ok

    def enqueue_and_transition(self, **kw):
        if self._enqueue_raises:
            raise self._enqueue_raises
        self.enqueued.append(kw)
        return True


def _workflow(**kw):
    base = dict(workflow_id="wf-1", outbound_booking_id="bk-1",
                status=WorkflowState.REMINDER_DISPATCHING, version=3,
                passenger_email="p@example.com", passenger_name="P",
                original_pickup_text="123 Main St",
                original_dropoff_airport="COS")
    base.update(kw)
    return Workflow(**base)


# ── the arming predicate ─────────────────────────────────────────────────────
class TestDeparturePredicate:
    def test_departure_is_found(self):
        factory, cur = _factory(rows=[("UA123",)])
        assert departure_metadata("bk-1", factory) == {"flight_number": "UA123"}

    def test_query_requires_expecteddest_null(self):
        """The null check is what separates a departure from an arrival.

        Pinned as SQL because it cannot be observed from the return value: a
        query missing this clause returns a flight number just the same, and
        every arrival in the system would start arming returns.
        """
        factory, cur = _factory(rows=[("UA123",)])
        departure_metadata("bk-1", factory)
        sql = cur.executed[0][0]
        assert "ExpectedDest IS NULL" in sql
        assert "FlightNumber IS NOT NULL" in sql

    def test_query_does_not_filter_on_expiry(self):
        """A completed trip's token has usually expired — that is the point.

        `get_cabin_trip` filters `ExpiresAt > GETDATE()`, which would return
        nothing for exactly the bookings this lookup exists to find.
        """
        factory, cur = _factory(rows=[("UA123",)])
        departure_metadata("bk-1", factory)
        assert "GETDATE()" not in cur.executed[0][0]

    def test_arrival_returns_none(self):
        factory, _ = _factory(rows=[])          # query filters it out server-side
        assert departure_metadata("bk-1", factory) is None

    def test_null_flight_number_returns_none(self):
        factory, _ = _factory(rows=[(None,)])
        assert departure_metadata("bk-1", factory) is None

    def test_schema_error_raises_rather_than_looking_empty(self):
        """Missing columns must not be indistinguishable from 'no departures'.

        If this returned None, a missing migration would silently stop every
        return being armed, and no counter or log anywhere would show it.
        """
        class _Boom:
            def cursor(self):
                raise RuntimeError("Invalid column name 'ExpectedDest'")

            def close(self):
                pass

        with pytest.raises(RuntimeError):
            departure_metadata("bk-1", lambda: _Boom())


# ── driver confirmation ──────────────────────────────────────────────────────
class TestCompleteOutboundTrip:
    def test_departure_arms_a_workflow(self, monkeypatch):
        monkeypatch.setattr(completion_mod, "departure_metadata",
                            lambda b, f: {"flight_number": "UA123"})
        store = _FakeStore()
        outcome = complete_outbound_trip("bk-1", store=store,
                                         connection_factory=lambda: None)
        assert outcome == CompletionOutcome.ARMED
        assert len(store.created) == 1
        assert store.created[0]["outbound_booking_id"] == "bk-1"

    def test_arrival_does_not_arm(self, monkeypatch):
        monkeypatch.setattr(completion_mod, "departure_metadata",
                            lambda b, f: None)
        store = _FakeStore()
        outcome = complete_outbound_trip("bk-1", store=store,
                                         connection_factory=lambda: None)
        assert outcome == CompletionOutcome.NOT_A_DEPARTURE
        assert store.created == []      # exact: not "no workflow armed" by luck

    def test_double_tap_is_a_no_op(self, monkeypatch):
        """create_workflow returns None when a claim already exists."""
        monkeypatch.setattr(completion_mod, "departure_metadata",
                            lambda b, f: {"flight_number": "UA123"})
        store = _FakeStore(create_returns=None)
        outcome = complete_outbound_trip("bk-1", store=store,
                                         connection_factory=lambda: None)
        assert outcome == CompletionOutcome.ALREADY_ACTIVE
        assert store.audits == []       # no second "completed" audit row

    def test_only_persisted_fields_are_passed_to_create(self, monkeypatch):
        """create_workflow SILENTLY IGNORES unknown keys.

        It reads its **fields by snake_case name, so a PascalCase or invented
        key is not an error — the value simply never reaches a column. This
        pins the call to keys the store actually persists.
        """
        monkeypatch.setattr(completion_mod, "departure_metadata",
                            lambda b, f: {"flight_number": "UA123"})
        store = _FakeStore()
        complete_outbound_trip("bk-1", store=store, connection_factory=lambda: None)
        assert set(store.created[0]) <= {
            "outbound_booking_id", "status", "correlation_id"}

    def test_outbound_flight_goes_to_the_audit_trail(self, monkeypatch):
        monkeypatch.setattr(completion_mod, "departure_metadata",
                            lambda b, f: {"flight_number": "UA123"})
        store = _FakeStore()
        complete_outbound_trip("bk-1", store=store, connection_factory=lambda: None)
        _, event, kw = store.audits[0]
        assert event == "OutboundTripCompleted"
        assert kw["detail"]["outboundFlight"] == "UA123"
        assert kw["detail"]["source"] == "DriverConfirmed"

    def test_missing_booking_id_is_rejected(self):
        assert complete_outbound_trip("", store=_FakeStore(),
                                      connection_factory=lambda: None) \
            == CompletionOutcome.UNKNOWN_BOOKING


# ── safety net ───────────────────────────────────────────────────────────────
class TestSafetyNet:
    def test_cutoff_is_exactly_the_configured_window(self):
        factory, cur = _factory(rows=[])
        find_unconfirmed(factory, now=NOW)
        params = cur.executed[0][1]
        assert NOW - timedelta(hours=SAFETY_NET_HOURS) in params

    def test_sweep_query_excludes_already_claimed(self):
        """Without NOT EXISTS the sweep re-offers every trip ever taken,
        forever, on every tick."""
        factory, cur = _factory(rows=[])
        find_unconfirmed(factory, now=NOW)
        sql = cur.executed[0][0]
        assert "NOT EXISTS" in sql
        assert "ReturnTripActiveClaim" in sql

    def test_sweep_is_bounded(self):
        factory, cur = _factory(rows=[])
        find_unconfirmed(factory, now=NOW, limit=7)
        assert "TOP (?)" in cur.executed[0][0]
        assert cur.executed[0][1][0] == 7

    def test_sweep_uses_the_same_departure_predicate(self):
        factory, cur = _factory(rows=[])
        find_unconfirmed(factory, now=NOW)
        sql = cur.executed[0][0]
        assert "ExpectedDest IS NULL" in sql
        assert "FlightNumber IS NOT NULL" in sql

    def test_one_bad_booking_does_not_abandon_the_batch(self, monkeypatch):
        monkeypatch.setattr(completion_mod, "find_unconfirmed",
                            lambda f, now=None, limit=None: ["bad", "good"])

        def _meta(booking_id, _factory):
            if booking_id == "bad":
                raise RuntimeError("boom")
            return {"flight_number": "UA1"}

        monkeypatch.setattr(completion_mod, "departure_metadata", _meta)
        store = _FakeStore()
        counts = sweep_unconfirmed(store=store, connection_factory=lambda: None)
        assert counts["Errors"] == 1
        assert counts[CompletionOutcome.ARMED] == 1

    def test_safety_net_is_tagged_distinctly_from_driver_taps(self, monkeypatch):
        monkeypatch.setattr(completion_mod, "find_unconfirmed",
                            lambda f, now=None, limit=None: ["bk-1"])
        monkeypatch.setattr(completion_mod, "departure_metadata",
                            lambda b, f: {"flight_number": "UA1"})
        store = _FakeStore()
        sweep_unconfirmed(store=store, connection_factory=lambda: None)
        assert store.audits[0][2]["detail"]["source"] == "SafetyNet"


# ── reminder worker ──────────────────────────────────────────────────────────
class TestReminderWorker:
    def test_queues_and_advances_in_one_call(self):
        store = _FakeStore(workflow=_workflow())
        assert dispatch_one("wf-1", store=store) is True
        assert len(store.enqueued) == 1
        call = store.enqueued[0]
        assert call["event_type"] == REMINDER_EVENT
        assert call["from_state"] is WorkflowState.REMINDER_DISPATCHING
        assert call["to_state"] is WorkflowState.REMINDER_SENT

    def test_enqueue_and_transition_carries_the_version_guard(self):
        """Advancing without the claimed version lets a concurrent writer's
        change be overwritten silently."""
        store = _FakeStore(workflow=_workflow(version=9))
        dispatch_one("wf-1", store=store)
        assert store.enqueued[0]["expected_version"] == 9

    def test_payload_reverses_the_journey(self):
        store = _FakeStore(workflow=_workflow())
        dispatch_one("wf-1", store=store)
        payload = store.enqueued[0]["payload"]
        assert payload["returnPickupAirport"] == "COS"
        assert payload["returnDropoffText"] == "123 Main St"

    def test_failed_enqueue_releases_the_claim(self):
        """A claimed row nobody releases is a reminder nothing will ever retry."""
        store = _FakeStore(workflow=_workflow(),
                           enqueue_raises=RuntimeError("db down"))
        assert dispatch_one("wf-1", store=store) is False
        assert len(store.transitions) == 1
        _, kw = store.transitions[0]
        assert kw["to_state"] is WorkflowState.REMINDER_SCHEDULED

    def test_missing_email_fails_rather_than_silently_skipping(self):
        store = _FakeStore(workflow=_workflow(passenger_email=None))
        assert dispatch_one("wf-1", store=store) is False
        _, kw = store.transitions[0]
        assert kw["to_state"] is WorkflowState.FAILED
        assert store.enqueued == []

    def test_row_moved_by_someone_else_is_left_alone(self):
        """Not ours to send, and not ours to release."""
        store = _FakeStore(workflow=_workflow(status=WorkflowState.CANCELED))
        assert dispatch_one("wf-1", store=store) is False
        assert store.transitions == []
        assert store.enqueued == []

    def test_vanished_workflow_is_not_an_exception(self):
        store = _FakeStore(workflow=None)
        assert dispatch_one("wf-1", store=store) is False

    def test_run_once_reports_queued_and_failed_separately(self):
        """A pass that claimed rows and queued none must not look like a quiet
        pass — the counts are the run's only observable output."""
        store = _FakeStore(workflow=_workflow(passenger_email=None),
                           claimed=["wf-1", "wf-2"])
        result = run_once(store=store)
        assert result == {"claimed": 2, "queued": 0, "failed": 2}

    def test_run_once_counts_successes(self):
        store = _FakeStore(workflow=_workflow(), claimed=["wf-1"])
        assert run_once(store=store) == {"claimed": 1, "queued": 1, "failed": 0}

    def test_unexpected_raise_does_not_abandon_the_batch(self, monkeypatch):
        calls = {"n": 0}

        def _boom(workflow_id, *, store):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("unexpected")
            return True

        monkeypatch.setattr(worker_mod, "dispatch_one", _boom)
        store = _FakeStore(claimed=["wf-1", "wf-2"])
        result = run_once(store=store)
        assert result == {"claimed": 2, "queued": 1, "failed": 1}
