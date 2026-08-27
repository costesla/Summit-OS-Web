"""
Return-trip link tokens.

The token IS the passenger's identity here. There is no account model (findings
§2.2), so a valid token means "whoever holds this is the person we emailed",
and it must therefore carry no PII and be unguessable rather than merely
obscure.

**Stored hashed, unlike `Rides.CabinTokens`.** That divergence is deliberate.
A cabin token is a six-digit code a human reads off a screen and types at a
car; its entropy is low by necessity and it is defended by a lockout. This one
is clicked from an email and never typed, so there is no reason to keep it
short — and being a high-entropy bearer credential, the interesting question is
what a database leak yields. Plaintext would hand over working links that can
book trips. A SHA-256 hash yields nothing usable: the raw value exists only in
the email we already sent.

No salt and no KDF, on purpose. Salting defeats the lookup this table exists
for, and a 256-bit random token has nothing to brute-force — the slow-hash
argument applies to human-chosen passwords, not to `secrets.token_urlsafe(32)`.
"""
import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

SCHEMA = "Bookings"

# 32 bytes → 43 url-safe chars. Long enough that guessing is not a threat model
# and the lockout below exists for cost, not for brute force.
TOKEN_BYTES = 32

# How long a reminder link stays usable. Matches the workflow's own expiry
# horizon: a link that outlives its workflow is a dead end the passenger cannot
# tell apart from a broken site.
TOKEN_TTL_DAYS = 14

# Resolve attempts allowed per workflow. This is a COST control, not an
# anti-guessing one: every resolve is a billed AeroAPI call, and the holder of
# a valid token would otherwise set our bill. Generous enough for a passenger
# who mistypes a flight number several times and tries a few variants.
MAX_RESOLVES_PER_WORKFLOW = 20


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_token() -> str:
    """A fresh raw token. Returned once, never stored in this form."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(raw: str) -> str:
    """SHA-256 hex of the raw token. Deterministic, so it can be looked up."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)


_DDL = (
    f"IF OBJECT_ID('{SCHEMA}.ReturnTripLinkToken') IS NULL "
    f"CREATE TABLE {SCHEMA}.ReturnTripLinkToken ("
    "TokenHash NVARCHAR(64) NOT NULL PRIMARY KEY, "
    "WorkflowId NVARCHAR(64) NOT NULL, "
    "ResolveCount INT NOT NULL DEFAULT 0, "
    "ExpiresAtUtc DATETIME2 NOT NULL, "
    "RevokedAtUtc DATETIME2 NULL, "
    "LastUsedAtUtc DATETIME2 NULL, "
    "CreatedAtUtc DATETIME2 NOT NULL)",

    # One live token per workflow. A filtered unique index rather than a plain
    # one so that reissuing after a revoke is still possible.
    f"IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'UQ_ReturnTripLinkToken_Workflow') "
    f"CREATE UNIQUE INDEX UQ_ReturnTripLinkToken_Workflow "
    f"ON {SCHEMA}.ReturnTripLinkToken (WorkflowId) WHERE RevokedAtUtc IS NULL",
)


class TokenService:
    """Issue, resolve and meter return-trip link tokens."""

    def __init__(self, connection_factory=None):
        if connection_factory is None:
            from services.database import DatabaseClient
            connection_factory = DatabaseClient().get_connection
        self._connect = connection_factory

    def ensure_schema(self, cursor=None) -> None:
        owned = cursor is None
        conn = None
        if owned:
            conn = self._connect()
            if not conn:
                raise RuntimeError("Database unavailable")
            cursor = conn.cursor()
        try:
            for statement in _DDL:
                cursor.execute(statement)
            if owned:
                conn.commit()
        finally:
            if owned and conn is not None:
                cursor.close()
                conn.close()

    def issue(self, workflow_id: str, *, ttl_days: int = TOKEN_TTL_DAYS) -> str:
        """Mint a token for a workflow and return the RAW value.

        The raw value is returned exactly once, to be put in the email. It is
        not recoverable afterwards — that is the point of storing the hash.
        """
        raw = new_token()
        now = _utcnow()
        conn = self._connect()
        if not conn:
            raise RuntimeError("Database unavailable")
        cur = conn.cursor()
        try:
            self.ensure_schema(cur)
            # Revoke any previous live token first: reissuing (a resend of the
            # reminder) must not leave two working links, or revoking the one
            # the passenger complained about would silently leave the other.
            cur.execute(
                f"UPDATE {SCHEMA}.ReturnTripLinkToken SET RevokedAtUtc = ? "
                "WHERE WorkflowId = ? AND RevokedAtUtc IS NULL",
                (now, workflow_id))
            cur.execute(
                f"INSERT INTO {SCHEMA}.ReturnTripLinkToken ("
                "TokenHash, WorkflowId, ResolveCount, ExpiresAtUtc, CreatedAtUtc) "
                "VALUES (?, ?, 0, ?, ?)",
                (hash_token(raw), workflow_id,
                 now + timedelta(days=ttl_days), now))
            conn.commit()
            return raw
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
            conn.close()

    def resolve(self, raw_token: str) -> Optional[Dict[str, Any]]:
        """Workflow id for a live token, or None.

        Expiry and revocation are in the WHERE clause, not checked afterwards:
        an expired token and a token that never existed must be
        indistinguishable to the caller, and a branch on 'found but expired'
        is how that distinction leaks back out.
        """
        if not raw_token:
            return None
        conn = self._connect()
        if not conn:
            raise RuntimeError("Database unavailable")
        cur = conn.cursor()
        try:
            self.ensure_schema(cur)
            cur.execute(
                "SELECT WorkflowId, ResolveCount FROM "
                f"{SCHEMA}.ReturnTripLinkToken "
                "WHERE TokenHash = ? AND RevokedAtUtc IS NULL AND ExpiresAtUtc > ?",
                (hash_token(raw_token), _utcnow()))
            row = cur.fetchone()
            if not row:
                return None
            return {"workflow_id": row[0], "resolve_count": row[1]}
        finally:
            cur.close()
            conn.close()

    def charge_resolve(self, raw_token: str) -> bool:
        """Count one billed lookup against this token. False if over budget.

        A single conditional UPDATE rather than read-then-write: two concurrent
        requests that both read 19 would both proceed, and the cap would be
        advisory rather than real. Whoever's UPDATE matches the predicate gets
        the budget.
        """
        conn = self._connect()
        if not conn:
            raise RuntimeError("Database unavailable")
        cur = conn.cursor()
        try:
            self.ensure_schema(cur)
            now = _utcnow()
            cur.execute(
                f"UPDATE {SCHEMA}.ReturnTripLinkToken "
                "SET ResolveCount = ResolveCount + 1, LastUsedAtUtc = ? "
                "WHERE TokenHash = ? AND RevokedAtUtc IS NULL "
                "  AND ExpiresAtUtc > ? AND ResolveCount < ?",
                (now, hash_token(raw_token), now, MAX_RESOLVES_PER_WORKFLOW))
            charged = (cur.rowcount or 0) == 1
            conn.commit()
            if not charged:
                logging.warning(
                    "Return-trip resolve budget exhausted or token invalid; "
                    "refusing billed provider call")
            return charged
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
            conn.close()

    def revoke(self, workflow_id: str) -> None:
        """Kill the live token for a workflow (confirmed, cancelled, expired)."""
        conn = self._connect()
        if not conn:
            raise RuntimeError("Database unavailable")
        cur = conn.cursor()
        try:
            self.ensure_schema(cur)
            cur.execute(
                f"UPDATE {SCHEMA}.ReturnTripLinkToken SET RevokedAtUtc = ? "
                "WHERE WorkflowId = ? AND RevokedAtUtc IS NULL",
                (_utcnow(), workflow_id))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
            conn.close()
