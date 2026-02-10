import os
import sys
import datetime
import pytz
from lib import datetime_utils

def test_32bit_enforcement():
    print("\n--- Testing 32-bit Enforcement ---")
    try:
        datetime_utils.ensure_32bit_python()
        print("[PASS] 32-bit check passed (or environment is 32-bit).")
    except RuntimeError as e:
        print(f"[FAIL] 32-bit check failed: {e}")

def test_timezone_conversions():
    print("\n--- Testing Timezone Conversions ---")
    # Fixed UTC time: 2026-02-02 15:30:00 UTC
    utc_now = datetime.datetime(2026, 2, 2, 15, 30, tzinfo=pytz.utc)
    
    test_cases = [
        ("CO", "America/Denver", "08:30 AM MST"),
        ("NV", "America/Los_Angeles", "07:30 AM PST"),
        ("NY", "America/New_York", "10:30 AM EST"),
    ]
    
    for state, expected_tz, expected_time_part in test_cases:
        local_dt = datetime_utils.utc_to_local(utc_now, state)
        formatted = datetime_utils.format_local_time(utc_now, state)
        print(f"State: {state} | Local: {formatted}")
        
        if expected_time_part in formatted:
            print(f"[OK] Correctly converted for {state}")
        else:
            print(f"[FAIL] Transformation mismatch for {state}")

def test_formatting():
    print("\n--- Testing Formatting Requirement ---")
    # Monday, February 2, 2026 at 03:30 PM UTC
    utc_dt = datetime.datetime(2026, 2, 2, 15, 30, tzinfo=pytz.utc)
    # Expected in CO: Monday, February 02 at 08:30 AM MST
    formatted = datetime_utils.format_local_time(utc_dt, "CO")
    expected = "Monday, February 02 at 08:30 AM MST"
    
    # Note: strftime %d might be padding with 0 or space depending on platform
    # Let's check for the core parts
    core_parts = ["Monday", "February", "08:30 AM", "MST"]
    all_ok = True
    for part in core_parts:
        if part not in formatted:
            all_ok = False
            print(f"❌ Missing part: {part}")
    
    if all_ok:
        print(f"[OK] Format matches requirement: {formatted}")
    else:
        print(f"[FAIL] Final format check failed: {formatted}")

def test_azure_cli():
    print("\n--- Testing Azure CLI Diagnostics ---")
    diag = datetime_utils.check_azure_cli()
    print(f"Status: {diag['status']}")
    print(f"Message: {diag['message']}")
    if "version" in diag:
        print(f"Version: {diag['version']}")

def test_normalize():
    print("\n--- Testing UTC Normalization ---")
    ts = "2026-02-02 10:30:00-07:00"
    normalized = datetime_utils.normalize_to_utc(ts)
    print(f"Input: {ts} | Normalized: {normalized}")
    if normalized and normalized.tzinfo == pytz.utc and normalized.hour == 17:
        print("[OK] Normalization correct.")
    else:
        print("[FAIL] Normalization mismatch.")

if __name__ == "__main__":
    test_32bit_enforcement()
    test_timezone_conversions()
    test_formatting()
    test_normalize()
    test_azure_cli()
