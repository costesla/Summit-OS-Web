"""
Return-trip persistence (stage 2).

The database is the source of truth for this workflow, so these tests are about
the guarantees that make that claim true: a replayed completion event doesn't
create a second workflow, two workers don't send the same passenger the same
email, a concurrent confirmation doesn't silently overwrite, and a side effect
queued alongside a booking commits with it or not at all.

The connection is faked (same approach as test_cabin_trip.py). That means these
prove the REPOSITORY LOGIC and the SQL's shape — not that SQL Server accepts the
DDL. There is no database in this environment to execute it against; the DDL is
reviewed, not executed. See the note in the PR.
"""
import os
import sys
from datetime import date, datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.return_trip.flight_types import (  # noqa: E402
    Airport, FlightOccurrence, FlightStatus, FlightTelemetry,
)
from services.return_trip.states import (  # noqa: E402
    TelemetryState, WorkflowState,
)
from services.return_trip.errors import InvalidStateTransition  # noqa: E402
from services.return_trip.store import (  # noqa: E402
    OUTBOX_BACKOFF_MINUTES, ReturnTripStore, SCHEMA,
)


class FakeIntegrityError(Exception):
    """Stands in for pyodbc.IntegrityError (duplicate key)."""


class _Cursor:
    def __init__(self, rows=None, rowcount=1, duplicate_on=None):
        self.executed = []
        self._rows = list(rows or [])
        self.rowcount = rowcount
        self._duplicate_on = duplicate_on

    def execute(self, sql, params=None):
        flat = " ".join(sql.split())
        self.executed.append((flat, params))
        if self._duplicate_on and self._duplicate_on in flat:
            raise FakeIntegrityError("duplicate key")

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
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        pass


def _store(cursor, monkeypatch):
    # The store catches pyodbc.IntegrityError; point that at our fake.
    import services.return_trip.store as store_mod
    monkeypatch.setattr(store_mod, "_integrity_errors", lambda: (FakeIntegrityError,))
    conn = _Conn(cursor)
    return ReturnTripStore(connection_factory=lambda: conn), conn


def _sql(cursor, fragment):
    return [(s, p) for s, p in cursor.executed if fragment in s]


def _inserts(cursor, table):
    """Only the INSERTs into a table — `ensure_schema` also names every table
    in its DDL, so a bare substring match picks up CREATE TABLE too."""
    return _sql(cursor, f"INSERT INTO {SCHEMA}.{table}")


NOW = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)


# ── schema ───────────────────────────────────────────────────────────────────
class TestSchema:
    def test_every_statement_is_idempotent(self, monkeypatch):
        # ensure_schema runs on every write path, so a non-idempotent statement
        # would fail the second request rather than at deploy time.
        cur = _Cursor()
        store, _ = _store(cur, monkeypatch)
        store.ensure_schema()
        assert cur.executed
        for sql, _ in cur.executed:
            assert "IF NOT EXISTS" in sql or "IF OBJECT_ID" in sql \
                or "IF SCHEMA_ID" in sql, sql

    def test_timestamps_are_utc_typed(self, monkeypatch):
        cur = _Cursor()
        store, _ = _store(cur, monkeypatch)
        store.ensure_schema()
        ddl = " ".join(s for s, _ in cur.executed)
        assert "DATETIME2" in ddl
        # DATETIME (no precision) silently truncates and is the older type.
        assert "DATETIME(" not in ddl

    def test_soft_delete_not_hard_delete(self, monkeypatch):
        # An audit trail that references a deleted workflow is worthless.
        cur = _Cursor()
        store, _ = _store(cur, monkeypatch)
        store.ensure_schema()
        ddl = " ".join(s for s, _ in cur.executed)
        assert "VoidedAtUtc" in ddl


# ── workflow creation ────────────────────────────────────────────────────────
class TestCreateWorkflow:
    def test_claims_uniqueness_before_writing_the_row(self, monkeypatch):
        cur = _Cursor()
        store, conn = _store(cur, monkeypatch)
        wf = store.create_workflow(outbound_booking_id="BK-1",
                                   passenger_email="a@example.com")

        assert wf is not None and wf.version == 1
        claim = _sql(cur, "ReturnTripActiveClaim")
        row = _sql(cur, "INSERT INTO Bookings.ReturnTripWorkflow")
        assert claim and row
        # Order matters: the claim must be attempted first, or a duplicate
        # completion event writes a workflow row before being rejected.
        assert cur.executed.index(claim[0]) < cur.executed.index(row[0])
        assert conn.committed

    def test_a_replayed_completion_event_is_a_no_op(self, monkeypatch):
        # Retries, redelivered webhooks and a driver double-tapping all land
        # here. A second workflow would mean a second reminder email.
        cur = _Cursor(duplicate_on="INSERT INTO Bookings.ReturnTripActiveClaim")
        store, conn = _store(cur, monkeypatch)
        assert store.create_workflow(outbound_booking_id="BK-1") is None
        assert conn.rolled_back
        assert not _sql(cur, "INSERT INTO Bookings.ReturnTripWorkflow")

    def test_creation_is_audited_in_the_same_transaction(self, monkeypatch):
        cur = _Cursor()
        store, _ = _store(cur, monkeypatch)
        store.create_workflow(outbound_booking_id="BK-1")
        audit = _inserts(cur, "ReturnWorkflowAuditEvent")
        assert audit and "ReturnWorkflowCreated" in str(audit[0][1])

    def test_the_airport_code_is_normalised(self, monkeypatch):
        cur = _Cursor()
        store, _ = _store(cur, monkeypatch)
        store.create_workflow(outbound_booking_id="BK-1",
                              original_dropoff_airport="  cos ")
        params = _sql(cur, "INSERT INTO Bookings.ReturnTripWorkflow")[0][1]
        assert "COS" in params

    def test_a_dead_database_raises_rather_than_returning_none(self, monkeypatch):
        # None means "already exists". Conflating that with an outage would
        # silently drop the return trip for every booking during the outage.
        store = ReturnTripStore(connection_factory=lambda: None)
        with pytest.raises(RuntimeError):
            store.create_workflow(outbound_booking_id="BK-1")


# ── transitions ──────────────────────────────────────────────────────────────
class TestTransition:
    def test_applies_a_legal_move_with_version_and_audit(self, monkeypatch):
        cur = _Cursor(rowcount=1)
        store, conn = _store(cur, monkeypatch)
        ok = store.transition("W-1", expected_version=3,
                              from_state=WorkflowState.REMINDER_SENT,
                              to_state=WorkflowState.FLIGHT_VERIFICATION_PENDING)
        assert ok and conn.committed
        sql, params = _sql(cur, "UPDATE Bookings.ReturnTripWorkflow")[0]
        assert "Version = Version + 1" in sql
        assert "Version = ?" in sql and "WorkflowStatus = ?" in sql
        assert 3 in params
        assert _inserts(cur, "ReturnWorkflowAuditEvent")

    def test_an_illegal_move_never_reaches_the_database(self, monkeypatch):
        # The state machine is the first guard; skipping verification must fail
        # before any SQL runs.
        cur = _Cursor()
        store, _ = _store(cur, monkeypatch)
        with pytest.raises(InvalidStateTransition):
            store.transition("W-1", expected_version=1,
                             from_state=WorkflowState.REMINDER_SENT,
                             to_state=WorkflowState.CONFIRMED)
        assert not cur.executed

    def test_losing_a_concurrency_race_reports_false(self, monkeypatch):
        # Two confirmations both read Version 3; only one writes Version 4.
        cur = _Cursor(rowcount=0)
        store, conn = _store(cur, monkeypatch)
        ok = store.transition("W-1", expected_version=3,
                              from_state=WorkflowState.FLIGHT_VERIFIED,
                              to_state=WorkflowState.CONFIRMATION_PROCESSING)
        assert ok is False
        assert conn.rolled_back and not conn.committed

    def test_a_lost_race_writes_no_audit_row(self, monkeypatch):
        cur = _Cursor(rowcount=0)
        store, _ = _store(cur, monkeypatch)
        store.transition("W-1", expected_version=3,
                         from_state=WorkflowState.FLIGHT_VERIFIED,
                         to_state=WorkflowState.CONFIRMATION_PROCESSING)
        assert not _inserts(cur, "ReturnWorkflowAuditEvent")

    @pytest.mark.parametrize("terminal", [
        WorkflowState.CANCELED, WorkflowState.EXPIRED,
    ])
    def test_reaching_a_dead_end_releases_the_claim(self, monkeypatch, terminal):
        # Otherwise a cancelled return would block the passenger from ever
        # being offered one again for that journey.
        cur = _Cursor(rowcount=1)
        store, _ = _store(cur, monkeypatch)
        store.transition("W-1", expected_version=1,
                         from_state=WorkflowState.REMINDER_SENT,
                         to_state=terminal)
        assert _sql(cur, "DELETE FROM Bookings.ReturnTripActiveClaim")

    def test_confirming_keeps_the_claim(self, monkeypatch):
        # A confirmed return must keep blocking a second one.
        cur = _Cursor(rowcount=1)
        store, _ = _store(cur, monkeypatch)
        store.transition("W-1", expected_version=1,
                         from_state=WorkflowState.CONFIRMATION_PROCESSING,
                         to_state=WorkflowState.CONFIRMED)
        assert not _sql(cur, "DELETE FROM Bookings.ReturnTripActiveClaim")

    def test_updatable_fields_are_whitelisted(self, monkeypatch):
        # These become column names in SQL; an unchecked key is an injection
        # point.
        cur = _Cursor(rowcount=1)
        store, _ = _store(cur, monkeypatch)
        with pytest.raises(ValueError):
            store.transition("W-1", expected_version=1,
                             from_state=WorkflowState.REMINDER_SENT,
                             to_state=WorkflowState.EXPIRED,
                             **{"WorkflowStatus = 'Confirmed' --": "x"})

    def test_a_whitelisted_field_is_applied(self, monkeypatch):
        cur = _Cursor(rowcount=1)
        store, _ = _store(cur, monkeypatch)
        store.transition("W-1", expected_version=1,
                         from_state=WorkflowState.REMINDER_DISPATCHING,
                         to_state=WorkflowState.REMINDER_SENT,
                         reminder_dispatched_at_utc=NOW)
        sql, params = _sql(cur, "UPDATE Bookings.ReturnTripWorkflow")[0]
        assert "ReminderDispatchedAtUtc = ?" in sql
        assert NOW in params


# ── reminder claiming ────────────────────────────────────────────────────────
class TestClaimDueReminders:
    def test_claims_in_a_single_statement(self, monkeypatch):
        # SELECT-then-UPDATE lets two workers email the same passenger twice.
        cur = _Cursor(rows=[("W-1",), ("W-2",)])
        store, _ = _store(cur, monkeypatch)
        claimed = store.claim_due_reminders(now=NOW, limit=5)

        assert claimed == ["W-1", "W-2"]
        updates = _sql(cur, "UPDATE TOP (?) Bookings.ReturnTripWorkflow")
        assert len(updates) == 1
        sql = updates[0][0]
        assert "OUTPUT inserted.WorkflowId" in sql
        assert "SET WorkflowStatus = ?" in sql

    def test_only_scheduled_and_due_rows_are_claimed(self, monkeypatch):
        cur = _Cursor(rows=[])
        store, _ = _store(cur, monkeypatch)
        store.claim_due_reminders(now=NOW)
        sql, params = _sql(cur, "UPDATE TOP (?)")[0]
        assert "WHERE WorkflowStatus = ?" in sql
        assert "ReminderDispatchAtUtc <= ?" in sql
        assert WorkflowState.REMINDER_SCHEDULED.value in params
        assert WorkflowState.REMINDER_DISPATCHING.value in params

    def test_expired_workflows_are_not_reminded(self, monkeypatch):
        # A link that has already lapsed shouldn't generate an email.
        cur = _Cursor(rows=[])
        store, _ = _store(cur, monkeypatch)
        store.claim_due_reminders(now=NOW)
        sql = _sql(cur, "UPDATE TOP (?)")[0][0]
        assert "ExpirationAtUtc IS NULL OR ExpirationAtUtc > ?" in sql

    def test_nothing_due_is_an_empty_list(self, monkeypatch):
        cur = _Cursor(rows=[])
        store, _ = _store(cur, monkeypatch)
        assert store.claim_due_reminders(now=NOW) == []


# ── verification ─────────────────────────────────────────────────────────────
def _occurrence():
    return FlightOccurrence(
        provider="flightaware-aeroapi", provider_flight_id="UAL1234-aug1",
        marketing_carrier="UA", marketing_number="1234",
        departure=Airport(iata="ORD", timezone_name="America/Chicago"),
        arrival=Airport(iata="COS", timezone_name="America/Denver"),
        scheduled_arrival_utc=datetime(2026, 8, 1, 21, tzinfo=timezone.utc),
        status=FlightStatus.SCHEDULED,
    )


class TestVerification:
    def test_stores_the_normalised_occurrence_not_a_raw_payload(self, monkeypatch):
        cur = _Cursor()
        store, _ = _store(cur, monkeypatch)
        store.save_verification(workflow_id="W-1", occurrence=_occurrence(),
                                ident_raw=" ua 1234 ", ident_normalized="UA1234",
                                service_date=date(2026, 8, 1))
        sql, params = _sql(cur, "INSERT INTO Bookings.ReturnFlightVerification")[0]
        assert "OccurrenceJson" in sql
        # The raw entry survives for audit alongside the normalised form.
        assert " ua 1234 " in params and "UA1234" in params

    def test_lookup_requires_ownership_expiry_and_non_consumption(self, monkeypatch):
        # All three in the WHERE clause: someone else's verification id must be
        # indistinguishable from one that never existed.
        cur = _Cursor(rows=[None])
        store, _ = _store(cur, monkeypatch)
        assert store.get_live_verification("V-1", "W-1") is None
        sql, params = _sql(cur, "FROM Bookings.ReturnFlightVerification")[0]
        assert "WHERE VerificationId = ? AND WorkflowId = ?" in sql
        assert "ConsumedAtUtc IS NULL" in sql
        assert "ExpiresAtUtc > ?" in sql
        assert "V-1" in params and "W-1" in params

    def test_a_live_verification_comes_back_parsed(self, monkeypatch):
        cur = _Cursor(rows=[(
            "V-1", "W-1", "flightaware-aeroapi", "UAL1234-aug1", "COS",
            datetime(2026, 8, 1, 21, tzinfo=timezone.utc), None,
            "America/Denver", '{"flightNumber": "UA1234"}',
        )])
        store, _ = _store(cur, monkeypatch)
        result = store.get_live_verification("V-1", "W-1")
        assert result["provider_flight_id"] == "UAL1234-aug1"
        assert result["occurrence"]["flightNumber"] == "UA1234"


# ── binding + telemetry ──────────────────────────────────────────────────────
def _telemetry(status=FlightStatus.ACTIVE, eta=None, gate=None):
    return FlightTelemetry(provider="p", provider_flight_id="UAL1234-aug1",
                           status=status, estimated_arrival_utc=eta,
                           arrival_gate=gate)


class TestBindingAndTelemetry:
    def test_binding_is_written_on_the_callers_cursor(self, monkeypatch):
        # It belongs inside the confirmation transaction: a booking without its
        # binding would never be monitored and nothing would notice.
        cur = _Cursor()
        store, conn = _store(cur, monkeypatch)
        binding_id = store.create_binding(
            cur, return_booking_id="RB-1", workflow_id="W-1",
            provider="p", provider_flight_id="UAL1234-aug1")
        assert binding_id
        assert _sql(cur, "INSERT INTO Bookings.BookingFlightBinding")
        # The store must NOT commit — the caller owns the transaction.
        assert not conn.committed

    def test_an_unchanged_poll_writes_no_snapshot(self, monkeypatch):
        # AeroAPI bills per call and each snapshot can push a calendar update.
        eta = datetime(2026, 8, 1, 21, tzinfo=timezone.utc)
        cur = _Cursor()
        store, _ = _store(cur, monkeypatch)
        wrote = store.record_snapshot(binding_id="B-1",
                                      telemetry=_telemetry(eta=eta),
                                      previous=_telemetry(eta=eta))
        assert wrote is False
        assert not _sql(cur, "INSERT INTO Bookings.FlightTelemetrySnapshot")
        # ...but the schedule still moves forward.
        assert _sql(cur, "UPDATE Bookings.BookingFlightBinding")

    def test_a_changed_eta_writes_a_snapshot(self, monkeypatch):
        cur = _Cursor()
        store, _ = _store(cur, monkeypatch)
        wrote = store.record_snapshot(
            binding_id="B-1",
            telemetry=_telemetry(eta=datetime(2026, 8, 1, 21, 40, tzinfo=timezone.utc)),
            previous=_telemetry(eta=datetime(2026, 8, 1, 21, tzinfo=timezone.utc)))
        assert wrote is True
        assert _sql(cur, "INSERT INTO Bookings.FlightTelemetrySnapshot")

    def test_the_first_poll_always_records(self, monkeypatch):
        cur = _Cursor()
        store, _ = _store(cur, monkeypatch)
        assert store.record_snapshot(binding_id="B-1", telemetry=_telemetry(),
                                     previous=None) is True

    def test_a_successful_poll_resets_the_failure_count(self, monkeypatch):
        cur = _Cursor()
        store, _ = _store(cur, monkeypatch)
        store.record_snapshot(binding_id="B-1", telemetry=_telemetry())
        sql = _sql(cur, "UPDATE Bookings.BookingFlightBinding")[0][0]
        assert "FailureCount = 0" in sql

    def test_a_failed_poll_does_not_touch_the_telemetry_state(self, monkeypatch):
        # A provider outage is not a fact about the aircraft. Writing a state
        # here is how an outage starts looking like a cancelled flight.
        cur = _Cursor()
        store, _ = _store(cur, monkeypatch)
        store.record_poll_failure(binding_id="B-1",
                                  next_check_at_utc=NOW + timedelta(minutes=10))
        sql = _sql(cur, "UPDATE Bookings.BookingFlightBinding")[0][0]
        assert "FailureCount = FailureCount + 1" in sql
        assert "TelemetryState" not in sql

    def test_telemetry_state_follows_the_observed_status(self, monkeypatch):
        cur = _Cursor()
        store, _ = _store(cur, monkeypatch)
        store.record_snapshot(binding_id="B-1",
                              telemetry=_telemetry(status=FlightStatus.LANDED))
        params = _sql(cur, "UPDATE Bookings.BookingFlightBinding")[0][1]
        assert TelemetryState.LANDED.value in params


# ── outbox ───────────────────────────────────────────────────────────────────
class TestOutbox:
    def test_enqueue_joins_the_callers_transaction(self, monkeypatch):
        # This is what makes the calendar a projection: the booking and the
        # intent to sync it commit together, or neither does.
        cur = _Cursor()
        store, conn = _store(cur, monkeypatch)
        outbox_id = store.enqueue(cur, event_type="CalendarHold",
                                  aggregate_id="RB-1", payload={"a": 1})
        assert outbox_id
        sql, params = _sql(cur, "INSERT INTO Bookings.OutboxEvent")[0]
        assert "'Pending'" in sql
        assert not conn.committed

    def test_claiming_is_one_statement_with_output(self, monkeypatch):
        cur = _Cursor(rows=[("O-1", "CalendarHold", "RB-1", '{"a": 1}', 1)])
        store, _ = _store(cur, monkeypatch)
        claimed = store.claim_outbox(now=NOW)

        assert claimed[0]["outbox_id"] == "O-1"
        assert claimed[0]["payload"] == {"a": 1}
        sql = _sql(cur, "UPDATE TOP (?) Bookings.OutboxEvent")[0][0]
        assert "OUTPUT inserted.OutboxId" in sql
        assert "Status = 'Processing'" in sql
        assert "AttemptCount = AttemptCount + 1" in sql

    def test_only_due_pending_rows_are_claimed(self, monkeypatch):
        cur = _Cursor(rows=[])
        store, _ = _store(cur, monkeypatch)
        store.claim_outbox(now=NOW)
        sql = _sql(cur, "UPDATE TOP (?) Bookings.OutboxEvent")[0][0]
        assert "WHERE Status = 'Pending' AND NextAttemptAtUtc <= ?" in sql

    def test_failures_back_off_then_dead_letter(self, monkeypatch):
        cur = _Cursor()
        store, _ = _store(cur, monkeypatch)

        assert store.fail_outbox("O-1", attempt=1, error="calendar 503") is True
        assert "Pending" in _sql(cur, "UPDATE Bookings.OutboxEvent")[0][1]

        cur.executed.clear()
        # Past the end of the backoff schedule it stops retrying forever.
        assert store.fail_outbox("O-1", attempt=len(OUTBOX_BACKOFF_MINUTES)) is False
        assert "Failed" in _sql(cur, "UPDATE Bookings.OutboxEvent")[0][1]

    def test_a_retry_clears_the_claim(self, monkeypatch):
        # Otherwise a row that failed mid-flight stays Processing forever.
        cur = _Cursor()
        store, _ = _store(cur, monkeypatch)
        store.fail_outbox("O-1", attempt=1)
        assert "ClaimedAtUtc = NULL" in _sql(cur, "UPDATE Bookings.OutboxEvent")[0][0]

    def test_errors_are_truncated(self, monkeypatch):
        # LastError is a message column, not somewhere to dump a provider payload.
        cur = _Cursor()
        store, _ = _store(cur, monkeypatch)
        store.fail_outbox("O-1", attempt=1, error="x" * 5000)
        params = _sql(cur, "UPDATE Bookings.OutboxEvent")[0][1]
        assert any(isinstance(p, str) and len(p) == 1000 for p in params)

    def test_completing_marks_done(self, monkeypatch):
        cur = _Cursor()
        store, _ = _store(cur, monkeypatch)
        store.complete_outbox("O-1")
        assert "Done" in _sql(cur, "UPDATE Bookings.OutboxEvent")[0][1]


# ── privacy ──────────────────────────────────────────────────────────────────
class TestPrivacy:
    def test_audit_details_are_caller_supplied_and_stay_structured(self, monkeypatch):
        cur = _Cursor()
        store, _ = _store(cur, monkeypatch)
        store.audit("W-1", "ReturnLinkOpened", detail={"source": "email"})
        params = _inserts(cur, "ReturnWorkflowAuditEvent")[0][1]
        assert '{"source": "email"}' in params

    def test_no_passenger_contact_reaches_the_logs(self, monkeypatch, caplog):
        # Emails and phone numbers live in columns, never in log lines.
        cur = _Cursor(duplicate_on="INSERT INTO Bookings.ReturnTripActiveClaim")
        store, _ = _store(cur, monkeypatch)
        with caplog.at_level("INFO"):
            store.create_workflow(outbound_booking_id="BK-1",
                                  passenger_email="ada@example.com",
                                  passenger_phone="555-0100",
                                  original_pickup_text="12 Private Road")
        logged = caplog.text
        assert "ada@example.com" not in logged
        assert "555-0100" not in logged
        assert "12 Private Road" not in logged
