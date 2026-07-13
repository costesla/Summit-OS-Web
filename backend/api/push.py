"""
Push subscription endpoints (B5b) — owner-gated via Easy Auth.

The SWA linked-backend proxy forwards the x-ms-client-principal header for
authenticated sessions; every route here requires it. Anonymous callers
(including direct hits on summitos-api) get 401 — real auth, not cosmetic.
"""
import logging
import azure.functions as func
import json
import base64

bp = func.Blueprint()


def _json_response(data, status_code=200):
    return func.HttpResponse(
        json.dumps(data),
        status_code=status_code,
        mimetype="application/json",
    )


def _principal(req: func.HttpRequest):
    """Parse the SWA-forwarded Easy Auth principal; None if absent/invalid."""
    header = req.headers.get("x-ms-client-principal")
    if not header:
        return None
    try:
        data = json.loads(base64.b64decode(header).decode("utf-8"))
        return data if (data.get("userId") or data.get("userDetails")) else None
    except Exception:
        return None


@bp.route(route="push/subscribe", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def push_subscribe(req: func.HttpRequest) -> func.HttpResponse:
    if not _principal(req):
        return _json_response({"success": False, "error": "Unauthorized"}, 401)
    try:
        body = req.get_json()
    except ValueError:
        return _json_response({"success": False, "error": "Invalid JSON"}, 400)

    sub = body.get("subscription") or {}
    if not sub.get("endpoint") or not isinstance(sub.get("keys"), dict):
        return _json_response({"success": False, "error": "subscription with endpoint+keys required"}, 400)

    try:
        from services.push_sender import add_subscription
        count = add_subscription({"endpoint": sub["endpoint"], "keys": sub["keys"]})
        return _json_response({"success": True, "count": count})
    except Exception as e:
        logging.error(f"push/subscribe failed: {e}")
        return _json_response({"success": False, "error": "storage failure"}, 500)


@bp.route(route="push/unsubscribe", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def push_unsubscribe(req: func.HttpRequest) -> func.HttpResponse:
    if not _principal(req):
        return _json_response({"success": False, "error": "Unauthorized"}, 401)
    try:
        endpoint = (req.get_json() or {}).get("endpoint")
    except ValueError:
        endpoint = None
    if not endpoint:
        return _json_response({"success": False, "error": "endpoint required"}, 400)

    try:
        from services.push_sender import remove_subscription
        count = remove_subscription(endpoint)
        return _json_response({"success": True, "count": count})
    except Exception as e:
        logging.error(f"push/unsubscribe failed: {e}")
        return _json_response({"success": False, "error": "storage failure"}, 500)


@bp.route(route="push/test", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def push_test(req: func.HttpRequest) -> func.HttpResponse:
    if not _principal(req):
        return _json_response({"success": False, "error": "Unauthorized"}, 401)
    try:
        from services.push_sender import notify_driver
        result = notify_driver("Test notification", "Push pipeline works ✔", "/more/")
        ok = result.get("sent", 0) > 0
        return _json_response({"success": ok, **result}, 200 if ok else 502)
    except Exception as e:
        logging.error(f"push/test failed: {e}")
        return _json_response({"success": False, "error": str(e)}, 500)
