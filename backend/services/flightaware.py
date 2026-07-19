"""
services/flightaware.py
-----------------------
FlightAware AeroAPI v4 client (https://aeroapi.flightaware.com/aeroapi).

Complements services/flightradar24.py: FR24 answers "what's airborne right
now", AeroAPI answers "what is SCHEDULED to arrive" — a true timetable with
airline, gate/runway times, and delays, including flights still on the ground.

Owns the production concerns (same shape as Flightradar24Client):
  - Auth via the `x-apikey` header. Key comes from SecretManager
    (Key Vault -> App Setting). NEVER hardcoded, printed, logged, or put in an
    exception message.
  - Rate-limit protection: process-wide minimum-interval throttle.
  - Backoff: HTTP 429 honours Retry-After, else exponential backoff capped at
    ~8s, up to 3 retries (5xx uses the same backoff).
  - Cost/credit protection: short-TTL in-process cache keyed by a SHA-256 of
    deterministic endpoint+params JSON (AeroAPI bills ~$0.005 per query).
  - Enterprise logging: provider, endpoint, UTC ISO timestamp, HTTP status,
    duration_ms, record_count. The x-apikey header is never logged.
  - Typed FlightAwareApiError with friendly, provider-safe messages.
"""

import time
import json
import hashlib
import logging
import threading
from datetime import datetime, timezone
from typing import Optional

import requests

from services.secret_manager import SecretManager

AEROAPI_BASE_URL = "https://aeroapi.flightaware.com/aeroapi"

# Colorado Springs Airport (ICAO is the AeroAPI airport id).
COS_ICAO = "KCOS"

# AeroAPI cannot distinguish passenger from cargo airlines (type=Airline
# includes both). We drop cargo carriers by operator ICAO. Extend as needed.
CARGO_OPERATORS_ICAO = {
    "FDX",  # FedEx
    "UPS",  # UPS
    "GTI",  # Atlas Air
    "ABX",  # ABX Air
    "CKS",  # Kalitta Air
    "CLX",  # Cargolux
    "GEC",  # Lufthansa Cargo
    "BOX",  # AeroLogic
    "ATN",  # Air Transport International
    "GSS",  # DHL / Global (Southern Air)
    "BCS",  # European Air Transport (DHL)
    "NCA",  # Nippon Cargo
    "CAO",  # Air China Cargo
    "PAC",  # Polar Air Cargo
    "MPH",  # Martinair Cargo
}

# ── Friendly, provider-safe error strings (never contain the key) ────────────
_MSG_401 = "FlightAware rejected the request because the AeroAPI key is invalid, expired, or missing."
_MSG_429 = "FlightAware rate limited the request. Try again shortly."
_MSG_5XX = "FlightAware is currently having provider-side trouble. Try again shortly."
_MSG_TIMEOUT = "FlightAware did not respond before the request timed out. Try again shortly."
_MSG_NETWORK = "FlightAware could not be reached. Check network connectivity and provider availability."
_MSG_INVALID_JSON = "FlightAware returned a response that could not be parsed as JSON."
_MSG_BADREQ = "FlightAware rejected the request as invalid (check the airport code or time window)."


class FlightAwareApiError(Exception):
    """AeroAPI failure with an operator-friendly message."""

    def __init__(self, status_code: Optional[int], message: str,
                 provider_message: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.provider_message = provider_message

    def to_dict(self) -> dict:
        d = {
            "error": self.message,
            "status_code": self.status_code,
            "provider": "FlightAware",
        }
        if self.provider_message:
            d["provider_message"] = self.provider_message
        return d


class FlightAwareClient:
    """Resilient client over the AeroAPI endpoints we use."""

    MIN_INTERVAL_SEC = 0.25
    MAX_RETRIES = 3
    BACKOFF_BASE_SEC = 1.0
    BACKOFF_CAP_SEC = 8.0
    TIMEOUT_SEC = 20
    DEFAULT_CACHE_TTL_SEC = 60  # scheduled boards move slowly; protects credits

    _throttle_lock = threading.Lock()
    _last_request_at = 0.0
    _cache_lock = threading.Lock()
    _cache: "dict[str, tuple[float, dict]]" = {}

    def __init__(self):
        self.secrets = SecretManager()
        self._key = self.secrets.get_secret("FLIGHTAWARE_API_KEY")
        self.base_url = AEROAPI_BASE_URL
        self._session = requests.Session()
        if self._key:
            self._session.headers.update({
                "x-apikey": self._key,
                "Accept": "application/json",
            })
        else:
            logging.warning(
                "FlightAware: FLIGHTAWARE_API_KEY not found in Key Vault or App "
                "Settings. Scheduled-arrivals tool will return a config error."
            )

    # ── internal helpers ─────────────────────────────────────────────────────
    @staticmethod
    def _cache_key(path: str, params: dict) -> str:
        blob = json.dumps({"endpoint": path, "params": params or {}},
                          sort_keys=True, default=str)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    @classmethod
    def _cache_get(cls, key: str):
        with cls._cache_lock:
            hit = cls._cache.get(key)
            if hit and hit[0] > time.monotonic():
                return hit[1]
            if hit:
                cls._cache.pop(key, None)
        return None

    @classmethod
    def _cache_set(cls, key: str, data: dict, ttl: int):
        with cls._cache_lock:
            cls._cache[key] = (time.monotonic() + ttl, data)

    @classmethod
    def _throttle(cls):
        with cls._throttle_lock:
            now = time.monotonic()
            wait = cls.MIN_INTERVAL_SEC - (now - cls._last_request_at)
            if wait > 0:
                time.sleep(wait)
            cls._last_request_at = time.monotonic()

    @staticmethod
    def _backoff_delay(attempt: int) -> float:
        return min(FlightAwareClient.BACKOFF_BASE_SEC * (2 ** (attempt - 1)),
                   FlightAwareClient.BACKOFF_CAP_SEC)

    def _get(self, path: str, params: dict, cache_ttl: Optional[int] = None) -> dict:
        """GET an AeroAPI endpoint with throttle, retry/backoff, cache, logging."""
        if not self._key:
            raise FlightAwareApiError(401, _MSG_401)

        ttl = self.DEFAULT_CACHE_TTL_SEC if cache_ttl is None else cache_ttl
        key = self._cache_key(path, params)
        if ttl > 0:
            cached = self._cache_get(key)
            if cached is not None:
                logging.info(f"FlightAware cache hit endpoint={path}")
                return cached

        url = self.base_url + path
        last_err: Optional[FlightAwareApiError] = None

        for attempt in range(1, self.MAX_RETRIES + 1):
            self._throttle()
            started = time.monotonic()
            ts = datetime.now(timezone.utc).isoformat()
            try:
                resp = self._session.get(url, params=params, timeout=self.TIMEOUT_SEC)
            except requests.Timeout:
                logging.warning(f"FlightAware timeout endpoint={path} ts={ts} attempt={attempt}")
                last_err = FlightAwareApiError(None, _MSG_TIMEOUT)
                time.sleep(self._backoff_delay(attempt))
                continue
            except requests.RequestException as e:
                logging.error(f"FlightAware network error endpoint={path} ts={ts} attempt={attempt}: {type(e).__name__}")
                last_err = FlightAwareApiError(None, _MSG_NETWORK)
                time.sleep(self._backoff_delay(attempt))
                continue

            duration_ms = round((time.monotonic() - started) * 1000, 1)
            status = resp.status_code

            if status == 200:
                try:
                    data = resp.json()
                except ValueError:
                    logging.warning(f"FlightAware invalid JSON endpoint={path} ts={ts}")
                    raise FlightAwareApiError(200, _MSG_INVALID_JSON)
                logging.info(
                    f"FlightAware provider=FlightAware endpoint={path} ts={ts} "
                    f"status=200 duration_ms={duration_ms} "
                    f"record_count={self._record_count(data)}"
                )
                if ttl > 0:
                    self._cache_set(key, data, ttl)
                return data

            logging.warning(
                f"FlightAware provider=FlightAware endpoint={path} ts={ts} "
                f"status={status} duration_ms={duration_ms}"
            )

            if status == 401:
                raise FlightAwareApiError(401, _MSG_401)
            if status == 400:
                raise FlightAwareApiError(400, _MSG_BADREQ)
            if status == 429:
                last_err = FlightAwareApiError(429, _MSG_429)
                retry_after = resp.headers.get("Retry-After")
                delay = (
                    min(float(retry_after), self.BACKOFF_CAP_SEC)
                    if retry_after and str(retry_after).strip().isdigit()
                    else self._backoff_delay(attempt)
                )
                if attempt < self.MAX_RETRIES:
                    logging.warning(f"FlightAware rate limited; backing off {delay}s")
                    time.sleep(delay)
                    continue
                raise last_err
            if status >= 500:
                last_err = FlightAwareApiError(status, _MSG_5XX)
                if attempt < self.MAX_RETRIES:
                    time.sleep(self._backoff_delay(attempt))
                    continue
                raise last_err

            raise FlightAwareApiError(status, f"FlightAware request failed (HTTP {status}).")

        raise last_err or FlightAwareApiError(None, _MSG_NETWORK)

    @staticmethod
    def _record_count(data) -> int:
        if isinstance(data, dict):
            for k in ("scheduled_arrivals", "arrivals", "flights"):
                if isinstance(data.get(k), list):
                    return len(data[k])
        return 0

    # ── public endpoint wrappers ─────────────────────────────────────────────
    def scheduled_arrivals(self, airport_icao: str, start: Optional[str] = None,
                           end: Optional[str] = None, flight_type: str = "Airline",
                           max_pages: int = 1, cache_ttl: Optional[int] = None) -> list:
        """GET /airports/{id}/flights/scheduled_arrivals -> list of flights.

        start/end are ISO8601 UTC strings (e.g. '2026-07-19T18:00:00Z').
        flight_type filters to 'Airline' (excludes general aviation).
        """
        params: dict = {"max_pages": max(1, int(max_pages))}
        if flight_type:
            params["type"] = flight_type
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        data = self._get(f"/airports/{airport_icao}/flights/scheduled_arrivals",
                         params, cache_ttl=cache_ttl)
        rows = data.get("scheduled_arrivals") if isinstance(data, dict) else None
        return rows if isinstance(rows, list) else []

    def flight_info(self, ident: str, cache_ttl: Optional[int] = None) -> Optional[dict]:
        """GET /flights/{ident} -> the most relevant flight instance, or None.

        Picks the in-progress flight if any, else the next not-yet-departed
        scheduled flight, else the most recent. Never raises to the caller
        (returns None on failure) so callers can degrade gracefully.
        """
        ident = (ident or "").strip().upper()
        if not ident:
            return None
        try:
            data = self._get(f"/flights/{ident}", {"max_pages": 1}, cache_ttl=cache_ttl)
        except FlightAwareApiError as e:
            logging.warning(f"FlightAware flight_info error for {ident}: {e.message}")
            return None
        flights = data.get("flights") if isinstance(data, dict) else None
        if not isinstance(flights, list) or not flights:
            return None
        for f in flights:  # 1) in progress
            pct = f.get("progress_percent")
            if isinstance(pct, (int, float)) and 0 < pct < 100 and not f.get("cancelled"):
                return f
        for f in flights:  # 2) next scheduled, not yet departed
            if not f.get("actual_out") and not f.get("cancelled"):
                return f
        return flights[-1]  # 3) most recent
