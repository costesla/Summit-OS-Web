import csv
import random
import uuid
from datetime import datetime, timedelta
import os
import sys

# Add backend to path to use PricingEngine
sys.path.append(os.path.join(os.getcwd(), 'backend'))
try:
    from services.pricing import PricingEngine
except ImportError:
    # Fallback if running from a different directory
    sys.path.append(os.path.join(os.getcwd(), '..'))
    from services.pricing import PricingEngine

# Mock Data Configuration
OUTPUT_FILE = "mock_data_trips.csv"
START_DATE = datetime.now() - timedelta(days=90) # Last 3 months
END_DATE = datetime.now() + timedelta(days=30)   # Next 30 days
TOTAL_TRIPS = 600

LOCATIONS = [
    ("The Broadmoor", "1 Lake Ave, Colorado Springs, CO"),
    ("Denver International Airport", "8500 Peña Blvd, Denver, CO"),
    ("Colorado Springs Airport", "7770 Milton E Proby Pkwy, Colorado Springs, CO"),
    ("Garden of the Gods", "1805 N 30th St, Colorado Springs, CO"),
    ("US Air Force Academy", "Air Force Academy, CO"),
    ("Downtown COS", "Tejon St, Colorado Springs, CO"),
    ("Manitou Springs", "Manitou Ave, Manitou Springs, CO"),
    ("Castle Rock", "Castle Rock, CO")
]

DRIVERS = ["Peter Teehan", "John Doe", "Jane Smith", "Auto-Dispatch"]
STATUSES = ["Completed", "Completed", "Completed", "Cancelled", "No Show"] # Weighted towards Completed
FUTURE_STATUSES = ["Scheduled", "Scheduled", "Pending"]

pricing_engine = PricingEngine()

def random_date(start, end):
    """Generate a random datetime between `start` and `end`"""
    return start + timedelta(
        seconds=random.randint(0, int((end - start).total_seconds())),
    )

def generate_trip():
    pickup = random.choice(LOCATIONS)
    dropoff = random.choice([l for l in LOCATIONS if l != pickup])
    
    # Simple distance estimation (mocking the Google Maps calls to avoid API costs/latency)
    # Broadmoor <-> DIA is ~85 miles
    # COS <-> DIA is ~80 miles
    # Local trips ~5-15 miles
    
    is_long_haul = "Denver" in pickup[0] or "Denver" in dropoff[0] or "Castle Rock" in pickup[0] or "Castle Rock" in dropoff[0]
    
    if is_long_haul:
        distance = random.uniform(60.0, 95.0)
        duration_min = int(distance * 1.1) # Approx minutes
    else:
        distance = random.uniform(3.0, 20.0)
        duration_min = int(distance * 2.5) # Slower city traffic
        
    price_data = pricing_engine.calculate_trip_price(distance_miles=distance)
    fare = price_data['total']
    
    trip_date = random_date(START_DATE, END_DATE)
    is_future = trip_date > datetime.now()
    
    status = random.choice(FUTURE_STATUSES) if is_future else random.choice(STATUSES)
    
    return {
        "TripID": str(uuid.uuid4()),
        "CustomerName": f"Customer {random.randint(100, 999)}",
        "PickupLocation": pickup[0],
        "DropoffLocation": dropoff[0],
        "PickupTime": trip_date.isoformat(),
        "DropoffTime": (trip_date + timedelta(minutes=duration_min)).isoformat(),
        "Status": status,
        "Fare": round(fare, 2),
        "Driver": random.choice(DRIVERS),
        "DistanceMiles": round(distance, 1),
        "DurationMinutes": duration_min
    }

def main():
    print(f"Generating {TOTAL_TRIPS} mock trips...")
    trips = [generate_trip() for _ in range(TOTAL_TRIPS)]
    
    # Sort by date
    trips.sort(key=lambda x: x['PickupTime'])
    
    # Ensure output directory exists
    output_path = os.path.join("summit_sync", "mock_data", OUTPUT_FILE)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    keys = trips[0].keys()
    
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        dict_writer = csv.DictWriter(f, keys)
        dict_writer.writeheader()
        dict_writer.writerows(trips)
        
    print(f"Successfully generated {len(trips)} trips to {output_path}")

if __name__ == "__main__":
    main()
