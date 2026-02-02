import azure.functions as func
import sys
import os
import logging

# Path fix - MUST BE ABSOLUTE
app_root = os.path.dirname(os.path.abspath(__file__))
if app_root not in sys.path:
    sys.path.append(app_root)

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

from api.health import bp as health_bp
from api.pricing import bp as pricing_bp
from api.tessie import bp as tessie_bp
from api.ocr import bp as ocr_bp
from api.reports import bp as reports_bp
from api.bookings import bp as bookings_bp
from api.copilot import bp as copilot_bp

app.register_blueprint(health_bp)
app.register_blueprint(pricing_bp)
app.register_blueprint(tessie_bp)
app.register_blueprint(ocr_bp)
app.register_blueprint(reports_bp)
app.register_blueprint(bookings_bp)
app.register_blueprint(copilot_bp)

logging.info("All blueprints registered successfully.")
