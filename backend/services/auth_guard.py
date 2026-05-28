"""
services/auth_guard.py
-----------------------
Reusable auth middleware for Azure Function endpoints.

Usage in a blueprint:

    from services.auth_guard import require_function_key, require_api_key

    @bp.route(route="my-secure-route", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
    def my_endpoint(req: func.HttpRequest):
        guard = require_function_key(req)   # or require_api_key(req)
        if guard:
            return guard  # 401 / 403 response
        # ... real handler logic

Why ANONYMOUS at the Azure level?
  Azure's built-in key check doesn't support per-route CORS preflight.
  We validate the key ourselves so OPTIONS requests still get a 204.
"""

import os
import logging
import json
import hashlib
import hmac
import azure.functions as func
from typing import Optional

# ── Allowed CORS origins ─────────────────────────────────────────────────────
# Set ALLOWED_ORIGINS in Azure App Settings as a comma-separated list.
# Falls back to production domain only. Wildcard (*) is NOT allowed here.
_DEFAULT_ORIGINS = "https://www.costesla.com,https://costesla.com,https://www.dashboardcostesla.com,https://dashboardcostesla.com"
_ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get("ALLOWED_ORIGINS", _DEFAULT_ORIGINS).split(",")
    if o.strip()
]


def cors_headers(req: func.HttpRequest) -> dict:
    """
    Return CORS headers with a reflected, allow-listed origin.
    Falls back to the first allowed origin if the request origin is not listed.
    """
    request_origin = req.headers.get("Origin", "")
    if request_origin in _ALLOWED_ORIGINS:
        allowed_origin = request_origin
    else:
        allowed_origin = _ALLOWED_ORIGINS[0]

    return {
        "Access-Control-Allow-Origin": allowed_origin,
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization, x-functions-key",
        "Access-Control-Allow-Credentials": "true",
        "Vary": "Origin",
    }


def _unauthorized(message: str, req: func.HttpRequest) -> func.HttpResponse:
    logging.warning(f"AUTH REJECTED: {message}")
    return func.HttpResponse(
        json.dumps({"error": "Unauthorized", "detail": message}),
        status_code=401,
        mimetype="application/json",
        headers=cors_headers(req),
    )


# ── Function Key Validation ───────────────────────────────────────────────────

def require_function_key(req: func.HttpRequest) -> Optional[func.HttpResponse]:
    """
    Validates the Azure Function host key supplied via:
      - Header:      x-functions-key
      - Query param: code

    Returns None on success (caller proceeds).
    Returns a 401 HttpResponse on failure (caller should return it).
    """
    expected = os.environ.get("AZURE_FUNCTION_KEY")
    if not expected:
        logging.warning("AZURE_FUNCTION_KEY not set — function key check disabled.")
        return None  # Fail-open in dev when key not configured

    provided = req.headers.get("x-functions-key") or req.params.get("code")
    if not provided:
        return _unauthorized("Missing function key", req)

    # Constant-time comparison to prevent timing attacks
    if not hmac.compare_digest(provided.strip(), expected.strip()):
        return _unauthorized("Invalid function key", req)

    return None


# ── API Key Validation (for Copilot / internal service calls) ─────────────────

def require_api_key(req: func.HttpRequest, env_var: str = "INTERNAL_API_KEY") -> Optional[func.HttpResponse]:
    """
    Validates an API key from the Authorization header (Bearer token).

    Returns None on success, 401 HttpResponse on failure.
    """
    expected = os.environ.get(env_var)
    if not expected:
        logging.warning(f"{env_var} not set — API key check disabled.")
        return None

    auth_header = req.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return _unauthorized("Missing or malformed Authorization header", req)

    provided = auth_header[len("Bearer "):].strip()
    if not hmac.compare_digest(provided, expected.strip()):
        return _unauthorized("Invalid API key", req)

    return None
