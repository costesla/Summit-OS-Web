"""
Airport-pickup context on the cabin token (services/database.py).

There is no bookings table — the cabin token IS the trip's identity — so the
flight number lives on Rides.CabinTokens. These tests pin the two properties
that matter:

  * the flight is written in the SAME INSERT as the token, so a booking can
    never produce a token that exists but has lost its flight, and
  * a lookup failure is never fatal: it degrades to "no server-side flight" and
    the console falls back to its ?flight= URL parameter.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.database import DatabaseClient  # noqa: E402


class _Cursor:
    def __init__(self, row=None, fail_on=None):
        self.executed = []
        self._row = row
        self._fail_on = fail_on

    def execute(self, sql, params=None):
        self.executed.append((" ".join(sql.split()), params))
        if self._fail_on and self._fail_on in sql:
            raise Exception("simulated SQL failure")

    def fetchone(self):
        return self._row

    def close(self):
        pass


class _Conn:
    def __init__(self, cursor):
        self._cursor = cursor
        self.committed = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed = True

    def close(self):
        pass


def _client(cursor):
    c = DatabaseClient()
    c.get_connection = lambda: _Conn(cursor)
    return c


def _inserts(cur):
    return [(s, p) for s, p in cur.executed if s.startswith("INSERT INTO Rides.CabinTokens")]


# ── write path ───────────────────────────────────────────────────────────────
def test_flight_is_written_in_the_same_insert_as_the_token():
    cur = _Cursor()
    token = _client(cur).create_cabin_token("R-1", flight_number="DL4089",
                                            expected_dest="COS")
    ins = _inserts(cur)
    assert len(ins) == 1, "token must be written by exactly one INSERT"
    sql, params = ins[0]
    assert "FlightNumber" in sql and "ExpectedDest" in sql
    assert token in params and "DL4089" in params and "COS" in params
    # No follow-up UPDATE that could half-fail.
    assert not any(s.startswith("UPDATE") for s, _ in cur.executed)


def test_values_are_normalised_and_bounded():
    cur = _Cursor()
    _client(cur).create_cabin_token("R-2", flight_number="  dl4089  ",
                                    expected_dest=" cos ")
    _, params = _inserts(cur)[0]
    assert "DL4089" in params and "COS" in params


def test_non_airport_booking_writes_nulls():
    cur = _Cursor()
    _client(cur).create_cabin_token("R-3")
    sql, params = _inserts(cur)[0]
    assert "FlightNumber" in sql          # column still addressed
    assert params[-2] is None and params[-1] is None


def test_garbage_flight_number_is_still_persisted():
    # An unrecognised or codeshare ident must survive — the console shows
    # whatever is in the column and a human can read it.
    cur = _Cursor()
    _client(cur).create_cabin_token("R-4", flight_number="NOTAFLIGHT")
    _, params = _inserts(cur)[0]
    assert "NOTAFLIGHT" in params


def test_columns_are_added_idempotently():
    cur = _Cursor()
    _client(cur).create_cabin_token("R-5")
    alters = [s for s, _ in cur.executed if "ALTER TABLE Rides.CabinTokens" in s]
    assert len(alters) == 2
    assert all("IF NOT EXISTS" in s for s in alters)


def test_token_still_returned_when_db_is_down():
    c = DatabaseClient()
    c.get_connection = lambda: None
    token = c.create_cabin_token("R-6", flight_number="DL4089")
    assert token and token.isdigit() and len(token) == 6


# ── read path ────────────────────────────────────────────────────────────────
def test_get_cabin_trip_returns_the_flight():
    cur = _Cursor(row=("DL4089", "COS"))
    trip = _client(cur).get_cabin_trip("123456")
    assert trip == {"flight_number": "DL4089", "expected_dest": "COS"}
    sql, _ = cur.executed[0]
    assert "ExpiresAt > GETDATE()" in sql, "expired tokens must not yield trip details"


def test_get_cabin_trip_none_for_unknown_or_flightless_token():
    assert _client(_Cursor(row=None)).get_cabin_trip("123456") is None
    assert _client(_Cursor(row=(None, None))).get_cabin_trip("123456") is None
    assert _client(_Cursor(row=("DL4089", "COS"))).get_cabin_trip("") is None


def test_get_cabin_trip_degrades_quietly_on_error():
    # Covers the pre-upgrade case where the columns don't exist yet: the console
    # must fall back to ?flight=, not error.
    assert _client(_Cursor(fail_on="SELECT FlightNumber")).get_cabin_trip("123456") is None
    c = DatabaseClient()
    c.get_connection = lambda: None
    assert c.get_cabin_trip("123456") is None


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
