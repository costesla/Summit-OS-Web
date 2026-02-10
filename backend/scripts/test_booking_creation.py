import os
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables
script_dir = os.path.dirname(__file__)
load_dotenv(os.path.join(script_dir, '..', '..', '.env'))

# Add backend to path
sys.path.append(os.path.join(script_dir, '..'))

from services.bookings import BookingsClient

def test_create_booking():
    """Test creating a booking appointment via Microsoft Bookings API"""
    print("Testing Microsoft Bookings API Integration...")
    print("-" * 50)
    
    try:
        # Initialize client
        client = BookingsClient()
        service_id = os.environ.get('MS_BOOKINGS_SERVICE_ID', 'dc16877c-160d-436e-b53b-52ae6f419604')
        
        # Test booking data
        customer_data = {
            'name': 'Test Customer',
            'email': 'peter.teehan@costesla.com',  # Using your email for testing
            'phone': '555-0123',
            'pickup': 'Denver International Airport',
            'dropoff': 'Downtown Denver'
        }
        
        # Schedule for tomorrow at 2 PM
        start_dt = datetime.now() + timedelta(days=1)
        start_dt = start_dt.replace(hour=14, minute=0, second=0, microsecond=0)
        end_dt = start_dt + timedelta(hours=1, minutes=30)  # 1.5 hour appointment
        
        print(f"Creating test booking:")
        print(f"  Customer: {customer_data['name']}")
        print(f"  Email: {customer_data['email']}")
        print(f"  Phone: {customer_data['phone']}")
        print(f"  Pickup: {customer_data['pickup']}")
        print(f"  Dropoff: {customer_data['dropoff']}")
        print(f"  Start: {start_dt}")
        print(f"  End: {end_dt}")
        print(f"  Service ID: {service_id}")
        print()
        
        # Create the appointment
        result = client.create_appointment(
            customer_data=customer_data,
            start_dt=start_dt,
            end_dt=end_dt,
            service_id=service_id
        )
        
        print("SUCCESS! Booking created:")
        print(f"  Appointment ID: {result.get('id')}")
        print(f"  Self Link: {result.get('selfLink', 'N/A')}")
        print()
        print("Please check your Microsoft Bookings page to verify the appointment appears.")
        
    except Exception as e:
        print(f"ERROR: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_create_booking()
