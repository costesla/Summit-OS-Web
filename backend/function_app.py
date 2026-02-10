import azure.functions as func
import sys
import os
import requests
import logging
import json
import importlib

# Path fix - MUST BE ABSOLUTE to prevent blueprint import failures
app_root = os.path.dirname(os.path.abspath(__file__))
if app_root not in sys.path:
    sys.path.append(app_root)
    logging.info(f"Added {app_root} to sys.path")

# Also add 'api' and 'services' to path explicitly if needed, but app_root should cover them
# as api.pricing etc.

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

@app.route(route="ping", methods=["GET"])
def ping_root(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse("pong from root", status_code=200)

# Robust Blueprint Registration
blueprints = [
    "api.pricing",
    "api.ocr",
    "api.bookings",
    "api.tessie",
    "api.reports",
    "api.copilot",
    "api.health",
    "api.operations"
]

registration_logs = []
for module_path in blueprints:
    try:
        logging.info(f"Attempting to register blueprint: {module_path}")
        module = importlib.import_module(module_path)
        if hasattr(module, 'bp'):
            app.register_blueprint(module.bp)
            registration_logs.append(f"SUCCESS: {module_path}")
            logging.info(f"Successfully registered blueprint: {module_path}")
        else:
            registration_logs.append(f"WARNING: {module_path} has no 'bp'")
            logging.warning(f"Blueprint {module_path} has no 'bp' attribute")
    except Exception as e:
        err_msg = f"ERROR: {module_path}: {str(e)}"
        registration_logs.append(err_msg)
        logging.error(err_msg)
        import traceback
        logging.error(traceback.format_exc())

@app.route(route="test_graph_auth", methods=["GET"])
def test_graph_auth(req: func.HttpRequest) -> func.HttpResponse:
    try:
        from services.graph import GraphClient
        client = GraphClient()
        token = client._get_token()
        # Validate by calling bookingBusinesses as requested
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get("https://graph.microsoft.com/v1.0/solutions/bookingBusinesses", headers=headers)
        
        return func.HttpResponse(
            json.dumps({
                "success": True, 
                "token_acquired": True,
                "booking_businesses_status": resp.status_code,
                "booking_businesses_data": resp.json() if resp.ok else resp.text
            }, indent=2), 
            status_code=200, 
            mimetype="application/json"
        )
    except Exception as e:
        import traceback
        return func.HttpResponse(
            json.dumps({
                "success": False, 
                "error": str(e),
                "traceback": traceback.format_exc()
            }, indent=2), 
            status_code=500, 
            mimetype="application/json"
        )

@app.route(route="diag", methods=["GET"])
def diag(req: func.HttpRequest) -> func.HttpResponse:
    import sys
    import os
    info = {
        "sys.path": sys.path,
        "cwd": os.getcwd(),
        "files": os.listdir('.'),
        "api_files": os.listdir('api') if os.path.exists('api') else "MISSING api",
        "registration_logs": registration_logs,
        "env_vars": {k: "SET" for k in os.environ.keys() if "KEY" in k or "SECRET" in k or "CONN" in k}
    }
    return func.HttpResponse(json.dumps(info, indent=2), mimetype="application/json")
