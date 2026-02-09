from datetime import datetime, timedelta, timezone
from .datetime_utils import normalize_to_utc

BUFFER_MINUTES = 30
DEFAULT_TRIP_DURATION = 60

# Hours: 0=Mon, 1=Tue, ... 6=Sun (Python default for .weekday())
# But TS used 0=Sun. I will map strict to TS logic.
# TS: 0=Sun, 1=Mon ... 6=Sat.
HOURS_CONFIG = {
    1: {"start": "04:30", "end": "22:00"}, # Mon
    2: {"start": "04:30", "end": "22:00"}, # Tue
    3: {"start": "04:30", "end": "22:00"}, # Wed
    4: {"start": "04:30", "end": "22:00"}, # Thu
    5: {"start": "04:30", "end": "23:30"}, # Fri (last slot 11:30 PM ends at midnight)
    6: {"start": "04:30", "end": "23:30"}, # Sat (last slot 11:30 PM ends at midnight)
    0: {"start": "08:00", "end": "17:00"}, # Sun (last slot 4:30 PM ends at 5:00 PM)
}

def get_hours_for_day(date_obj: datetime):
    # Python isoweekday: 1=Mon...7=Sun
    # Python weekday: 0=Mon...6=Sun
    # We want to match JS getDay(): 0=Sun, 1=Mon...6=Sat
    
    # Python weekday(): Mon=0, Tue=1, ... Sat=5, Sun=6
    # Map to JS: (d + 1) % 7
    # Mon(0)->1, Tue(1)->2, Sat(5)->6, Sun(6)->0
    py_day = date_obj.weekday()
    js_day = (py_day + 1) % 7
    
    return HOURS_CONFIG.get(js_day)

def calculate_buffers(appointment_start: datetime, duration_minutes=DEFAULT_TRIP_DURATION):
    # Ensure appointment_start is aware
    appointment_start = normalize_to_utc(appointment_start)
    
    buffer_start = appointment_start - timedelta(minutes=BUFFER_MINUTES)
    appointment_end = appointment_start + timedelta(minutes=duration_minutes)
    buffer_end = appointment_end + timedelta(minutes=BUFFER_MINUTES)
    
    return {
        "buffer_start": buffer_start,
        "appointment_start": appointment_start,
        "appointment_end": appointment_end,
        "buffer_end": buffer_end
    }

def time_ranges_overlap(start1, end1, start2, end2):
    return start1 < end2 and start2 < end1

def generate_time_slots_for_day(date_obj: datetime):
    """Generate time slots for a given day in Mountain Time, return as UTC."""
    from .datetime_utils import utc_to_local, get_timezone
    import pytz
    
    # Convert input to Mountain Time to determine the correct day and HOP
    mt_tz = get_timezone("CO")  # Mountain Time
    date_obj_utc = normalize_to_utc(date_obj)
    date_obj_mt = date_obj_utc.astimezone(mt_tz)
    
    # Get HOP for this day in Mountain Time
    hours = get_hours_for_day(date_obj_mt)
    if not hours:
        return []
    
    start_str = hours["start"]
    end_str = hours["end"]
    
    start_h, start_m = map(int, start_str.split(":"))
    end_h, end_m = map(int, end_str.split(":"))
    
    # Create start/end times in Mountain Time for this specific date
    # Use the date component from date_obj_mt
    current_start_mt = date_obj_mt.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
    
    # Handle end time
    if end_h == 0 and end_str == "00:00":
        # Midnight next day
        current_end_mt = date_obj_mt.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    else:
        current_end_mt = date_obj_mt.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
    
    # Generate slots in Mountain Time, then convert to UTC
    slots = []
    while current_start_mt < current_end_mt:
        # Convert to UTC for storage/API response
        slot_utc = current_start_mt.astimezone(pytz.UTC)
        slots.append(slot_utc)
        current_start_mt += timedelta(minutes=30)
        
    return slots
