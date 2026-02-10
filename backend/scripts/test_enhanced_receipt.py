"""
Test script for the enhanced receipt engine with pickup time and payment options
This script will:
1. Send a test booking request to the local/production API
2. Save the receipt HTML to a file for preview
3. Optionally open it in your browser
"""

import requests
import json
from datetime import datetime, timedelta
import os
import webbrowser

# Configuration
USE_LOCAL = False  # Set to False to test against production
LOCAL_URL = "http://localhost:7071/api/book"
PROD_URL = "https://www.costesla.com/api/book"

URL = LOCAL_URL if USE_LOCAL else PROD_URL

# Create test payload with the new pickup time field
pickup_datetime = datetime.now() + timedelta(days=1, hours=2)  # Tomorrow at 2 hours from now
pickup_time_formatted = pickup_datetime.strftime("%a, %b %d, %Y, %I:%M %p")

payload = {
    "name": "Peter Teehan",
    "email": "peter.teehan@costesla.com",
    "phone": "(555) 123-4567",
    "pickup": "The Broadmoor, 1 Lake Avenue, Colorado Springs, CO 80906",
    "dropoff": "Denver International Airport, 8500 Pena Blvd, Denver, CO 80249",
    "price": "$125.00",
    "pickupTime": pickup_time_formatted,  # NEW FIELD!
    "passengers": "2",
    "tripDetails": {
        "dist": "75.3",
        "time": "90"
    }
}

print("=" * 60)
print("TESTING ENHANCED RECEIPT ENGINE")
print("=" * 60)
print(f"\nTarget URL: {URL}")
print(f"Pickup Time: {pickup_time_formatted}")
print(f"\nPayload:")
print(json.dumps(payload, indent=2))
print("\n" + "=" * 60)

try:
    print("\nSending request...")
    response = requests.post(URL, json=payload, timeout=20)
    
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        print("SUCCESS: Receipt generated!")
        
        try:
            response_data = response.json()
            print(f"\nResponse: {json.dumps(response_data, indent=2)}")
        except:
            print(f"\nResponse: {response.text[:200]}...")
        
        # If we can extract HTML from response, save it
        # Note: The actual receipt is sent via email, but we can create a mock preview
        print("\nCreating local receipt preview...")
        
        # Create a mock HTML receipt for preview
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Receipt Preview - Enhanced</title>
</head>
<body style="margin: 0; padding: 0; font-family: Arial, Helvetica, sans-serif; background: #f4f4f4;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color: #f4f4f4;">
        <tr>
            <td align="center" style="padding: 20px 10px;">
                <table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" style="max-width: 600px; width: 100%; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                    
                    <!-- Header -->
                    <tr>
                        <td style="background-color: #000000; color: #ffffff; padding: 30px 20px; text-align: center;">
                            <h1 style="margin: 0; font-size: 24px; font-weight: bold;">SummitOS LLC</h1>
                            <p style="margin: 5px 0 0; color: #aaaaaa; font-size: 14px; text-transform: uppercase; letter-spacing: 1px;">Trip Confirmation</p>
                        </td>
                    </tr>
                    
                    <!-- Content -->
                    <tr>
                        <td style="padding: 30px 20px;">
                            <p style="margin: 0 0 20px; font-size: 16px; color: #333333;">Hello {payload['name']},</p>
                            <p style="margin: 0 0 25px; font-size: 14px; color: #666666; line-height: 1.5;">
                                Thank you for choosing SummitOS. Your booking has been confirmed. Please review the details below:
                            </p>
                            
                            <!-- Trip Details -->
                            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin: 0 0 25px; border-bottom: 1px solid #eeeeee; padding-bottom: 20px;">
                                <tr>
                                    <td colspan="2" style="padding: 0 0 15px; font-size: 18px; font-weight: bold; color: #000000;">Trip Details</td>
                                </tr>
                                <tr>
                                    <td style="padding: 6px 0; font-size: 14px; color: #666666;">Booking ID</td>
                                    <td style="padding: 6px 0; font-size: 14px; color: #333333; text-align: right; font-weight: 600;">#TEST-{datetime.now().strftime('%Y%m%d%H%M')}</td>
                                </tr>
                                <tr>
                                    <td style="padding: 6px 0; font-size: 14px; color: #666666;">Pickup Time</td>
                                    <td style="padding: 6px 0; font-size: 14px; color: #06b6d4; text-align: right; font-weight: 600; background: #f0f9ff; border-radius: 4px; padding-left: 8px; padding-right: 8px;">{pickup_time_formatted}</td>
                                </tr>
                                <tr>
                                    <td colspan="2" style="padding: 15px 0 6px; font-size: 14px; color: #666666;">Pickup Location</td>
                                </tr>
                                <tr>
                                    <td colspan="2" style="padding: 0 0 6px; font-size: 14px; color: #333333; font-weight: 600;">{payload['pickup']}</td>
                                </tr>
                                <tr>
                                    <td colspan="2" style="padding: 15px 0 6px; font-size: 14px; color: #666666;">Dropoff Location</td>
                                </tr>
                                <tr>
                                    <td colspan="2" style="padding: 0 0 6px; font-size: 14px; color: #333333; font-weight: 600;">{payload['dropoff']}</td>
                                </tr>
                                <tr>
                                    <td style="padding: 20px 0 0; font-size: 18px; font-weight: bold; color: #000000; border-top: 2px solid #000000;">Total</td>
                                    <td style="padding: 20px 0 0; font-size: 18px; font-weight: bold; color: #000000; text-align: right; border-top: 2px solid #000000;">{payload['price']}</td>
                                </tr>
                            </table>
                            
                            <!-- Payment Options -->
                            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin: 0 0 25px; border-bottom: 1px solid #eeeeee; padding-bottom: 20px;">
                                <tr>
                                    <td style="padding: 0 0 15px; font-size: 18px; font-weight: bold; color: #000000;">Payment Options</td>
                                </tr>
                                <tr>
                                    <td style="padding: 10px 0; font-size: 14px; color: #666666; line-height: 1.6;">
                                        <p style="margin: 0 0 10px; font-weight: 600; color: #333333;">Venmo</p>
                                        <p style="margin: 0 0 15px; padding-left: 20px;">
                                            Send payment to: <a href="https://www.venmo.com/u/costesla" style="color: #008CFF; text-decoration: none; font-weight: 600;">@costesla</a>
                                        </p>
                                        
                                        <p style="margin: 0 0 10px; font-weight: 600; color: #333333;">Zelle</p>
                                        <p style="margin: 0 0 15px; padding-left: 20px;">
                                            Send to: <strong>peter.teehan@costesla.com</strong><br>
                                            <span style="font-size: 12px; color: #888;">Recipient: COS TESLA LLC</span>
                                        </p>
                                        
                                        <p style="margin: 0 0 10px; font-weight: 600; color: #333333;">Cash</p>
                                        <p style="margin: 0; padding-left: 20px;">
                                            Pay your driver directly at pickup or dropoff
                                        </p>
                                    </td>
                                </tr>
                            </table>
                            
                            <!-- Next Steps -->
                            <div style="background: #f0f9ff; padding: 15px; border-radius: 8px; border-left: 4px solid #06b6d4;">
                                <p style="margin: 0 0 10px; font-size: 14px; font-weight: bold; color: #0e7490;">Next Steps</p>
                                <p style="margin: 0; font-size: 13px; color: #164e63; line-height: 1.5;">
                                    Please select your preferred time slot by visiting our booking calendar. 
                                    You will receive a confirmation email once your time is confirmed.
                                </p>
                            </div>
                            
                        </td>
                    </tr>
                    
                    <!-- Footer -->
                    <tr>
                        <td style="background-color: #f5f5f5; padding: 25px 20px; text-align: center;">
                            <p style="margin: 0 0 5px; font-size: 14px; font-weight: bold; color: #333333;">SummitOS LLC</p>
                            <p style="margin: 0 0 15px; font-size: 12px; color: #888888;">
                                Support: <a href="mailto:peter.teehan@costesla.com" style="color: #06b6d4; text-decoration: none;">peter.teehan@costesla.com</a>
                            </p>
                            <p style="margin: 0; font-size: 11px; color: #999999; line-height: 1.5;">
                                Driven by Precision | COS Tesla LLC
                            </p>
                        </td>
                    </tr>
                    
                </table>
            </td>
        </tr>
    </table>
</body>
</html>"""
        
        # Save to file
        output_dir = os.path.join(os.path.dirname(__file__), "..", "..", "test-outputs")
        os.makedirs(output_dir, exist_ok=True)
        
        output_file = os.path.join(output_dir, f"receipt_preview_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html")
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"SUCCESS: Receipt preview saved to: {output_file}")
        
        # Ask if user wants to open it
        print("\nOpening receipt in browser...")
        webbrowser.open(f'file://{os.path.abspath(output_file)}')
        
    else:
        print(f"FAILED: {response.status_code}")
        print(f"Response: {response.text}")

except requests.exceptions.ConnectionError:
    print("\nCONNECTION ERROR!")
    if USE_LOCAL:
        print("\nMake sure the Azure Functions backend is running locally:")
        print("   cd backend")
        print("   func start")
    else:
        print("\nCheck your internet connection and the production URL")
        
except Exception as e:
    print(f"\nERROR: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("Test Complete")
print("=" * 60)
