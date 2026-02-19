import logging
import azure.functions as func
import json
import os
from services.tessie import TessieClient

bp = func.Blueprint()

def _cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization"
    }

def _cors_preflight():
    return func.HttpResponse(status_code=204, headers=_cors_headers())

def _json_response(data, status_code=200):
    return func.HttpResponse(
        json.dumps(data, default=str),
        status_code=status_code,
        headers=_cors_headers(),
        mimetype="application/json"
    )

def _validate_token(token):
    """
    Basic token presence check.
    TODO: Validate token against DB session table keyed to active booking.
    """
    return bool(token)


# ─── GET /cabin/state ─────────────────────────────────────────────────
@bp.route(route="cabin/state", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def cabin_state(req: func.HttpRequest) -> func.HttpResponse:
    """Returns flattened cabin state for the passenger UI."""
    if req.method == "OPTIONS":
        return _cors_preflight()

    logging.info("Cabin state requested")

    token = req.params.get("token")
    if not _validate_token(token):
        return _json_response({"error": "Unauthorized"}, 401)

    try:
        tessie = TessieClient()
        vin = os.environ.get("TESSIE_VIN")
        if not vin:
            return _json_response({"error": "No VIN configured"}, 500)

        state = tessie.get_vehicle_state(vin)
        if not state:
            return _json_response({"error": "Vehicle unreachable"}, 502)

        drive = state.get("drive_state", {})
        vehicle = state.get("vehicle_state", {})
        climate = state.get("climate_state", {})
        charge = state.get("charge_state", {})

        # Convert Celsius temps to Fahrenheit for US display
        inside_c = climate.get("inside_temp")
        outside_c = climate.get("outside_temp")
        driver_temp_c = climate.get("driver_temp_setting")

        payload = {
            "speed": drive.get("speed") or 0,
            "elevation": drive.get("elevation") or 0,
            "heading": drive.get("heading"),
            "inside_temp_f": round(inside_c * 9/5 + 32) if inside_c is not None else None,
            "outside_temp_f": round(outside_c * 9/5 + 32) if outside_c is not None else None,
            "climate_on": climate.get("is_climate_on", False),
            "target_temp_f": round(driver_temp_c * 9/5 + 32) if driver_temp_c is not None else 72,
            "seats": {
                "rl": climate.get("seat_heater_rear_left", 0),
                "rr": climate.get("seat_heater_rear_right", 0),
                "rc": climate.get("seat_heater_rear_center", 0),
            },
            "windows_vented": (vehicle.get("fd_window", 0) > 0 or vehicle.get("rd_window", 0) > 0),
            "battery_level": charge.get("battery_level"),
            "battery_range_mi": charge.get("battery_range"),
            "charging_state": charge.get("charging_state"),
        }

        return _json_response(payload)

    except Exception as e:
        logging.error(f"Cabin state error: {e}")
        return _json_response({"error": str(e)}, 500)


# ─── POST /cabin/command ──────────────────────────────────────────────
@bp.route(route="cabin/command", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def cabin_command(req: func.HttpRequest) -> func.HttpResponse:
    """Dispatches cabin control commands from the passenger UI."""
    if req.method == "OPTIONS":
        return _cors_preflight()

    logging.info("Cabin command received")

    try:
        body = req.get_json()
    except ValueError:
        return _json_response({"error": "Invalid JSON"}, 400)

    token = body.get("token")
    if not _validate_token(token):
        return _json_response({"error": "Unauthorized"}, 401)

    command = body.get("command")
    if not command:
        return _json_response({"error": "Missing command"}, 400)

    tessie = TessieClient()
    vin = os.environ.get("TESSIE_VIN")
    if not vin:
        return _json_response({"error": "No VIN configured"}, 500)

    ALLOWED_COMMANDS = {
        "seat_heater", "vent_windows", "close_windows",
        "start_climate", "stop_climate", "set_temp"
    }
    if command not in ALLOWED_COMMANDS:
        return _json_response({"error": f"Unknown command: {command}"}, 400)

    result = None

    try:
        if command == "seat_heater":
            seat = body.get("seat")
            level = body.get("level", 0)
            if seat not in ("rear_left", "rear_right", "rear_center"):
                return _json_response({"error": "Passengers may only control rear seats"}, 403)
            result = tessie.set_seat_heater(vin, seat, int(level))

        elif command == "vent_windows":
            result = tessie.control_windows(vin, "vent")

        elif command == "close_windows":
            result = tessie.control_windows(vin, "close")

        elif command == "start_climate":
            result = tessie.start_climate(vin)

        elif command == "stop_climate":
            result = tessie.stop_climate(vin)

        elif command == "set_temp":
            temp_f = body.get("temp_f")
            if temp_f is None:
                return _json_response({"error": "Missing temp_f"}, 400)
            # Clamp to safe range
            temp_f = max(60, min(85, int(temp_f)))
            result = tessie.set_climate_temp(vin, temp_f)

        if result:
            return _json_response({"success": True, "command": command})
        else:
            return _json_response({"error": "Command failed or vehicle unreachable"}, 502)

    except Exception as e:
        logging.error(f"Cabin command error: {e}")
        return _json_response({"error": str(e)}, 500)
