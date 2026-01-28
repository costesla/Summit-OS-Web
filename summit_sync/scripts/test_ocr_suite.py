import os
import sys
import unittest
import logging
from dotenv import load_dotenv

# Add parent directory to path so we can import lib
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.ocr import OCRClient

# Setup logging
logging.basicConfig(level=logging.INFO)

class TestOCRClient(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        load_dotenv()
        cls.ocr = OCRClient()

    def test_initialization(self):
        """Test if the client initializes correctly with environment variables."""
        if os.environ.get("AZURE_VISION_ENDPOINT"):
            self.assertIsNotNone(self.ocr.client, "OCR Client should be initialized when endpoint is present.")
        else:
            self.assertIsNone(self.ocr.client, "OCR Client should be None when endpoint is missing.")

    def test_parse_ubertrip_win(self):
        """Test parsing an Uber trip that should be a 'Win'."""
        mock_text = """
        Picking up Ethan
        Comfort
        Rider payment $24.52
        Your earnings $14.12
        Tip $4.00
        12.5 mi
        24 min
        """
        data = self.ocr.parse_ubertrip(mock_text)
        self.assertEqual(data["rider"], "Ethan")
        self.assertEqual(data["rider_payment"], 24.52)
        self.assertEqual(data["driver_total"], 14.12)
        self.assertEqual(data["tip"], 4.0)
        self.assertEqual(data["distance_miles"], 12.5)
        self.assertEqual(data["duration_minutes"], 24)
        self.assertEqual(data["result"], "Win")

    def test_parse_ubertrip_loss(self):
        """Test parsing an Uber trip that should be a 'Loss'."""
        mock_text = """
        Picking up Sarah
        UberX
        Price $30.00
        You earned $10.00
        5.0 mi
        15 min
        """
        data = self.ocr.parse_ubertrip(mock_text)
        self.assertEqual(data["rider"], "Sarah")
        self.assertEqual(data["rider_payment"], 30.0)
        self.assertEqual(data["driver_total"], 10.0)
        self.assertEqual(data["result"], "Loss")

    def test_classify_image_uber(self):
        """Test classification of Uber-related text."""
        text = "Order Details\nYour earnings $15.00\nUber"
        self.assertEqual(self.ocr.classify_image(text), "Uber_Core")

    def test_classify_image_expense(self):
        """Test classification of expense-related text."""
        text = "Starbucks Coffee\nTotal: $5.45"
        self.assertEqual(self.ocr.classify_image(text), "Expense")

    def test_classify_image_aviation(self):
        """Test classification of aviation-related text."""
        text = "Flightradar24\nFlight Path"
        self.assertEqual(self.ocr.classify_image(text), "Aviation_Context")

    def test_classify_image_environmental(self):
        """Test classification of environmental-related text."""
        text = "WeatherWise\nRadar Image"
        self.assertEqual(self.ocr.classify_image(text), "Environmental_Context")

    def test_extract_text_stream_connection(self):
        """Test connectivity to Azure AI Vision via stream (using a dummy call if no image)."""
        if not self.ocr.client:
            self.skipTest("OCR Client not initialized. Skipping connection test.")
        
        # We'll try to analyze a non-existent file to see if we get a specific error or if it fails gracefully
        # In a real scenario, we'd use a small valid image.
        test_image = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "public", "logo.png")
        if os.path.exists(test_image):
            try:
                text = self.ocr.extract_text_from_stream(test_image)
                # We don't necessarily expect text from the logo, but it shouldn't crash.
                logging.info(f"Connection test successful. Extracted text length: {len(text) if text else 0}")
            except Exception as e:
                self.fail(f"OCR Stream extraction failed with error: {str(e)}")
        else:
            self.skipTest(f"Test image not found at {test_image}")

if __name__ == "__main__":
    unittest.main()
