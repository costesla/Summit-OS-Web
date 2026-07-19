"""
services/flightradar24.py
-------------------------
Flightradar24 API v1 client (https://fr24api.flightradar24.com).

Thin-blueprint / fat-service pattern (mirrors services/tessie.py): the MCP
tools in api/flightradar24.py stay declarative and this module owns every
production concern:

  - Bearer auth. The token is read via SecretManager (Key Vault -> App Setting
    fallback). It is NEVER hardcoded, NEVER printed, NEVER logged, and NEVER
    placed into an exception message.
  - Rate-limit protection: a process-wide minimum-interval throttle between
    outbound requests (class-level lock + last_request_at).
  - Backoff: HTTP 429 honours Retry-After, else exponential backoff capped at
    ~8s, up to 3 retries (5xx uses the same backoff).
  - Credit protection: a short-TTL in-process response cache keyed by a
    SHA-256 of deterministic endpoint+params JSON. cache_ttl=0 bypasses it.
  - Enterprise logging: provider, endpoint, UTC ISO timestamp, HTTP status,
    duration_ms, record_count, and any FR24 usage/credit/quota/rate response
    header. The Authorization header is never logged.
  - Typed FR24ApiError with friendly, provider-safe messages.

Design note: the FR24 v1 API is organised around LIVE flight-positions, NOT a
scheduled arrivals/departures board. Arrivals/departures are derived from the
airports=inbound:/outbound: filter, so results are live *airborne* traffic.
The API exposes no delay data and no static aircraft-registration database.
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

FR24_BASE_URL = "https://fr24api.flightradar24.com"
FR24_ACCEPT_VERSION = "v1"

# Colorado Springs Airport. Use ICAO in the FR24 airports filter.
COS_ICAO = "KCOS"
COS_IATA = "COS"

# FR24 flight category codes: P,C,M,J,T,H,B,G,D,V,O,N. J == Business jets.
CATEGORY_BUSINESS_JETS = "J"

# ── Friendly, provider-safe error strings (never contain the token) ──────────
_MSG_401 = "Flightradar24 rejected the request because the API token is invalid, expired, or missing."
_MSG_402 = "Flightradar24 credits appear to be exhausted or payment is required for this request."
_MSG_429 = "Flightradar24 rate limited the request. Try again shortly."
_MSG_5XX = "Flightradar24 is currently having provider-side trouble. Try again shortly."
_MSG_TIMEOUT = "Flightradar24 did not respond before the request timed out. Try again shortly."
_MSG_NETWORK = "Flightradar24 could not be reached. Check network connectivity and provider availability."
_MSG_INVALID_JSON = "Flightradar24 returned a response that could not be parsed as JSON."


class FR24ApiError(Exception):
    """Flightradar24 API failure with an operator-friendly message.

    provider_message optionally carries a message extracted from the FR24
    response body; it is never allowed to contain secrets.
    """

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
            "provider": "Flightradar24",
        }
        if self.provider_message:
            d["provider_message"] = self.provider_message
        return d


class Flightradar24Client:
    """Resilient client over the FR24 API v1 endpoints we use."""

    # Tuning knobs (production-safe defaults).
    MIN_INTERVAL_SEC = 0.25
    MAX_RETRIES = 3
    BACKOFF_BASE_SEC = 1.0
    BACKOFF_CAP_SEC = 8.0
    TIMEOUT_SEC = 20
    DEFAULT_CACHE_TTL_SEC = 30

    # Process-wide shared state so throttle/cache protect the credit budget
    # across the many short-lived client instances the tools create.
    _throttle_lock = threading.Lock()
    _last_request_at = 0.0
    _cache_lock = threading.Lock()
    _cache: "dict[str, tuple[float, dict]]" = {}

    def __init__(self):
        self.secrets = SecretManager()
        self._token = self.secrets.get_secret("FLIGHTRADAR24_API_TOKEN")
        self.base_url = FR24_BASE_URL
        self._session = requests.Session()
        if self._token:
            self._session.headers.update({
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/json",
                "Accept-Version": FR24_ACCEPT_VERSION,
            })
        else:
            logging.warning(
                "FR24: FLIGHTRADAR24_API_TOKEN not found in Key Vault or App "
                "Settings. Flight tools will return a configuration error."
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
        """Enforce a minimum interval between outbound requests, process-wide."""
        with cls._throttle_lock:
            now = time.monotonic()
            wait = cls.MIN_INTERVAL_SEC - (now - cls._last_request_at)
            if wait > 0:
                time.sleep(wait)
            cls._last_request_at = time.monotonic()

    @staticmethod
    def _log_usage_headers(headers) -> None:
        """Log any FR24 usage/credit/quota/rate response header. Never auth."""
        for k, v in (headers or {}).items():
            lk = k.lower()
            if any(t in lk for t in ("credit", "usage", "quota", "ratelimit", "rate-limit")):
                logging.info(f"FR24 usage header {k}={v}")

    @staticmethod
    def _backoff_delay(attempt: int) -> float:
        return min(Flightradar24Client.BACKOFF_BASE_SEC * (2 ** (attempt - 1)),
                   Flightradar24Client.BACKOFF_CAP_SEC)

    @staticmethod
    def _record_count(data) -> int:
        if isinstance(data, dict):
            d = data.get("data")
            if isinstance(d, list):
                return len(d)
            if isinstance(d, dict) and "record_count" in d:
                return int(d.get("record_count") or 0)
            if "record_count" in data:
                return int(data.get("record_count") or 0)
        if isinstance(data, list):
            return len(data)
        return 0

    def _get(self, path: str, params: dict, cache_ttl: Optional[int] = None) -> dict:
        """GET a FR24 endpoint with throttle, retry/backoff, caching, logging.

        Raises FR24ApiError on unrecoverable failure. Returns parsed JSON.
        """
        if not self._token:
            raise FR24ApiError(401, _MSG_401)

        ttl = self.DEFAULT_CACHE_TTL_SEC if cache_ttl is None else cache_ttl
        key = self._cache_key(path, params)
        if ttl > 0:
            cached = self._cache_get(key)
            if cached is not None:
                logging.info(f"FR24 cache hit endpoint={path}")
                return cached

        url = self.base_url + path
        last_err: Optional[FR24ApiError] = None

        for attempt in range(1, self.MAX_RETRIES + 1):
            self._throttle()
            started = time.monotonic()
            ts = datetime.now(timezone.utc).isoformat()
            try:
                resp = self._session.get(url, params=params, timeout=self.TIMEOUT_SEC)
            except requests.Timeout:
                logging.warning(f"FR24 timeout endpoint={path} ts={ts} attempt={attempt}")
                last_err = FR24ApiError(None, _MSG_TIMEOUT)
                time.sleep(self._backoff_delay(attempt))
                continue
            except requests.RequestException as e:
                logging.error(f"FR24 network error endpoint={path} ts={ts} attempt={attempt}: {type(e).__name__}")
                last_err = FR24ApiError(None, _MSG_NETWORK)
                time.sleep(self._backoff_delay(attempt))
                continue

            duration_ms = round((time.monotonic() - started) * 1000, 1)
            status = resp.status_code
            self._log_usage_headers(resp.headers)

            if status == 200:
                try:
                    data = resp.json()
                except ValueError:
                    logging.warning(f"FR24 invalid JSON endpoint={path} ts={ts}")
                    raise FR24ApiError(200, _MSG_INVALID_JSON)
                logging.info(
                    f"FR24 provider=Flightradar24 endpoint={path} ts={ts} "
                    f"status=200 duration_ms={duration_ms} "
                    f"record_count={self._record_count(data)}"
                )
                if ttl > 0:
                    self._cache_set(key, data, ttl)
                return data

            logging.warning(
                f"FR24 provider=Flightradar24 endpoint={path} ts={ts} "
                f"status={status} duration_ms={duration_ms}"
            )

            if status == 401:
                raise FR24ApiError(401, _MSG_401)
            if status == 402:
                raise FR24ApiError(402, _MSG_402)
            if status == 429:
                last_err = FR24ApiError(429, _MSG_429)
                retry_after = resp.headers.get("Retry-After")
                delay = (
                    min(float(retry_after), self.BACKOFF_CAP_SEC)
                    if retry_after and str(retry_after).strip().isdigit()
                    else self._backoff_delay(attempt)
                )
                if attempt < self.MAX_RETRIES:
                    logging.warning(f"FR24 rate limited; backing off {delay}s")
                    time.sleep(delay)
                    continue
                raise last_err
            if status >= 500:
                last_err = FR24ApiError(status, _MSG_5XX)
                if attempt < self.MAX_RETRIES:
                    time.sleep(self._backoff_delay(attempt))
                    continue
                raise last_err

            # Other 4xx: do not retry.
            raise FR24ApiError(status, _MSG_5XX if status >= 500 else
                               f"Flightradar24 request failed (HTTP {status}).")

        # Retries exhausted (timeout / network).
        raise last_err or FR24ApiError(None, _MSG_NETWORK)

    # ── public endpoint wrappers ─────────────────────────────────────────────
    def live_flight_positions(
        self,
        airports: Optional[str] = None,
        flights: Optional[str] = None,
        callsigns: Optional[str] = None,
        registrations: Optional[str] = None,
        categories: Optional[str] = None,
        limit: Optional[int] = None,
        cache_ttl: Optional[int] = None,
    ) -> list:
        """GET /api/live/flight-positions/full -> list of flight dicts."""
        params: dict = {}
        if airports:
            params["airports"] = airports
        if flights:
            params["flights"] = flights
        if callsigns:
            params["callsigns"] = callsigns
        if registrations:
            params["registrations"] = registrations
        if categories:
            params["categories"] = categories
        if limit:
            params["limit"] = int(limit)
        data = self._get("/api/live/flight-positions/full", params, cache_ttl=cache_ttl)
        rows = data.get("data") if isinstance(data, dict) else data
        return rows if isinstance(rows, list) else []

    def live_flight_count(self, airports: str, categories: Optional[str] = None,
                          cache_ttl: Optional[int] = None) -> int:
        """GET /api/live/flight-positions/count -> integer count."""
        params: dict = {"airports": airports}
        if categories:
            params["categories"] = categories
        data = self._get("/api/live/flight-positions/count", params, cache_ttl=cache_ttl)
        return self._record_count(data)

    def airline_light(self, icao: str) -> Optional[dict]:
        """GET /api/static/airlines/{icao}/light -> airline dict or None.

        Used only to resolve an operator ICAO code to a name. Static data, so
        cached aggressively (1 hour). Never raises to the caller.
        """
        icao = (icao or "").strip().upper()
        if not icao:
            return None
        try:
            data = self._get(f"/api/static/airlines/{icao}/light", {}, cache_ttl=3600)
        except FR24ApiError:
            return None
        if isinstance(data, dict):
            inner = data.get("data")
            return inner if isinstance(inner, dict) else data
        return None
