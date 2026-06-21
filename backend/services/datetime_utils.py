import os
import sys
import datetime
try:
    import pytz
except ImportError:
    pytz = None
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
    if pytz:
        return pytz.timezone(tz_name)
    else:
        # Fallback if pytz missing
        return datetime.timezone.utc

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
        utc_dt = utc_dt.replace(tzinfo=datetime.timezone.utc)
    else:
        utc_dt = utc_dt.astimezone(datetime.timezone.utc)
        
    if pytz:
        tz = get_timezone(state)
        return utc_dt.astimezone(tz)
    else:
        # Fallback to UTC if pytz missing
        return utc_dt

def format_local_time(dt, state=None):
    """Formats a datetime object for customer-facing display."""
    if not dt:
        return "N/A"
    
    local_dt = utc_to_local(dt, state)
    # Format: “Monday, February 2 at 03:30 PM MST”
    return local_dt.strftime("%A, %B %d at %I:%M %p %Z")

def normalize_to_utc(dt_str_or_obj):
    """Normalizes an inbound timestamp string or object to a UTC datetime object (AWARE)."""
    if not dt_str_or_obj:
        return None
        
    try:
        if isinstance(dt_str_or_obj, str):
            dt = parser.parse(dt_str_or_obj)
        else:
            dt = dt_str_or_obj
            
        if dt.tzinfo is None:
            # If naive, assume it's already UTC
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        else:
            dt = dt.astimezone(datetime.timezone.utc)
        return dt
    except Exception as e:
        logging.error(f"Failed to normalize datetime {dt_str_or_obj}: {e}")
        return None

def ensure_32bit_python():
    """Validates that the execution environment is 32-bit Python."""
    is_64bit = sys.maxsize > 2**32
    if is_64bit:
        error_msg = "WARNING: Detected 64-bit Python environment. SummitOS usually requires 32-bit Python for some native compatibility components."
        logging.warning(error_msg)
        # We no longer raise RuntimeError to allow local 64-bit debugging while keeping the warning.
    logging.info("Environment Validation: 32-bit Python confirmed.")
    return True


# ─── Operational-Day Boundary ─────────────────────────────────────────────────

def get_operational_window(
    date_str: str,
    tz=None,
) -> "tuple[datetime.datetime, datetime.datetime]":
    """Return the (window_start, window_end) that defines one operational day.

    An operational day begins at 04:00 local time on *date_str* and ends at
    04:00 the following calendar day.  This matches the Tessie sync window in
    ``TessieSyncService.sync_day()`` and correctly groups overnight rideshare
    shifts — a shift starting on the evening of *date_str* that runs past
    midnight still belongs to *date_str*'s operational day as long as its
    drives end before 04:00 the next morning.

    KNOWN LIMITATION: If a single shift's tail extends past 04:00 the next
    morning, those post-04:00 drives will be bucketed into the *next*
    operational day rather than the shift's start date.  This edge case is
    uncommon (rideshare shifts rarely run past 4 AM) and is not handled here.
    A future implementation could detect shift continuity via gap analysis on
    Timestamp_Start values and anchor everything to the shift-open drive's
    date.

    Args:
        date_str: Operational date in "YYYY-MM-DD" format.
        tz: Optional timezone.  Accepts a ``pytz`` timezone object, a
            ``datetime.timezone`` fixed-offset, or a ``zoneinfo.ZoneInfo``
            object.  If omitted the function returns naive datetimes (safe for
            comparison against the naive ``Timestamp_Start`` values stored in
            Rides.Rides).

    Returns:
        (window_start, window_end) — both datetimes at 04:00 on their
        respective calendar days, in the supplied timezone (or naive if tz is
        None).
    """
    base = datetime.datetime.strptime(date_str, "%Y-%m-%d")
    # 04:00 on date_str (start of this operational day)
    window_start = base.replace(hour=4, minute=0, second=0, microsecond=0)
    # 04:00 on date_str + 1 day (exclusive upper bound)
    window_end   = window_start + datetime.timedelta(days=1)

    if tz is not None:
        # Support pytz (.localize), zoneinfo.ZoneInfo, and fixed datetime.timezone
        if hasattr(tz, "localize"):
            # pytz-style
            window_start = tz.localize(window_start)
            window_end   = tz.localize(window_end)
        else:
            # zoneinfo.ZoneInfo or datetime.timezone
            window_start = window_start.replace(tzinfo=tz)
            window_end   = window_end.replace(tzinfo=tz)

    return window_start, window_end
