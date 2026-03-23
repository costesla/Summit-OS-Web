import os
import sys

from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(__file__), '../../.env')
load_dotenv(env_path)
print(f"Loaded credentials from {env_path}")

# Now import and run
from setup_polaris_bookings import setup_polaris
setup_polaris()
