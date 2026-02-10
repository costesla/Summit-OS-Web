"""
Simple local test to preview the enhanced receipt HTML
This generates a receipt preview without calling any API
"""

from datetime import datetime, timedelta
import os
import webbrowser

# Test data
pickup_datetime = datetime.now() + timedelta(days=1, hours=2)
pickup_time_formatted = pickup_datetime.strftime("%a, %b %d, %Y, %I:%M %p")

test_data = {
    "name": "Peter Teehan",
    "email": "peter.teehan@costesla.com",
    "phone": "(555) 123-4567",
    "pickup": "The Broadmoor, 1 Lake Avenue, Colorado Springs, CO 80906",
    "dropoff": "Denver International Airport, 8500 Pena Blvd, Denver, CO 80249",
    "price": "$125.00",
    "pickupTime": pickup_time_formatted,
    "bookingId": f"TEST-{datetime.now().strftime('%Y%m%d%H%M')}"
}

print("=" * 60)
print("GENERATING ENHANCED RECEIPT PREVIEW")
print("=" * 60)
print(f"\nCustomer: {test_data['name']}")
print(f"Pickup Time: {test_data['pickupTime']}")
print(f"Route: {test_data['pickup']} -> {test_data['dropoff']}")
print(f"Total: {test_data['price']}")
print("\n" + "=" * 60)

# Create the enhanced receipt HTML
html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Enhanced Receipt Preview - SummitOS LLC</title>
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
                            <p style="margin: 0 0 20px; font-size: 16px; color: #333333;">Hello {test_data['name']},</p>
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
                                    <td style="padding: 6px 0; font-size: 14px; color: #333333; text-align: right; font-weight: 600;">#{test_data['bookingId']}</td>
                                </tr>
                                <tr>
                                    <td style="padding: 6px 0; font-size: 14px; color: #666666;">Pickup Time</td>
                                    <td style="padding: 6px 0; font-size: 14px; color: #06b6d4; text-align: right; font-weight: 600; background: #f0f9ff; border-radius: 4px; padding-left: 8px; padding-right: 8px;">{test_data['pickupTime']}</td>
                                </tr>
                                <tr>
                                    <td colspan="2" style="padding: 15px 0 6px; font-size: 14px; color: #666666;">Pickup Location</td>
                                </tr>
                                <tr>
                                    <td colspan="2" style="padding: 0 0 6px; font-size: 14px; color: #333333; font-weight: 600;">{test_data['pickup']}</td>
                                </tr>
                                <tr>
                                    <td colspan="2" style="padding: 15px 0 6px; font-size: 14px; color: #666666;">Dropoff Location</td>
                                </tr>
                                <tr>
                                    <td colspan="2" style="padding: 0 0 6px; font-size: 14px; color: #333333; font-weight: 600;">{test_data['dropoff']}</td>
                                </tr>
                                <tr>
                                    <td style="padding: 20px 0 0; font-size: 18px; font-weight: bold; color: #000000; border-top: 2px solid #000000;">Total</td>
                                    <td style="padding: 20px 0 0; font-size: 18px; font-weight: bold; color: #000000; text-align: right; border-top: 2px solid #000000;">{test_data['price']}</td>
                                </tr>
                            </table>
                            
                            <!-- Payment Options -->
                            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin: 0 0 25px; border-bottom: 1px solid #eeeeee; padding-bottom: 20px;">
                                <tr>
                                    <td style="padding: 0 0 15px; font-size: 18px; font-weight: bold; color: #000000;">Payment Options</td>
                                </tr>
                                <tr>
                                    <td style="padding: 10px 0; font-size: 14px; color: #666666; line-height: 1.6;">
                                        <p style="margin: 0 0 10px; font-weight: 600; color: #333333;">💳 Venmo</p>
                                        <p style="margin: 0 0 15px; padding-left: 20px;">
                                            Send payment to: <a href="https://www.venmo.com/u/costesla" style="color: #008CFF; text-decoration: none; font-weight: 600;">@costesla</a>
                                        </p>
                                        
                                        <p style="margin: 0 0 10px; font-weight: 600; color: #333333;">💜 Zelle</p>
                                        <p style="margin: 0 0 15px; padding-left: 20px;">
                                            Send to: <strong>peter.teehan@costesla.com</strong><br>
                                            <span style="font-size: 12px; color: #888;">Recipient: COS TESLA LLC</span>
                                        </p>
                                        
                                        <p style="margin: 0 0 10px; font-weight: 600; color: #333333;">💵 Cash</p>
                                        <p style="margin: 0; padding-left: 20px;">
                                            Pay your driver directly at pickup or dropoff
                                        </p>
                                    </td>
                                </tr>
                            </table>
                            
                            <!-- Next Steps -->
                            <div style="background: #f0f9ff; padding: 15px; border-radius: 8px; border-left: 4px solid #06b6d4;">
                                <p style="margin: 0 0 10px; font-size: 14px; font-weight: bold; color: #0e7490;">📅 Next Steps</p>
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
script_dir = os.path.dirname(os.path.abspath(__file__))
output_dir = os.path.join(script_dir, "..", "..", "test-outputs")
os.makedirs(output_dir, exist_ok=True)

output_file = os.path.join(output_dir, f"receipt_preview_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html")

with open(output_file, 'w', encoding='utf-8') as f:
    f.write(html_content)

print(f"\nSUCCESS: Receipt preview saved to:")
print(f"  {output_file}")
print("\nOpening in browser...")

# Open in browser
webbrowser.open(f'file://{os.path.abspath(output_file)}')

print("\n" + "=" * 60)
print("PREVIEW COMPLETE")
print("=" * 60)
print("\nWhat you're seeing:")
print("  - Pickup Time field (highlighted in blue)")
print("  - Payment Options section with Venmo, Zelle, and Cash")
print("  - Professional email-compatible layout")
print("\nNext steps:")
print("  1. Review the receipt in your browser")
print("  2. Deploy backend changes to Azure")
print("  3. Test with a real booking")
print("=" * 60)
