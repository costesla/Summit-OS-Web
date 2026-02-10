
import sys
import os
import json

# Add backend to path
backend_path = os.path.join(os.getcwd(), 'backend')
if backend_path not in sys.path:
    sys.path.append(backend_path)

try:
    from services.pricing import PricingEngine
    from services.customer_pricing import CustomerPricingProfile
    
    print("--- Standard Pricing Test ---")
    pe = PricingEngine()
    # 10 mile trip
    quote = pe.calculate_trip_price(distance_miles=10.0)
    print(f"10 miles (Standard): ${quote['total']} (Base: {quote['baseFare']}, Overage: {quote['overage']})")
    
    # 30 mile trip
    quote = pe.calculate_trip_price(distance_miles=30.0)
    print(f"30 miles (Standard): ${quote['total']} (Base: {quote['baseFare']}, Overage: {quote['overage']})")
    
    print("\n--- Grandfathered Pricing Test ---")
    email = "esmii.lopez@hotmail.com"
    quote = pe.calculate_trip_price(distance_miles=10.0, customer_email=email)
    print(f"10 miles (Esmeralda): ${quote['total']} (Type: {quote['pricing_type']})")
    
    email = "unknown@random.com"
    quote = pe.calculate_trip_price(distance_miles=10.0, customer_email=email)
    print(f"10 miles (Unknown): ${quote['total']} (Type: {quote['pricing_type']})")
    
    print("\n--- Error Case: Small Distance ---")
    quote = pe.calculate_trip_price(distance_miles=1.0)
    print(f"1 mile (Standard): ${quote['total']} (Base: {quote['baseFare']}, Overage: {quote['overage']})")

except Exception as e:
    print(f"ERROR during test: {e}")
    import traceback
    traceback.print_exc()
