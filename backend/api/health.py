import logging
import azure.functions as func
import json
import os
import sys

bp = func.Blueprint()

@bp.route(route="health", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def health_check(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse("OK", status_code=200)

@bp.route(route="ping", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def ping(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse("pong", status_code=200)

@bp.route(route="sql-probe", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
def sql_probe(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("SQL probe endpoint invoked")
    try:
        import pyodbc
        conn_str = os.environ.get("SQL_CONNECTION_STRING")
        with pyodbc.connect(conn_str, timeout=10) as conn:
            conn.autocommit = True
            return func.HttpResponse(json.dumps({"status": "success", "message": "SQL Connection Verified"}), status_code=200, mimetype="application/json")
    except Exception as e:
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500, mimetype="application/json")
