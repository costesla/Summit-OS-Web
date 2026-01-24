/**
 * Test script for Private Trip Receipt Engine
 * Tests the complete flow: validation, photo fetch, HTML/text generation, and SMTP send
 */

const sampleReceiptInput = {
    "TripData": {
        "Id": "PT-20260120-072315",
        "DateLocal": "Mon, Jan 20, 2026",
        "StartTimeLocal": "7:23 AM",
        "EndTimeLocal": "7:43 AM",
        "PickupArea": "Northgate (near Voyager Pkwy)",
        "DropoffArea": "Banning Lewis Ranch",
        "PickupAddress": "1234 Example St, Colorado Springs, CO 80907",
        "DropoffAddress": "9876 Sample Ave, Colorado Springs, CO 80920",
        "Distance": { "mi": 15.54 },
        "Duration": { "min": 20 },
        "Notes": "Thank you for choosing COS Tesla LLC for your private transportation needs.",
        "Pickup": { "PlaceId": "" },
        "Dropoff": { "PlaceId": "" }
    },
    "FareData": {
        "Base": "20.00",
        "TimeDistance": "5.50",
        "Extras": "0.00",
        "Discount": "2.50",
        "Subtotal": "23.00",
        "Tax": "1.84",
        "Tip": "5.00",
        "Total": "29.84"
    },
    "PaymentData": {
        "Method": "Venmo",
        "Last4": "1234",
        "AuthCode": "PRVT-OK-7A23"
    },
    "PassengerData": {
        "firstName": "Alex",
        "email": "peter.teehan@costesla.com" // Change to your test email
    },
    "GeoData": {
        "city": "Colorado Springs",
        "region": "CO",
        "country": "US",
        "lat": 38.8339,
        "lng": -104.8214
    },
    "Now": { "Year": 2026 }
};

async function testReceiptGeneration() {
    console.log('🚀 Testing Private Trip Receipt Engine...\n');

    try {
        const response = await fetch('http://localhost:3000/api/receipt/generate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(sampleReceiptInput),
        });

        const result = await response.json();

        if (response.ok) {
            console.log('✅ Receipt generated and sent successfully!');
            console.log('📧 Message ID:', result.messageId);
            console.log('📬 Sent to:', result.to);
            console.log('🎫 Trip ID:', result.tripId);
            console.log('🖼️  Has Photo:', result.hasPhoto);
        } else {
            console.error('❌ Error:', result.error);
        }
    } catch (error) {
        console.error('❌ Request failed:', error);
    }
}

testReceiptGeneration();
