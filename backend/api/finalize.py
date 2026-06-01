import logging
import azure.functions as func
import json
import os

bp = func.Blueprint()

def _cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type"
    }

@bp.route(route="finalize-booking", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def finalize_booking(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_cors_headers())

    try:
        req_body = req.get_json()
        session_id = req_body.get("session_id")
        if not session_id:
            return func.HttpResponse(
                json.dumps({"success": False, "error": "No session ID provided"}),
                status_code=400,
                headers=_cors_headers(),
                mimetype="application/json"
            )

        from services.finalize_service import finalize_stripe_session
        result = finalize_stripe_session(session_id)

        status_code = 200 if result.get("success") else 400
        return func.HttpResponse(
            json.dumps(result),
            status_code=status_code,
            headers=_cors_headers(),
            mimetype="application/json"
        )

    except Exception as e:
        import traceback
        logging.error(f"Finalize Booking Error: {str(e)}\n{traceback.format_exc()}")
        return func.HttpResponse(
            json.dumps({"success": False, "error": str(e)}),
            status_code=500,
            headers=_cors_headers(),
            mimetype="application/json"
        )
