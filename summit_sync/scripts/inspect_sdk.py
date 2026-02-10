
import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from azure.ai.vision.imageanalysis import ImageAnalysisClient
from azure.core.credentials import AzureKeyCredential
from dotenv import load_dotenv

load_dotenv()
endpoint = os.environ.get("AZURE_VISION_ENDPOINT")
key = os.environ.get("AZURE_VISION_KEY")

client = ImageAnalysisClient(endpoint=endpoint, credential=AzureKeyCredential(key))

print("Client methods:")
print(dir(client))

import inspect
print("\nAnalyze signature:")
try:
    print(inspect.signature(client.analyze))
except Exception as e:
    print(e)
