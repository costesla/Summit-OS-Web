import azure.functions as func
import json

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

@app.route(route="ping", methods=["GET"])
def ping(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse("pong", status_code=200)

@app.route(route="vehicle-location", methods=["GET", "OPTIONS"])
def vehicle_location(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse(json.dumps({"lat": 0, "long": 0}), mimetype="application/json")
