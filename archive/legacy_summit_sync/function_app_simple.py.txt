import logging
import azure.functions as func

app = func.FunctionApp()

@app.blob_trigger(arg_name="myblob", path="function-releases/{name}", connection="AzureWebJobsStorage")
def automation_trigger(myblob: func.InputStream):
    logging.info(f"Python Blob trigger processed blob \nName: {myblob.name}\nSize: {myblob.length} bytes")
    
    # Simple test - just log that we received the blob
    logging.info(f"Blob URL: {myblob.uri}")
    logging.info("Function executed successfully!")
