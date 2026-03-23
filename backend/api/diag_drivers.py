import pyodbc
import azure.functions as func

bp = func.Blueprint()

@bp.route(route="diag/drivers", methods=["GET"])
def diag_drivers(req: func.HttpRequest) -> func.HttpResponse:
    import os
    drivers = pyodbc.drivers()
    conn_str = os.environ.get("SQL_CONNECTION_STRING", "NOT SET")
    
    # Mask password
    masked_conn_str = conn_str
    if "Password" in conn_str:
        masked_conn_str = "HIDDEN"

    result = {
        "drivers": drivers,
        "conn_str_masked": masked_conn_str,
        "os_name": os.name,
        "test_connection": "PENDING"
    }
    
    # Try connecting with patches
    try:
        if os.name == 'posix' and 'ODBC Driver 17' in conn_str:
            conn_str = conn_str.replace('ODBC Driver 17', 'ODBC Driver 18')
            result['patched_conn_str'] = "Applied Driver 18 patch"
            
        conn = pyodbc.connect(conn_str)
        result['test_connection'] = "SUCCESS"
        conn.close()
    except Exception as e:
        result['test_connection'] = f"FAILED: {str(e)}"
        
    return func.HttpResponse(str(result), status_code=200)
