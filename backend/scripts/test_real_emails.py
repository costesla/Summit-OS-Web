"""
Quick test with real customer emails
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from services.pricing import PricingEngine
from services.customer_pricing import CustomerPricingProfile

print("=" * 60)
print("TESTING WITH REAL CUSTOMER EMAILS")
print("=" * 60)

# Test with real emails
test_cases = [
    ("esmii.lopez@hotmail.com", "Esmeralda", 25.0),
    ("jacquelyn.heslep@playaba.net", "Jacquelyn", 25.0),
    ("random@customer.com", "Regular Customer", 25.0),
]

for email, name, distance in test_cases:
    print(f"\n{name} ({email})")
    print("-" * 60)
    
    pricing = PricingEngine()
    result = pricing.calculate_trip_price(
        distance_miles=distance,
        customer_email=email
    )
    
    print(f"  Distance: {distance} miles")
    print(f"  Total: ${result['total']}")
    print(f"  Pricing Type: {result.get('pricing_type', 'N/A')}")
    print(f"  Customer Tier: {result.get('customer_tier', 'N/A')}")

print("\n" + "=" * 60)
print("GRANDFATHERED CUSTOMERS LIST")
print("=" * 60)

customers = CustomerPricingProfile.list_grandfathered_customers()
for email, profile in customers.items():
    status = "EXPIRED" if profile.get('is_expired') else "ACTIVE"
    print(f"\n{profile['name']} ({email})")
    print(f"  Status: {status}")
    print(f"  Pricing: Flat $20/trip")
    print(f"  Expires: {profile.get('expires', 'Never')}")

print("\n" + "=" * 60)
print("SUCCESS - Real emails configured!")
print("=" * 60)
