"""
Return-trip token service, resolve and confirm (stage 4).

The token is the passenger's entire credential — there is no account behind it
— so most of what follows is about the ways a token can be more powerful than
intended: readable from a database dump, usable after confirmation, usable to
spend our AeroAPI budget, or usable to confirm a flight other than the one that
was verified.

Connections are faked, same approach as stages 1–3.
"""
import os
import sys
from datetime import date, datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.return_trip import booking_service as bs_mod  # noqa: E402
from services.return_trip.booking_service import (  # noqa: E402
    ReturnTripBookingService,
)
from services.return_trip.errors import (  # noqa: E402
    AmbiguousFlightOccurrence, FlightNotFound, InvalidOrExpiredToken,
    RateLimitExceeded, ReturnBookingAlreadyExists,
)
from services.return_trip.flight_types import (  # noqa: E402
    Airport, FlightOccurrence,
)
from services.return_trip.states import WorkflowState  # noqa: E402
from services.return_trip.store import Workflow  # noqa: E402
from services.return_trip.tokens import (  # noqa: E402
    MAX_RESOLVES_PER_WORKFLOW, TokenService, hash_token, new_token,
)

NOW = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
SERVICE_DATE = date(2026, 8, 14)


class _Cursor:
    def __init__(self, rows=None, rowcount=1):
        self.executed = []
        self._rows = list(rows or [])
        self.rowcount = rowcount

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


def _tokens(rows=None, rowcount=1):
    cur = _Cursor(rows, rowcount)
    conn = _Conn(cur)
    return TokenService(connection_factory=lambda: conn), cur, conn


def _sql(cur, fragment):
    return [(s, p) for s, p in cur.executed if fragment in s]


# ── token hygiene ────────────────────────────────────────────────────────────
class TestTokenService:
    def test_raw_token_is_never_stored(self):
        svc, cur, _ = _tokens()
        raw = svc.issue("wf-1")
        inserts = _sql(cur, "INSERT INTO Bookings.ReturnTripLinkToken")
        assert len(inserts) == 1
        params = inserts[0][1]
        assert raw not in params, "raw token must never reach the database"
        assert hash_token(raw) in params

    def test_tokens_are_high_entropy_and_unique(self):
        seen = {new_token() for _ in range(200)}
        assert len(seen) == 200
        assert all(len(t) >= 40 for t in seen)

    def test_issue_revokes_any_previous_live_token(self):
        """A resent reminder must not leave two working links."""
        svc, cur, _ = _tokens()
        svc.issue("wf-1")
        revokes = _sql(cur, "UPDATE Bookings.ReturnTripLinkToken SET RevokedAtUtc")
        assert len(revokes) == 1

    def test_resolve_filters_expiry_and_revocation_in_sql(self):
        """Checked in the WHERE clause, not after the fetch — otherwise
        'exists but expired' becomes distinguishable from 'never existed'."""
        svc, cur, _ = _tokens(rows=[("wf-1", 0)])
        svc.resolve("raw")
        sql = _sql(cur, "SELECT WorkflowId, ResolveCount")[0][0]
        assert "RevokedAtUtc IS NULL" in sql
        assert "ExpiresAtUtc > ?" in sql

    def test_resolve_looks_up_by_hash_not_raw(self):
        svc, cur, _ = _tokens(rows=[("wf-1", 0)])
        svc.resolve("raw-value")
        params = _sql(cur, "SELECT WorkflowId, ResolveCount")[0][1]
        assert hash_token("raw-value") in params
        assert "raw-value" not in params

    def test_unknown_token_resolves_to_none(self):
        svc, _, _ = _tokens(rows=[])
        assert svc.resolve("nope") is None

    def test_empty_token_short_circuits(self):
        svc, cur, _ = _tokens()
        assert svc.resolve("") is None
        assert cur.executed == []


# ── the AeroAPI budget ───────────────────────────────────────────────────────
class TestResolveBudget:
    def test_charge_is_one_conditional_update(self):
        """Read-then-write would let two concurrent requests both pass the cap.
        Whoever's UPDATE matches the predicate gets the budget."""
        svc, cur, _ = _tokens(rowcount=1)
        assert svc.charge_resolve("raw") is True
        updates = _sql(cur, "SET ResolveCount = ResolveCount + 1")
        assert len(updates) == 1
        assert "ResolveCount < ?" in updates[0][0]
        assert MAX_RESOLVES_PER_WORKFLOW in updates[0][1]

    def test_over_budget_returns_false(self):
        svc, _, _ = _tokens(rowcount=0)
        assert svc.charge_resolve("raw") is False

    def test_budget_check_also_enforces_expiry(self):
        """An expired token must not still be able to spend money."""
        svc, cur, _ = _tokens(rowcount=1)
        svc.charge_resolve("raw")
        sql = _sql(cur, "SET ResolveCount = ResolveCount + 1")[0][0]
        assert "ExpiresAtUtc > ?" in sql
        assert "RevokedAtUtc IS NULL" in sql


# ── resolve flow ─────────────────────────────────────────────────────────────
class _FakeTokens:
    def __init__(self, workflow_id="wf-1", charge=True):
        self._workflow_id = workflow_id
        self._charge = charge
        self.charges = 0
        self.revoked = []

    def resolve(self, raw):
        return {"workflow_id": self._workflow_id} if raw == "good" else None

    def charge_resolve(self, raw):
        self.charges += 1
        return self._charge

    def revoke(self, workflow_id):
        self.revoked.append(workflow_id)


class _FakeStore:
    def __init__(self, workflow=None, verification=None, confirm_result=None):
        self._workflow = workflow
        self._verification = verification
        self._confirm_result = confirm_result
        self.saved = []
        self.transitions = []
        self.confirms = []

    def get_workflow(self, workflow_id):
        return self._workflow

    def save_verification(self, **kw):
        self.saved.append(kw)
        return "ver-1"

    def transition(self, workflow_id, **kw):
        self.transitions.append(kw)
        return True

    def get_live_verification(self, verification_id, workflow_id):
        return self._verification

    def confirm_return_trip(self, **kw):
        self.confirms.append(kw)
        return self._confirm_result


def _Occurrence(number="123", provider_flight_id="fa-1"):
    """A REAL FlightOccurrence, not a stand-in.

    An earlier version of this file used a hand-rolled fake with an `ident`
    attribute the real dataclass does not have. Every test passed and
    `resolve_flight` would have raised AttributeError on its first successful
    lookup in production. Using the real type is what stops a fake drifting
    away from the thing it stands for.
    """
    return FlightOccurrence(
        provider="aeroapi", provider_flight_id=provider_flight_id,
        marketing_carrier="UA", marketing_number=number,
        departure=Airport(iata="SFO"), arrival=Airport(iata="COS"),
        scheduled_arrival_utc=NOW, estimated_arrival_utc=NOW,
    )


class _Provider:
    def __init__(self, occurrences):
        self._occurrences = occurrences
        self.calls = 0

    def resolve_flight_occurrence(self, *, ident, service_date):
        self.calls += 1
        return self._occurrences


def _workflow(status=WorkflowState.REMINDER_SENT, version=2):
    return Workflow(workflow_id="wf-1", outbound_booking_id="bk-1",
                    status=status, version=version,
                    passenger_email="p@example.com",
                    original_pickup_text="123 Main St",
                    original_dropoff_airport="COS")


def _service(*, workflow=None, occurrences=None, charge=True,
             verification=None, confirm_result=None):
    tokens = _FakeTokens(charge=charge)
    store = _FakeStore(workflow=workflow or _workflow(),
                       verification=verification,
                       confirm_result=confirm_result)
    provider = _Provider(occurrences if occurrences is not None else [_Occurrence()])
    return ReturnTripBookingService(store=store, tokens=tokens,
                                    provider=provider), store, tokens, provider


class TestResolveFlight:
    def test_bad_token_is_rejected_before_anything_else(self):
        svc, store, tokens, provider = _service()
        with pytest.raises(InvalidOrExpiredToken):
            svc.resolve_flight("bad", flight_number="UA123",
                               service_date=SERVICE_DATE)
        assert tokens.charges == 0
        assert provider.calls == 0

    def test_malformed_flight_number_does_not_spend_budget(self):
        """A typo is the passenger's to fix and must cost neither of us."""
        svc, _, tokens, provider = _service()
        with pytest.raises(Exception):
            svc.resolve_flight("good", flight_number="!!!",
                               service_date=SERVICE_DATE)
        assert tokens.charges == 0
        assert provider.calls == 0

    def test_budget_is_charged_before_the_provider_call(self):
        """Charging after would let a slow or erroring provider be hammered
        for free."""
        svc, _, tokens, provider = _service(charge=False)
        with pytest.raises(RateLimitExceeded):
            svc.resolve_flight("good", flight_number="UA123",
                               service_date=SERVICE_DATE)
        assert tokens.charges == 1
        assert provider.calls == 0

    def test_single_occurrence_saves_a_verification(self):
        svc, store, _, _ = _service()
        out = svc.resolve_flight("good", flight_number="UA123",
                                 service_date=SERVICE_DATE)
        assert out["verificationId"] == "ver-1"
        assert len(store.saved) == 1

    def test_ambiguous_returns_candidates_and_saves_nothing(self):
        svc, store, _, _ = _service(occurrences=[_Occurrence(), _Occurrence()])
        with pytest.raises(AmbiguousFlightOccurrence) as exc:
            svc.resolve_flight("good", flight_number="UA123",
                               service_date=SERVICE_DATE)
        assert len(exc.value.details["candidates"]) == 2
        assert store.saved == []

    def test_no_occurrence_is_flight_not_found(self):
        svc, store, _, _ = _service(occurrences=[])
        with pytest.raises(FlightNotFound):
            svc.resolve_flight("good", flight_number="UA123",
                               service_date=SERVICE_DATE)
        assert store.saved == []

    def test_candidates_carry_no_provider_ids(self):
        """Passenger-facing payloads must not leak our provider's identifiers."""
        svc, _, _, _ = _service()
        out = svc.resolve_flight("good", flight_number="UA123",
                                 service_date=SERVICE_DATE)
        blob = str(out["flight"])
        assert "fa-1" not in blob
        assert "aeroapi" not in blob

    def test_confirmed_workflow_cannot_resolve_again(self):
        svc, _, tokens, provider = _service(
            workflow=_workflow(status=WorkflowState.CONFIRMED))
        with pytest.raises(ReturnBookingAlreadyExists):
            svc.resolve_flight("good", flight_number="UA123",
                               service_date=SERVICE_DATE)
        assert tokens.charges == 0
        assert provider.calls == 0


class TestConfirm:
    def test_confirm_uses_the_stored_verification_not_client_flight(self):
        """The client sends an id; the flight comes from OUR row.

        Otherwise a client could verify one flight and confirm another, and
        the binding would look entirely consistent afterwards.
        """
        svc, store, _, _ = _service(
            verification={"provider": "aeroapi", "provider_flight_id": "fa-9"},
            confirm_result={"binding_id": "bind-1"})
        svc.confirm("good", verification_id="ver-1")
        assert store.confirms[0]["provider_flight_id"] == "fa-9"

    def test_unusable_verification_is_rejected(self):
        svc, _, _, _ = _service(verification=None)
        with pytest.raises(InvalidOrExpiredToken):
            svc.confirm("good", verification_id="ver-1")

    def test_already_confirmed_is_a_replay_not_an_error(self):
        svc, store, _, _ = _service(
            workflow=_workflow(status=WorkflowState.CONFIRMED))
        out = svc.confirm("good", verification_id="ver-1")
        assert out["alreadyConfirmed"] is True
        assert store.confirms == []

    def test_lost_race_raises_rather_than_reporting_success(self):
        svc, _, _, _ = _service(
            verification={"provider": "aeroapi", "provider_flight_id": "fa-9"},
            confirm_result=None)
        with pytest.raises(ReturnBookingAlreadyExists):
            svc.confirm("good", verification_id="ver-1")

    def test_successful_confirm_revokes_the_link(self):
        """A live link to a confirmed workflow can only fail confusingly."""
        svc, _, tokens, _ = _service(
            verification={"provider": "aeroapi", "provider_flight_id": "fa-9"},
            confirm_result={"binding_id": "bind-1"})
        svc.confirm("good", verification_id="ver-1")
        assert tokens.revoked == ["wf-1"]

    def test_revoke_failure_does_not_undo_the_confirmation(self):
        """The trip is booked; a failed cleanup must not report failure."""
        svc, _, tokens, _ = _service(
            verification={"provider": "aeroapi", "provider_flight_id": "fa-9"},
            confirm_result={"binding_id": "bind-1"})

        def _boom(_wf):
            raise RuntimeError("db blip")

        tokens.revoke = _boom
        out = svc.confirm("good", verification_id="ver-1")
        assert out["bindingId"] == "bind-1"

    def test_bad_token_never_reaches_the_store(self):
        svc, store, _, _ = _service()
        with pytest.raises(InvalidOrExpiredToken):
            svc.confirm("bad", verification_id="ver-1")
        assert store.confirms == []
