import sys
import os
import datetime
import pytz
from unittest.mock import MagicMock

# Add current dir to path for imports
sys.path.append(os.path.dirname(__file__))

from services.datetime_utils import normalize_to_utc
from services.customer_pricing import CustomerPricingProfile

def test_pricing_expiry_safe():
    print("\n--- Testing Pricing Expiry Safety ---")
    # This should NOT throw "can't compare offset-naive and offset-aware datetimes"
    # Even if datetime.now() usually returns naive.
    try:
        is_expired = CustomerPricingProfile.is_pricing_expired("2026-03-01")
        print(f"[OK] Pricing expiry check completed. Expired: {is_expired}")
    except TypeError as e:
        print(f"[FAIL] Type mismatch in pricing: {e}")
    except Exception as e:
        print(f"[FAIL] Unexpected error in pricing: {e}")

def test_normalization_robustness():
    print("\n--- Testing Normalization Robustness ---")
    # Test normalization of mix of types
    ts_str = "2026-02-02T15:30:00Z"
    ts_naive = datetime.datetime(2026, 2, 2, 15, 30)
    ts_aware = datetime.datetime(2026, 2, 2, 15, 30, tzinfo=pytz.utc)
    
    norm_str = normalize_to_utc(ts_str)
    norm_naive = normalize_to_utc(ts_naive)
    norm_aware = normalize_to_utc(ts_aware)
    
    if all(dt.tzinfo is not None for dt in [norm_str, norm_naive, norm_aware]):
        print("[OK] All normalization types returned UTC-aware objects.")
    else:
        print("[FAIL] Normalization failed to enforce UTC awareness.")

def test_availability_logic():
    print("\n--- Testing Availability Comparison Logic ---")
    # Mocking the overlap check pattern in bookings.py
    evt_start = normalize_to_utc("2026-02-02T15:00:00Z")
    evt_end = normalize_to_utc("2026-02-02T16:00:00Z")
    
    # Simulate a buffer that might be naive or aware
    buf_start = datetime.datetime(2026, 2, 2, 15, 30) # Naive
    buf_end = datetime.datetime(2026, 2, 2, 16, 30) # Naive
    
    # The fix uses normalize_to_utc on buffers too
    buf_start_utc = normalize_to_utc(buf_start)
    buf_end_utc = normalize_to_utc(buf_end)
    
    try:
        # Comparison test
        overlap = buf_start_utc < evt_end and evt_start < buf_end_utc
        print(f"[OK] Overlap check completed safely. Overlap: {overlap}")
    except TypeError as e:
        print(f"[FAIL] Overlap check threw TypeError: {e}")

def test_calendar_loop_safety():
    print("\n--- Testing Calendar Loop Safety ---")
    from services.calendar import generate_time_slots_for_day
    # Even if we pass a naive date, it should handle it aware now
    ts_naive = datetime.datetime(2026, 2, 2)
    try:
        slots = generate_time_slots_for_day(ts_naive)
        if slots and slots[0].tzinfo:
            print(f"[OK] Generated {len(slots)} aware slots from naive input.")
        else:
            print("[FAIL] Slots are naive or empty.")
    except TypeError as e:
        print(f"[FAIL] Calendar loop threw TypeError: {e}")

if __name__ == "__main__":
    test_pricing_expiry_safe()
    test_normalization_robustness()
    test_availability_logic()
    test_calendar_loop_safety()
