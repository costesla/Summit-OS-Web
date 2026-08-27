"""
manual_ledger.py
================
Manual Ledger for Jackie & Luis — the single source of truth for what these
two people currently owe.

Why this module exists
----------------------
Both were previously driven by automatic producers:

  * Luis   — `payment_tracker._recompute_luis_chain` accrued $190/day ("Missed")
             into Finance.LuisBalanceLog, compounding to $4,670 and continuing
             to climb (including future-dated rows).
  * Jackie — legacy INV- invoice rows counted into the Receivables/Deferred
             total on the dashboards.

Both are now **ManualOnly**: no automatic path may create, mutate, or surface a
current amount due for them. Balances are driven exclusively by entries a human
logs here.

Design guarantees
-----------------
1. *Structural* legacy isolation. A displayed balance is an active baseline's
   OpeningBalance plus the net of entries carrying that BaselineID (FK). Legacy
   rows have no BaselineID, so no clock skew, replay, backfill, or back-dated
   insert can leak them into the balance. Isolation does not depend on dates.
2. Non-destructive. Nothing legacy is deleted or mutated. The reset to $0.00 is
   an opening baseline, never offsetting "correction" transactions.
3. Auditable. Edits append a new revision (the prior revision is superseded, not
   overwritten); voids are a state transition; there is no hard delete.
4. Exact money. `decimal.Decimal` end to end, DECIMAL(10,2) in SQL. No floats.

The pure helpers here (policy, validation, balance math) have no I/O so they can
be unit-tested without a database, matching this repo's test conventions.
"""

import datetime
import decimal
import json
import logging
import uuid
from decimal import Decimal

log = logging.getLogger(__name__)

TWOPLACES = Decimal("0.01")
MAX_ENTRY_AMOUNT = Decimal("100000.00")
MAX_NOTE_LEN = 500
MAX_IDEMPOTENCY_KEY_LEN = 120

ENTRY_TYPE_CHARGE = "Charge"
ENTRY_TYPE_PAYMENT = "Payment"
ENTRY_TYPE_CREDIT = "Credit"
#: Charge increases the balance; Payment and Credit decrease it.
VALID_ENTRY_TYPES = (ENTRY_TYPE_CHARGE, ENTRY_TYPE_PAYMENT, ENTRY_TYPE_CREDIT)
DECREASING_ENTRY_TYPES = (ENTRY_TYPE_PAYMENT, ENTRY_TYPE_CREDIT)

MODE_MANUAL_ONLY = "ManualOnly"
MODE_LEGACY = "Legacy"


class PersonKey:
    """Stable person identifiers.

    These are opaque keys, never display names. Nothing in this system may key
    policy off a free-text passenger name, note, address, or invoice
    description — those are user-editable and would silently break isolation.
    """

    JACKIE = "JACKIE"
    LUIS = "LUIS"


#: The people this implementation places under manual-ledger-only control.
#: Centralized so accrual producers and receivables queries share one decision.
MANUAL_ONLY_PERSON_KEYS = frozenset({PersonKey.JACKIE, PersonKey.LUIS})

#: Maps a legacy invoice RideID prefix token to a stable person key.
#: Rides.Rides has no customer FK; the RideID (`INV-<TOKEN>-...`) is the
#: structured record identifier available, and unlike a passenger-name column
#: it is part of the record's primary key rather than free text.
#: JACQUELYN is a known spelling variant of Jackie in historical invoice data.
LEGACY_INVOICE_TOKENS = {
    PersonKey.JACKIE: ("JACKIE", "JACQUELYN"),
    PersonKey.LUIS: ("LUIS",),
}


def is_manual_only(person_key: str) -> bool:
    """Single policy gate: is this person driven exclusively by the manual ledger?

    Every automatic producer (Luis accrual, recompute, backfill, repair) and
    every active-receivables query must consult this rather than testing names
    inline, so the decision cannot drift between call sites.
    """
    if not person_key:
        return False
    return str(person_key).strip().upper() in MANUAL_ONLY_PERSON_KEYS


def manual_only_invoice_tokens() -> tuple:
    """All legacy invoice tokens belonging to manual-only people."""
    tokens = []
    for person_key in sorted(MANUAL_ONLY_PERSON_KEYS):
        tokens.extend(LEGACY_INVOICE_TOKENS.get(person_key, ()))
    return tuple(tokens)


def manual_only_invoice_predicate(column: str = "RideID") -> str:
    """Shared SQL fragment excluding manual-only people from ACTIVE receivables.

    Used by every current-amount-due path (dashboard totals, API summaries,
    exports) so a person can never be hidden from one surface while still
    counted in another. History remains fully queryable without this predicate.
    """
    tokens = manual_only_invoice_tokens()
    if not tokens:
        return "1=1"
    return " AND ".join(f"{column} NOT LIKE 'INV-{token}-%'" for token in tokens)


# ── Validation (pure) ────────────────────────────────────────────────────────

class ValidationError(ValueError):
    """Raised when a caller-supplied manual-ledger payload is not acceptable."""


def parse_amount(raw) -> Decimal:
    """Parse a currency amount into an exact positive Decimal.

    Accepts str/int/Decimal. Floats are rejected outright: binary floats cannot
    represent cents exactly, and silently coercing one would defeat the point of
    using DECIMAL storage.
    """
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        raise ValidationError("amount is required")
    if isinstance(raw, float):
        raise ValidationError("amount must be sent as a string or integer, not a float")
    try:
        value = Decimal(str(raw).strip())
    except (decimal.InvalidOperation, ValueError):
        raise ValidationError("amount is not a valid decimal number")
    if not value.is_finite():
        raise ValidationError("amount must be a finite number")
    if value <= 0:
        raise ValidationError("amount must be greater than zero")
    if value.as_tuple().exponent < -2:
        raise ValidationError("amount supports at most 2 decimal places")
    if value > MAX_ENTRY_AMOUNT:
        raise ValidationError(f"amount exceeds the {MAX_ENTRY_AMOUNT} limit")
    return value.quantize(TWOPLACES, rounding=decimal.ROUND_HALF_UP)


def parse_person_key(raw) -> str:
    key = str(raw or "").strip().upper()
    if key not in MANUAL_ONLY_PERSON_KEYS:
        raise ValidationError("personKey must be one of: JACKIE, LUIS")
    return key


def parse_entry_type(raw) -> str:
    value = str(raw or "").strip().title()
    if value not in VALID_ENTRY_TYPES:
        raise ValidationError("entryType must be one of: Charge, Payment, Credit")
    return value


def parse_effective_date(raw) -> datetime.date:
    if isinstance(raw, datetime.date):
        return raw
    text = str(raw or "").strip()
    if not text:
        raise ValidationError("effectiveDate is required")
    try:
        parsed = datetime.datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        raise ValidationError("effectiveDate must be formatted YYYY-MM-DD")
    if not (datetime.date(2000, 1, 1) <= parsed <= datetime.date(2100, 1, 1)):
        raise ValidationError("effectiveDate is outside the supported range")
    return parsed


def parse_note(raw) -> str | None:
    if raw is None:
        return None
    note = str(raw).strip()
    if not note:
        return None
    if len(note) > MAX_NOTE_LEN:
        raise ValidationError(f"note exceeds {MAX_NOTE_LEN} characters")
    return note


def parse_idempotency_key(raw) -> str | None:
    if raw is None:
        return None
    key = str(raw).strip()
    if not key:
        return None
    if len(key) > MAX_IDEMPOTENCY_KEY_LEN:
        raise ValidationError(f"idempotencyKey exceeds {MAX_IDEMPOTENCY_KEY_LEN} characters")
    return key


def validate_entry_payload(payload: dict) -> dict:
    """Validate and normalize a create/edit payload. Raises ValidationError.

    Server-side and authoritative — the UI's own checks are a convenience only.
    """
    if not isinstance(payload, dict):
        raise ValidationError("request body must be a JSON object")
    return {
        "person_key": parse_person_key(payload.get("personKey")),
        "entry_type": parse_entry_type(payload.get("entryType")),
        "amount": parse_amount(payload.get("amount")),
        "effective_date": parse_effective_date(payload.get("effectiveDate")),
        "note": parse_note(payload.get("note")),
        "idempotency_key": parse_idempotency_key(payload.get("idempotencyKey")),
    }


# ── Balance math (pure) ──────────────────────────────────────────────────────

def signed_amount(entry_type: str, amount: Decimal) -> Decimal:
    """Charge increases the balance; Payment/Credit decrease it.

    Amounts are always stored as positive magnitudes — direction comes from the
    entry type alone, so a negative amount paired with `Payment` is impossible.
    """
    if entry_type in DECREASING_ENTRY_TYPES:
        return -amount
    return amount


def entry_counts_toward_balance(entry: dict) -> bool:
    """Only the current, non-voided revision of an entry affects the balance."""
    if entry.get("voided_at_utc") is not None:
        return False
    return bool(entry.get("is_current", True))


def compute_balance(opening_balance, entries) -> Decimal:
    """Opening baseline + net of qualifying entries.

    Callers must pass only entries belonging to the ACTIVE baseline; legacy rows
    have no BaselineID and are structurally incapable of appearing here.
    """
    total = Decimal(str(opening_balance or "0.00"))
    for entry in entries or []:
        if not entry_counts_toward_balance(entry):
            continue
        amount = entry.get("amount")
        amount = amount if isinstance(amount, Decimal) else Decimal(str(amount))
        total += signed_amount(entry.get("entry_type"), amount)
    return total.quantize(TWOPLACES, rounding=decimal.ROUND_HALF_UP)


# ── Persistence ──────────────────────────────────────────────────────────────

class ManualLedgerService:
    """DB-backed manual ledger. All money is DECIMAL; all writes are audited."""

    def __init__(self, db=None):
        if db is None:
            from services.database import DatabaseClient
            db = DatabaseClient()
        self.db = db

    # -- baseline ------------------------------------------------------------

    def get_active_baseline(self, person_key: str, cursor=None) -> dict | None:
        """The person's active ManualOnly baseline, or None if not activated."""
        sql = """
            SELECT TOP 1 BaselineID, PersonKey, OpeningBalance, Mode, ActivatedAtUtc
            FROM Finance.ManualLedgerBaseline
            WHERE PersonKey = ? AND IsActive = 1
        """
        if cursor is not None:
            cursor.execute(sql, person_key)
            row = cursor.fetchone()
            return self._baseline_row(row)
        conn = self.db.get_connection()
        if not conn:
            return None
        try:
            cur = conn.cursor()
            cur.execute(sql, person_key)
            return self._baseline_row(cur.fetchone())
        finally:
            conn.close()

    @staticmethod
    def _baseline_row(row) -> dict | None:
        if not row:
            return None
        return {
            "baseline_id": str(row[0]),
            "person_key": row[1],
            "opening_balance": Decimal(str(row[2])),
            "mode": row[3],
            "activated_at_utc": row[4],
        }

    def activate(self, person_key: str, actor: str = "migration",
                 opening_balance: Decimal = Decimal("0.00"),
                 legacy_cutoff_ref: str | None = None) -> str:
        """Deliberately activate a ManualOnly baseline. Idempotent per person.

        Never called at application startup — activation is an explicit
        migration/runbook step so a restart cannot flip production behavior.
        """
        person_key = parse_person_key(person_key)
        conn = self.db.get_connection()
        if not conn:
            raise RuntimeError("database unavailable")
        try:
            cur = conn.cursor()
            existing = self.get_active_baseline(person_key, cursor=cur)
            if existing:
                return existing["baseline_id"]
            baseline_id = str(uuid.uuid4())
            cur.execute(
                """INSERT INTO Finance.ManualLedgerBaseline
                   (BaselineID, PersonKey, OpeningBalance, Mode, IsActive, ActivatedBy, LegacyCutoffRef)
                   VALUES (?, ?, ?, ?, 1, ?, ?)""",
                baseline_id, person_key, opening_balance, MODE_MANUAL_ONLY, actor, legacy_cutoff_ref,
            )
            cur.execute(
                """INSERT INTO Finance.ManualLedgerAudit
                   (EntryID, EventType, NewValues, Actor, Reason)
                   VALUES (?, 'Activate', ?, ?, ?)""",
                baseline_id,
                json.dumps({"person_key": person_key, "opening_balance": str(opening_balance),
                            "mode": MODE_MANUAL_ONLY}),
                actor,
                "Manual ledger activation",
            )
            conn.commit()
            return baseline_id
        finally:
            conn.close()

    # -- entries -------------------------------------------------------------

    def list_entries(self, person_key: str, include_voided: bool = True, limit: int = 100) -> list:
        """Current revisions for a person, newest first. Deterministic ordering."""
        person_key = parse_person_key(person_key)
        baseline = self.get_active_baseline(person_key)
        if not baseline:
            return []
        conn = self.db.get_connection()
        if not conn:
            return []
        try:
            cur = conn.cursor()
            sql = """
                SELECT EntryID, PersonKey, EntryType, Amount, EffectiveDate, Note,
                       VoidedAtUtc, IsCurrent, RevisionNumber, CreatedAtUtc, UpdatedAtUtc
                FROM Finance.ManualLedgerEntry
                WHERE BaselineID = ? AND IsCurrent = 1
            """
            if not include_voided:
                sql += " AND VoidedAtUtc IS NULL"
            sql += " ORDER BY EffectiveDate DESC, CreatedAtUtc DESC, EntryID DESC"
            cur.execute(sql, baseline["baseline_id"])
            rows = cur.fetchall()[:limit]
            return [self._entry_row(r) for r in rows]
        finally:
            conn.close()

    @staticmethod
    def _entry_row(row) -> dict:
        return {
            "entry_id": str(row[0]),
            "person_key": row[1],
            "entry_type": row[2],
            "amount": Decimal(str(row[3])),
            "effective_date": row[4],
            "note": row[5],
            "voided_at_utc": row[6],
            "is_current": bool(row[7]),
            "revision_number": row[8],
            "created_at_utc": row[9],
            "updated_at_utc": row[10],
        }

    def get_balance(self, person_key: str) -> Decimal:
        """Authoritative balance: baseline opening + net of qualifying entries."""
        person_key = parse_person_key(person_key)
        baseline = self.get_active_baseline(person_key)
        if not baseline:
            return Decimal("0.00")
        entries = self.list_entries(person_key, include_voided=True, limit=100000)
        return compute_balance(baseline["opening_balance"], entries)

    def create_entry(self, payload: dict, actor: str = "unknown",
                     correlation_id: str | None = None) -> dict:
        """Create an entry. Replaying an idempotency key returns the original."""
        clean = validate_entry_payload(payload)
        person_key = clean["person_key"]
        baseline = self.get_active_baseline(person_key)
        if not baseline:
            raise ValidationError(f"manual ledger is not activated for {person_key}")

        conn = self.db.get_connection()
        if not conn:
            raise RuntimeError("database unavailable")
        try:
            cur = conn.cursor()
            if clean["idempotency_key"]:
                cur.execute(
                    """SELECT EntryID, PersonKey, EntryType, Amount, EffectiveDate, Note,
                              VoidedAtUtc, IsCurrent, RevisionNumber, CreatedAtUtc, UpdatedAtUtc
                       FROM Finance.ManualLedgerEntry WHERE IdempotencyKey = ?""",
                    clean["idempotency_key"],
                )
                existing = cur.fetchone()
                if existing:
                    replayed = self._entry_row(existing)
                    # Same key + different payload is a client bug, not a replay.
                    if (replayed["entry_type"] != clean["entry_type"]
                            or replayed["amount"] != clean["amount"]
                            or replayed["person_key"] != person_key):
                        raise ValidationError(
                            "idempotencyKey was already used with a different payload"
                        )
                    return replayed

            entry_id = str(uuid.uuid4())
            cur.execute(
                """INSERT INTO Finance.ManualLedgerEntry
                   (EntryID, BaselineID, PersonKey, EntryType, Amount, EffectiveDate,
                    Note, RootEntryID, RevisionNumber, IsCurrent, IdempotencyKey, CreatedBy)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1, ?, ?)""",
                entry_id, baseline["baseline_id"], person_key, clean["entry_type"],
                clean["amount"], clean["effective_date"], clean["note"], entry_id,
                clean["idempotency_key"], actor,
            )
            self._audit(cur, entry_id, "Create", None, {
                "person_key": person_key,
                "entry_type": clean["entry_type"],
                "amount": str(clean["amount"]),
                "effective_date": clean["effective_date"].isoformat(),
            }, actor, correlation_id)
            conn.commit()
            return {
                "entry_id": entry_id,
                "person_key": person_key,
                "entry_type": clean["entry_type"],
                "amount": clean["amount"],
                "effective_date": clean["effective_date"],
                "note": clean["note"],
                "voided_at_utc": None,
                "is_current": True,
                "revision_number": 1,
            }
        finally:
            conn.close()

    def edit_entry(self, entry_id: str, payload: dict, actor: str = "unknown",
                   correlation_id: str | None = None) -> dict:
        """Append a new revision; the prior revision is superseded, not overwritten."""
        clean = validate_entry_payload(payload)
        conn = self.db.get_connection()
        if not conn:
            raise RuntimeError("database unavailable")
        try:
            cur = conn.cursor()
            cur.execute(
                """SELECT EntryID, BaselineID, PersonKey, EntryType, Amount, EffectiveDate,
                          Note, RootEntryID, RevisionNumber, IsCurrent, VoidedAtUtc
                   FROM Finance.ManualLedgerEntry WHERE EntryID = ?""",
                entry_id,
            )
            row = cur.fetchone()
            if not row:
                raise ValidationError("entry not found")
            if not bool(row[9]):
                raise ValidationError("entry has already been superseded by a newer revision")
            if row[10] is not None:
                raise ValidationError("a voided entry cannot be edited")
            if row[2] != clean["person_key"]:
                raise ValidationError("an entry cannot be reassigned to another person")

            previous = {
                "entry_type": row[3], "amount": str(row[4]),
                "effective_date": str(row[5]), "note": row[6],
            }
            root_id = str(row[7]) if row[7] else str(row[0])
            new_id = str(uuid.uuid4())
            # Supersede only if still current — optimistic concurrency: a racing
            # edit flips IsCurrent first and this UPDATE then affects 0 rows.
            cur.execute(
                """UPDATE Finance.ManualLedgerEntry
                   SET IsCurrent = 0, UpdatedAtUtc = SYSUTCDATETIME()
                   WHERE EntryID = ? AND IsCurrent = 1""",
                entry_id,
            )
            if cur.rowcount != 1:
                conn.rollback()
                raise ValidationError("entry was modified concurrently; reload and retry")
            cur.execute(
                """INSERT INTO Finance.ManualLedgerEntry
                   (EntryID, BaselineID, PersonKey, EntryType, Amount, EffectiveDate,
                    Note, RootEntryID, RevisionNumber, IsCurrent, CreatedBy)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)""",
                new_id, str(row[1]), clean["person_key"], clean["entry_type"],
                clean["amount"], clean["effective_date"], clean["note"], root_id,
                int(row[8]) + 1, actor,
            )
            self._audit(cur, new_id, "Edit", previous, {
                "entry_type": clean["entry_type"],
                "amount": str(clean["amount"]),
                "effective_date": clean["effective_date"].isoformat(),
                "note": clean["note"],
                "supersedes": entry_id,
            }, actor, correlation_id)
            conn.commit()
            return {"entry_id": new_id, "supersedes": entry_id,
                    "revision_number": int(row[8]) + 1}
        finally:
            conn.close()

    def void_entry(self, entry_id: str, actor: str = "unknown", reason: str | None = None,
                   correlation_id: str | None = None) -> dict:
        """State transition, never a delete. Repeated voids are safe (no-op)."""
        conn = self.db.get_connection()
        if not conn:
            raise RuntimeError("database unavailable")
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT EntryID, VoidedAtUtc, IsCurrent FROM Finance.ManualLedgerEntry WHERE EntryID = ?",
                entry_id,
            )
            row = cur.fetchone()
            if not row:
                raise ValidationError("entry not found")
            if row[1] is not None:
                return {"entry_id": entry_id, "voided": True, "already_voided": True}
            cur.execute(
                """UPDATE Finance.ManualLedgerEntry
                   SET VoidedAtUtc = SYSUTCDATETIME(), VoidedBy = ?, UpdatedAtUtc = SYSUTCDATETIME()
                   WHERE EntryID = ? AND VoidedAtUtc IS NULL""",
                actor, entry_id,
            )
            self._audit(cur, entry_id, "Void", None, {"voided": True}, actor, correlation_id, reason)
            conn.commit()
            return {"entry_id": entry_id, "voided": True, "already_voided": False}
        finally:
            conn.close()

    @staticmethod
    def _audit(cursor, entry_id, event_type, previous, new, actor,
               correlation_id=None, reason=None):
        cursor.execute(
            """INSERT INTO Finance.ManualLedgerAudit
               (EntryID, EventType, PreviousValues, NewValues, Actor, CorrelationID, Reason)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            entry_id, event_type,
            json.dumps(previous) if previous else None,
            json.dumps(new) if new else None,
            actor, correlation_id, reason,
        )
