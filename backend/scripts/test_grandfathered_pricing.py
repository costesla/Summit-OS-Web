"""
Test script for grandfathered customer pricing
Tests Esmeralda and Jacquelyn's flat $20 pricing
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from services.pricing import PricingEngine
from services.customer_pricing import CustomerPricingProfile

print("=" * 60)
print("GRANDFATHERED CUSTOMER PRICING TEST")
print("=" * 60)

# Test distances
test_distances = [3.0, 10.0, 25.0, 50.0]

print("\n1. Testing Esmeralda (Flat $20 pricing)")
print("-" * 60)
for distance in test_distances:
    pricing = PricingEngine()
    result = pricing.calculate_trip_price(
        distance_miles=distance,
        customer_email="esmeralda@example.com"  # Update with real email
    )
    print(f"  Distance: {distance} mi")
    print(f"  Total: ${result['total']}")
    print(f"  Pricing Type: {result.get('pricing_type', 'N/A')}")
    print(f"  Tier: {result.get('customer_tier', 'N/A')}")
    print()

print("\n2. Testing Jacquelyn (Flat $20 pricing)")
print("-" * 60)
for distance in test_distances:
    pricing = PricingEngine()
    result = pricing.calculate_trip_price(
        distance_miles=distance,
        customer_email="jacquelyn@example.com"  # Update with real email
    )
    print(f"  Distance: {distance} mi")
    print(f"  Total: ${result['total']}")
    print(f"  Pricing Type: {result.get('pricing_type', 'N/A')}")
    print(f"  Tier: {result.get('customer_tier', 'N/A')}")
    print()

print("\n3. Testing Regular Customer (Standard pricing)")
print("-" * 60)
for distance in test_distances:
    pricing = PricingEngine()
    result = pricing.calculate_trip_price(
        distance_miles=distance,
        customer_email="regular@customer.com"
    )
    print(f"  Distance: {distance} mi")
    print(f"  Total: ${result['total']}")
    print(f"  Pricing Type: {result.get('pricing_type', 'N/A')}")
    print(f"  Tier: {result.get('customer_tier', 'N/A')}")
    print()

print("\n4. List All Grandfathered Customers")
print("-" * 60)
customers = CustomerPricingProfile.list_grandfathered_customers()
for email, profile in customers.items():
    print(f"\nEmail: {email}")
    print(f"  Name: {profile['name']}")
    print(f"  Tier: {profile['pricing_tier']}")
    if 'expires' in profile:
        print(f"  Expires: {profile['expires']}")
        print(f"  Is Expired: {profile.get('is_expired', False)}")
    print(f"  Notes: {profile.get('notes', 'N/A')}")

print("\n" + "=" * 60)
print("TEST COMPLETE")
print("=" * 60)
print("\nNOTE: Update email addresses in customer_pricing.py")
print("Current emails are placeholders:")
print("  - esmeralda@example.com")
print("  - jacquelyn@example.com")
print("=" * 60)
