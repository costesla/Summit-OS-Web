
import sys
import os
import importlib
import logging

# Configure logging to see output
logging.basicConfig(level=logging.INFO)

# Path fix
app_root = os.path.dirname(os.path.abspath(__file__))
if app_root not in sys.path:
    sys.path.append(app_root)

blueprints = [
    "api.pricing",
    "api.ocr",
    "api.bookings",
    "api.tessie",
    "api.reports",
    "api.copilot",
    "api.health"
]

print("--- Starting Blueprint Diagnostic ---")
for module_path in blueprints:
    try:
        print(f"Loading {module_path}...")
        module = importlib.import_module(module_path)
        if hasattr(module, 'bp'):
            print(f"SUCCESS: {module_path} loaded and has 'bp'")
        else:
            print(f"WARNING: {module_path} loaded but MISSING 'bp'")
    except Exception as e:
        print(f"FAILED: {module_path}: {str(e)}")
        import traceback
        traceback.print_exc()
print("--- Diagnostic Complete ---")
