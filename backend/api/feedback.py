"""
POST /api/feedback — minimal feedback intake (B4b).

Accepts {rating: 1-5, message: str, contact?: str} from the app's More tab
and delivers it as an email to the owner via the existing GraphClient
(Mail.Send is already granted). No storage, no schema — deliberately the
smallest possible endpoint; revisit if feedback volume ever justifies a table.
"""
import logging
import azure.functions as func
import json
import html

bp = func.Blueprint()


def _cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type"
    }


def _json_response(data, status_code=200):
    return func.HttpResponse(
        json.dumps(data),
        status_code=status_code,
        headers=_cors_headers(),
        mimetype="application/json"
    )


@bp.route(route="feedback", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def submit_feedback(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_cors_headers())

    try:
        body = req.get_json()
    except ValueError:
        return _json_response({"success": False, "error": "Invalid JSON"}, 400)

    rating = body.get("rating")
    message = (body.get("message") or "").strip()
    contact = (body.get("contact") or "").strip()[:200]

    if not isinstance(rating, int) or not 1 <= rating <= 5:
        return _json_response({"success": False, "error": "rating must be an integer 1-5"}, 400)
    if not message or len(message) > 2000:
        return _json_response({"success": False, "error": "message required (max 2000 chars)"}, 400)

    try:
        from services.graph import GraphClient

        stars = "★" * rating + "☆" * (5 - rating)
        body_html = (
            f"<h3>App feedback — {stars} ({rating}/5)</h3>"
            f"<p style='white-space:pre-wrap'>{html.escape(message)}</p>"
            f"<p><b>Contact:</b> {html.escape(contact) if contact else '(not provided)'}</p>"
        )
        GraphClient().send_mail(
            to_email="peter.teehan@costesla.com",
            subject=f"App feedback: {rating}/5",
            body_html=body_html,
        )
        return _json_response({"success": True})
    except Exception as e:
        logging.error(f"Feedback delivery failed: {e}")
        return _json_response({"success": False, "error": "delivery failed"}, 502)
