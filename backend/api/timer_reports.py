import logging
import azure.functions as func
import os
import csv
import io
import datetime
from azure.storage.blob import BlobServiceClient
from services.database import DatabaseClient

bp = func.Blueprint()

@bp.schedule(schedule="0 0 2 * * *", arg_name="myTimer", run_on_startup=False,
              use_monitor=False) 
def timer_reports(myTimer: func.TimerRequest) -> None:
    if myTimer.past_due:
        logging.info('The timer is past due!')

    logging.info('Python timer trigger function started execution.')
    
    try:
        # 1. Connect to Database
        db = DatabaseClient()
        
        # 2. Connect to Blob Storage
        connect_str = os.environ.get("AZUREWEBJOBSSTORAGE")
        if not connect_str:
            logging.error("AZUREWEBJOBSSTORAGE not found.")
            return

        blob_service_client = BlobServiceClient.from_connection_string(connect_str)
        container_name = "reports"
        
        # Create container if not exists
        try:
            container_client = blob_service_client.get_container_client(container_name)
            if not container_client.exists():
                container_client.create_container()
        except Exception as e:
            logging.error(f"Container creation failed: {e}")

        # 3. Define Reports to Export
        reports = [
            {
                "view": "Reports.MobilityEvents",
                "filename_prefix": "Report_MobilityEvents"
            },
            {
                "view": "Reports.TripAnalytics", 
                "filename_prefix": "Report_Uber_Trips" # Matches user request "Report_Uber_Trips_YYYY-MM-DD.csv"
            }
        ]

        today_str = datetime.datetime.now().strftime("%Y-%m-%d")

        for report in reports:
            view_name = report["view"]
            prefix = report["filename_prefix"]
            
            logging.info(f"Exporting {view_name}...")
            
            # Fetch Data
            try:
                # Dynamic Column Handling to fix datetimeoffset issue
                try:
                    schema, table = view_name.split('.')
                    col_query = f"""
                        SELECT COLUMN_NAME, DATA_TYPE 
                        FROM INFORMATION_SCHEMA.COLUMNS 
                        WHERE TABLE_SCHEMA = '{schema}' AND TABLE_NAME = '{table}'
                        ORDER BY ORDINAL_POSITION
                    """
                    cols_data = db.execute_query_with_results(col_query)
                    
                    select_parts = []
                    if cols_data:
                        for col in cols_data:
                            # Dictionary keys from pyodbc row conversion (usually lowercase or matching db)
                            # DatabaseClient returns dicts, let's assume case matches query or is standard
                            # Safe retrieval
                            c_name = col.get('COLUMN_NAME') or col.get('column_name')
                            d_type = col.get('DATA_TYPE') or col.get('data_type')
                            
                            if 'datetimeoffset' in str(d_type):
                                select_parts.append(f"CAST({c_name} AS VARCHAR(30)) AS {c_name}")
                            else:
                                select_parts.append(c_name)
                        safe_query = f"SELECT {', '.join(select_parts)} FROM {view_name}"
                    else:
                        safe_query = f"SELECT * FROM {view_name}"
                except Exception as ex:
                    logging.warning(f"Schema inspection failed: {ex}. Falling back to SELECT *")
                    safe_query = f"SELECT * FROM {view_name}"

                results = db.execute_query_with_results(safe_query)
                
                if results:
                    # Generate CSV
                    output = io.StringIO()
                    
                    # services.database.execute_query_with_results returns list of dicts
                    first_row = results[0]
                    fieldnames = list(first_row.keys())
                    
                    writer = csv.DictWriter(output, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(results)
                    
                    csv_content = output.getvalue()
                    
                    # Upload to Blob
                    blob_name = f"{prefix}_{today_str}.csv"
                    blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
                    
                    blob_client.upload_blob(csv_content, overwrite=True)
                    logging.info(f"Uploaded {blob_name} ({len(results)} rows)")
                else:
                    logging.warning(f"No data found for {view_name}")

            except Exception as e:
                logging.error(f"Failed to export {view_name}: {e}")

    except Exception as e:
        logging.error(f"Timer Reports Error: {e}")
