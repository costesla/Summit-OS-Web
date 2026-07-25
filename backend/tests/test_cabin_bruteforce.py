"""
Brute-force protection for the cabin access code (api/cabin.py).

SECURITY CONTROL. The cabin code is 6 digits (~900k values) so a passenger can
read it out or type it, and a valid code opens the vehicle's trunk. Both cabin
routes are anonymous, so without a lockout the code space can be exhausted by
guessing — and because every unexpired booking's code is a valid answer, more
concurrent trips make guessing EASIER. Expiry alone does not mitigate this.

These tests pin the lockout so a refactor can't silently remove it.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api import cabin  # noqa: E402


class _Req:
    """Minimal stand-in for func.HttpRequest (only what _guard touches)."""
    def __init__(self, ip="203.0.113.9"):
        self.headers = {"X-Forwarded-For": ip}


def setup_function():
    cabin._FAILED_ATTEMPTS.clear()


def _deny_all(monkey_token=None):
    cabin._validate_token = lambda t: False


def _allow_all():
    cabin._validate_token = lambda t: True


def test_client_ip_strips_the_azure_source_port():
    """Azure sends "<ip>:<port>" and the port changes every connection. If it
    isn't stripped, every request lands in its own bucket and the lockout never
    fires — which is exactly what happened in production."""
    class R:
        def __init__(self, v):
            self.headers = {"X-Forwarded-For": v}

    assert cabin._client_ip(R("203.0.113.9:52431")) == "203.0.113.9"
    assert cabin._client_ip(R("203.0.113.9:1")) == "203.0.113.9"
    assert cabin._client_ip(R("203.0.113.9")) == "203.0.113.9"
    # Proxy chain: the client is the first entry.
    assert cabin._client_ip(R("203.0.113.9:52431, 70.0.0.1:80")) == "203.0.113.9"
    # IPv6 forms must survive intact.
    assert cabin._client_ip(R("[2001:db8::1]:443")) == "2001:db8::1"
    assert cabin._client_ip(R("2001:db8::1")) == "2001:db8::1"
    assert cabin._client_ip(R("")) == "unknown"


def test_consecutive_requests_from_one_client_share_a_bucket():
    """The regression that let the attack through: differing source ports must
    still count as one attacker."""
    class R:
        def __init__(self, v):
            self.headers = {"X-Forwarded-For": v}

    _deny_all()
    for port in range(50000, 50000 + cabin._FAIL_MAX):
        cabin._guard(R(f"198.51.100.4:{port}"), "000000")
    # A fresh port from the same client must now be locked out.
    assert cabin._guard(R("198.51.100.4:60999"), "000000").status_code == 429


def test_bad_code_is_rejected():
    _deny_all()
    resp = cabin._guard(_Req(), "123456")
    assert resp is not None
    assert resp.status_code == 401


def test_locks_out_after_repeated_bad_codes():
    _deny_all()
    req = _Req()
    # Burn through the allowance.
    for _ in range(cabin._FAIL_MAX):
        assert cabin._guard(req, "000000").status_code == 401
    # The next attempt must be refused before the code is even checked.
    resp = cabin._guard(req, "000000")
    assert resp.status_code == 429


def test_lockout_blocks_even_a_valid_code():
    # An attacker who guesses correctly *after* tripping the lockout still gets
    # nothing — the gate runs before validation.
    _deny_all()
    req = _Req()
    for _ in range(cabin._FAIL_MAX):
        cabin._guard(req, "000000")
    _allow_all()
    assert cabin._guard(req, "999999").status_code == 429


def test_lockout_is_per_ip():
    _deny_all()
    attacker = _Req("198.51.100.7")
    for _ in range(cabin._FAIL_MAX):
        cabin._guard(attacker, "000000")
    assert cabin._guard(attacker, "000000").status_code == 429
    # A different passenger is unaffected.
    assert cabin._guard(_Req("203.0.113.55"), "000000").status_code == 401


def test_valid_code_passes_and_resets_the_counter():
    req = _Req("203.0.113.99")
    _deny_all()
    for _ in range(cabin._FAIL_MAX - 1):   # a few typos, not yet locked out
        cabin._guard(req, "000000")
    _allow_all()
    assert cabin._guard(req, "424242") is None      # allowed through
    # Counter cleared, so the passenger keeps a full allowance afterwards.
    _deny_all()
    for _ in range(cabin._FAIL_MAX - 1):
        assert cabin._guard(req, "000000").status_code == 401


def test_attempts_age_out_of_the_window():
    import time
    _deny_all()
    req = _Req("203.0.113.77")
    for _ in range(cabin._FAIL_MAX):
        cabin._guard(req, "000000")
    assert cabin._guard(req, "000000").status_code == 429
    # Rewind the recorded attempts past the window.
    ip = cabin._client_ip(req)
    cabin._FAILED_ATTEMPTS[ip] = [t - (cabin._FAIL_WINDOW_SEC + 1)
                                  for t in cabin._FAILED_ATTEMPTS[ip]]
    assert cabin._guard(req, "000000").status_code == 401   # locked out no more


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
