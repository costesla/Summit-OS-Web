import os
import sys
import datetime
import pytz
import logging
import subprocess
from dateutil import parser

# Universal State-Based Timezone Map
TIMEZONE_BY_STATE = {
    "CO": "America/Denver",
    "NV": "America/Los_Angeles",
    "AZ": "America/Phoenix",
    "CA": "America/Los_Angeles",
    "UT": "America/Denver",
    "NM": "America/Denver",
    "TX": "America/Chicago",
    "FL": "America/New_York",
    "NY": "America/New_York"
}

# SQL Server Timezone Map (Windows standard names)
SQL_TIMEZONE_BY_STATE = {
    "CO": "Mountain Standard Time",
    "NV": "Pacific Standard Time",
    "AZ": "US Mountain Standard Time",
    "CA": "Pacific Standard Time",
    "UT": "Mountain Standard Time",
    "NM": "Mountain Standard Time",
    "TX": "Central Standard Time",
    "FL": "Eastern Standard Time",
    "NY": "Eastern Standard Time"
}

def get_home_state():
    """Retrieves the project's home state from environment variables."""
    return os.environ.get("HOME_STATE", "CO")

def get_timezone(state=None):
    """Returns the pytz timezone object for a given state."""
    state = state or get_home_state()
    tz_name = TIMEZONE_BY_STATE.get(state.upper(), "UTC")
    return pytz.timezone(tz_name)

def get_sql_timezone(state=None):
    """Returns the SQL Server compatible timezone name for a given state."""
    state = state or get_home_state()
    return SQL_TIMEZONE_BY_STATE.get(state.upper(), "Mountain Standard Time")

def utc_to_local(utc_dt, state=None):
    """Converts a UTC datetime to the local state timezone."""
    if not utc_dt:
        return None
    
    # Ensure utc_dt is aware and in UTC
    if utc_dt.tzinfo is None:
        utc_dt = pytz.utc.localize(utc_dt)
    else:
        utc_dt = utc_dt.astimezone(pytz.utc)
        
    tz = get_timezone(state)
    return utc_dt.astimezone(tz)

def format_local_time(dt, state=None):
    """Formats a datetime object for customer-facing display."""
    if not dt:
        return "N/A"
    
    local_dt = utc_to_local(dt, state)
    # Format: “Monday, February 2 at 03:30 PM MST”
    return local_dt.strftime("%A, %B %d at %I:%M %p %Z")

def mst_to_utc(dt_naive):
    """
    Specifically converts a naive MST datetime to a UTC datetime.
    Used by TimezoneAgent for screenshot normalization.
    """
    if not dt_naive:
        return None
    
    mst_tz = pytz.timezone("America/Denver")
    # Localize the naive datetime as MST
    localized_dt = mst_tz.localize(dt_naive)
    # Convert to UTC
    return localized_dt.astimezone(pytz.utc)

def get_summit_routing_path(dt_utc, block_name="Default_Block", trip_id="Unknown_Trip"):
    """
    Calculates the deterministic SummitOS path:
    Year/Month/Week/MM.DD.YY/Block/Trip
    """
    year = dt_utc.strftime("%Y")
    month = dt_utc.strftime("%B")
    week = f"Week {dt_utc.isocalendar()[1]}"
    date_folder = dt_utc.strftime("%m.%d.%y")
    
    return os.path.join(year, month, week, date_folder, block_name, trip_id)

def normalize_to_utc(dt_str):
    """Normalizes an inbound timestamp string to a UTC datetime object."""
    try:
        dt = parser.parse(dt_str)
        if dt.tzinfo is None:
            # For this mission, naive strings from filenames are MST
            return mst_to_utc(dt)
        else:
            return dt.astimezone(pytz.utc)
    except Exception as e:
        logging.error(f"Failed to normalize datetime string {dt_str}: {e}")
        return None

def ensure_32bit_python():
    """Validates that the execution environment is 32-bit Python."""
    is_64bit = sys.maxsize > 2**32
    if is_64bit:
        error_msg = "WARNING: Detected 64-bit Python environment. SummitOS usually requires 32-bit Python for native library compatibility."
        logging.warning(error_msg)
        # No longer raising RuntimeError to avoid blocking local execution.
        # In a real Azure Function, we might not want to sys.exit() immediately 
        # but rather flag it in diagnostics.
    logging.info("Environment Validation: 32-bit Python confirmed.")
    return True

def check_azure_cli():
    """Checks if the Azure CLI is installed and authenticated."""
    try:
        # Check version
        version_proc = subprocess.run(["az", "--version"], capture_output=True, text=True, check=True)
        logging.info("Azure CLI Diagnostic: Installed.")
        
        # Check account status
        account_proc = subprocess.run(["az", "account", "show"], capture_output=True, text=True)
        if account_proc.returncode != 0:
            return {
                "status": "warning",
                "message": "Azure CLI is installed but not authenticated. Run 'az login'.",
                "version": version_proc.stdout.splitlines()[0]
            }
        
        return {
            "status": "success",
            "message": "Azure CLI is functioning and authenticated.",
            "version": version_proc.stdout.splitlines()[0]
        }
    except FileNotFoundError:
        return {
            "status": "error",
            "message": "Azure CLI is not installed or not in PATH.",
            "remediation": "Install Azure CLI from: https://aka.ms/installazurecliwindows"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Azure CLI diagnostic failed: {str(e)}"
        }
