import os
import logging
import time
import re
from azure.identity import DefaultAzureCredential
from azure.ai.vision.imageanalysis import ImageAnalysisClient
from azure.ai.vision.imageanalysis.models import VisualFeatures
from azure.core.credentials import AzureKeyCredential

class OCRClient:
    def __init__(self):
        self.endpoint = os.environ.get("AZURE_VISION_ENDPOINT")
        self.key = os.environ.get("AZURE_VISION_KEY")
        
        self.client = None

        # Try API Key first if available
        if self.key:
            try:
                self.client = ImageAnalysisClient(
                    endpoint=self.endpoint,
                    credential=AzureKeyCredential(self.key)
                )
                logging.info(f"OCR Client initialized with API Key at endpoint: {self.endpoint}")
            except Exception as e:
                logging.warning(f"Failed to initialize with API Key: {e}")
                self.client = None

        # Fallback to DefaultAzureCredential if Key failed or was missing
        if not self.client:
            try:
                self.client = ImageAnalysisClient(
                    endpoint=self.endpoint,
                    credential=DefaultAzureCredential()
                )
                logging.info(f"OCR Client initialized with DefaultAzureCredential at endpoint: {self.endpoint}")
            except Exception as e:
                logging.error(f"Failed to initialize OCR Client with AAD: {str(e)}")
                self.client = None

    def extract_text(self, image_url):
        """
        Extracts text from an image URL using Azure AI Vision (Image Analysis SDK).
        """
        if not self.client:
            logging.error("OCR Client not initialized.")
            return None

        logging.info(f"Starting OCR extraction for URL: {image_url}")
        try:
            result = self.client.analyze(
                image_url=image_url,
                visual_features=[VisualFeatures.READ]
            )
            return self._parse_analysis_result(result)
        except Exception as e:
            logging.error(f"Error during OCR extraction (URL): {str(e)}")
            return None

    def extract_text_from_stream(self, image_path):
        """
        Extracts text by streaming the local file directly to Azure.
        """
        if not self.client:
            return None

        logging.info(f"Starting OCR extraction for local stream: {os.path.basename(image_path)}")
        try:
            with open(image_path, "rb") as image_stream:
                result = self.client.analyze(
                    image_data=image_stream,
                    visual_features=[VisualFeatures.READ]
                )
            return self._parse_analysis_result(result)
        except Exception as e:
            logging.error(f"Error during OCR extraction (Stream): {str(e)}")
            return None

    def _parse_analysis_result(self, result):
        """Helper to parse text from the Image Analysis result."""
        try:
            if result.read is not None:
                text_lines = []
                for block in result.read.blocks:
                    for line in block.lines:
                        text_lines.append(line.text)
                return "\n".join(text_lines)
            return None
        except Exception as e:
            logging.error(f"Error parsing OCR result: {str(e)}")
            return None

    def parse_ubertrip(self, text):
        """
        Parses raw text from an Uber receipt to extract key details.
        Ported from SummitOS_Stage5b_Intelligence.ps1
        """
        data = {
            "rider": "Unknown",
            "rider_payment": 0.0,
            "driver_total": 0.0,
            "tip": 0.0,
            "uber_cut": 0.0,
            "distance_miles": 0.0,
            "duration_minutes": 0.0,
            "service_type": None,
            "airport": False,
            "result": "Loss"
        }
        
        if not text:
            return data

        # 1. Rider Name
        # "Picking up Ethan"
        match = re.search(r"Picking up (.+)", text)
        if match:
            data["rider"] = match.group(1).strip()
        
        # 2. Financials
        # Rider Payment: "Rider payment $15.78" or "Price $15.78"
        # Note: Python regex needs escaped $ for literal dollar sign if it's not end of line anchor.
        # But in raw strings, we just look for patterns.
        match = re.search(r"(?:Rider payment|Price|Total)\s*[\$]?([0-9]+\.[0-9]{2})", text, re.IGNORECASE)
        if match:
            data["rider_payment"] = float(match.group(1))

        # Driver Earnings: "Your earnings $7.03" or "You earned $7.03" or standalone "$12.36" (Offer screens)
        match = re.search(r"(?:Your earnings|You earned)\s*[\$]?([0-9]+\.[0-9]{2})", text, re.IGNORECASE)
        if match:
            data["driver_total"] = float(match.group(1))
        else:
            # Fallback for offer/accept screens: Look for the first major dollar amount
            # Usually looks like "$12.36" on a line by itself
            match = re.search(r"^\s*[\$]([0-9]+\.[0-9]{2})\s*$", text, re.MULTILINE)
            if match:
                data["driver_total"] = float(match.group(1))
                # For offers, we assume rider payment is at least the driver total
                data["rider_payment"] = max(data["rider_payment"], data["driver_total"])

        # Tip: "Tip $3.00"
        match = re.search(r"Tip\s*[\$]?([0-9]+\.[0-9]{2})", text, re.IGNORECASE)
        if match:
            data["tip"] = float(match.group(1))
            
        # Private Payment override (Venmo style "+ $15.00")
        match = re.search(r"\+\s?\$?([0-9]+\.[0-9]{2})", text)
        if match and "Venmo" in text: # Simple check for Venmo context
            data["driver_total"] = float(match.group(1))
            data["rider_payment"] = data["driver_total"] # Private trip assumption

        # 3. Stats
        # Distance: "12.5 mi"
        match = re.search(r"([0-9.]+)\s*mi", text, re.IGNORECASE)
        if match:
            data["distance_miles"] = float(match.group(1))

        # Duration: "24 min"
        match = re.search(r"([0-9]+)\s*min", text, re.IGNORECASE)
        if match:
            data["duration_minutes"] = int(match.group(1))

        # 4. Service Type
        if re.search(r"(Comfort|Black|XL|Pet|Green)", text, re.IGNORECASE):
            match = re.search(r"(Comfort|Black|XL|Pet|Green)", text, re.IGNORECASE)
            data["service_type"] = match.group(1)
        if "Exclusive" in text:
            data["service_type"] = (data["service_type"] or "") + " Exclusive"

        # 5. Logic Checks
        if re.search(r"(Airport|DEN|DIA|MCO)", text, re.IGNORECASE):
            data["airport"] = True

        # Calculations
        data["uber_cut"] = data["rider_payment"] - data["driver_total"]
        
        # Win/Loss Logic (Driver check > 50%)
        if data["rider_payment"] > 0:
            if (data["driver_total"] / data["rider_payment"]) >= 0.5:
                data["result"] = "Win"
        elif data["driver_total"] > 0:
            data["result"] = "Win" # Optimistic

        return data

    def classify_image(self, text):
        """
        Classifies the image text into a Summit Sync category:
        - Uber_Core
        - Expense
        - Aviation_Context
        - Environmental_Context
        """
        if not text:
            return "Unknown"
        
        text_lower = text.lower()

        # 1. Aviation
        if "flightradar24" in text_lower or re.search(r"flight\s+path", text_lower):
            return "Aviation_Context"

        # 2. Environmental
        if "weatherwise" in text_lower or re.search(r"radar\s+image", text_lower):
            return "Environmental_Context"

        # 3. Expense (Business Context)
        expense_keywords = [
            "starbucks", "mcdonald", "tacobell", "shell", "chevron", 
            "circle k", "7-eleven", "costco gas", "fuel", "gasoline"
        ]
        if any(keyword in text_lower for keyword in expense_keywords):
            return "Expense"

        # 4. Uber Core
        uber_keywords = ["uber", "trip detail", "rider payment", "your earnings", "picking up"]
        if any(keyword in text_lower for keyword in uber_keywords):
            return "Uber_Core"

        return "Unknown"

    def parse_weather(self, text):
        """
        Parses weather information from a screenshot.
        Looking for: Temperature (e.g., 32°), Condition (e.g., Clear, Snow).
        """
        data = {
            "temperature": None,
            "condition": "Unknown",
            "location": "Colorado Springs" # Default based on project context
        }
        
        if not text:
            return data

        # Look for temperature: "32°" or "32 F"
        match = re.search(r"(\d+)\s?[°F]", text)
        if match:
            data["temperature"] = int(match.group(1))

        # Look for common conditions
        conditions = ["Clear", "Sunny", "Cloudy", "Rain", "Snow", "Fog", "Overcast"]
        for cond in conditions:
            if cond.lower() in text.lower():
                data["condition"] = cond
                break
        
        return data
