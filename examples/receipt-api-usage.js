/**
 * Example: Using the Receipt API Endpoint
 */

// Example 1: Using fetch
async function sendReceiptViaAPI() {
    const tripData = {
        TripData: {
            Id: "PT-20260120-123456",
            DateLocal: "Mon, Jan 20, 2026",
            StartTimeLocal: "10:30 AM",
            EndTimeLocal: "10:55 AM",
            PickupArea: "Downtown Colorado Springs",
            DropoffArea: "Airport",
            PickupAddress: "123 Main St, Colorado Springs, CO 80903",
            DropoffAddress: "7770 Milton E Proby Pkwy, Colorado Springs, CO 80916",
            Distance: { mi: 12.5 },
            Duration: { min: 25 }
        },
        FareData: {
            Base: "25.00",
            TimeDistance: "8.75",
            Extras: "0.00",
            Discount: "0.00",
            Subtotal: "33.75",
            Tax: "2.70",
            Tip: "7.00",
            Total: "43.45"
        },
        PaymentData: {
            Method: "Venmo",
            Last4: "5678",
            AuthCode: "PRVT-OK-1A23"
        },
        PassengerData: {
            firstName: "Jordan",
            email: "customer@example.com"
        },
        GeoData: {
            city: "Colorado Springs",
            region: "CO",
            lat: 38.8339,
            lng: -104.8214
        }
    };

    const response = await fetch('/api/receipt-graph', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(tripData)
    });

    const result = await response.json();

    if (result.success) {
        console.log('Receipt sent successfully!');
        console.log('Send status:', result.send);
    } else {
        console.error('Error:', result.error);
    }
}

// Example 2: Using from booking completion
async function onBookingComplete(bookingData) {
    // Transform booking data to receipt format
    const receiptInput = {
        TripData: {
            Id: bookingData.confirmationCode,
            DateLocal: bookingData.date,
            StartTimeLocal: bookingData.pickupTime,
            EndTimeLocal: bookingData.estimatedDropoffTime,
            PickupArea: bookingData.pickupArea,
            DropoffArea: bookingData.dropoffArea,
            PickupAddress: bookingData.pickup,
            DropoffAddress: bookingData.dropoff,
            Distance: { mi: bookingData.distance },
            Duration: { min: bookingData.duration }
        },
        FareData: {
            Base: bookingData.basePrice,
            TimeDistance: bookingData.distancePrice,
            Extras: "0.00",
            Discount: "0.00",
            Subtotal: bookingData.subtotal,
            Tax: bookingData.tax,
            Tip: bookingData.tip || "0.00",
            Total: bookingData.total
        },
        PaymentData: {
            Method: bookingData.paymentMethod,
            Last4: bookingData.last4,
            AuthCode: bookingData.authCode
        },
        PassengerData: {
            firstName: bookingData.firstName,
            email: bookingData.email
        },
        GeoData: {
            city: bookingData.city,
            region: bookingData.state,
            lat: bookingData.pickupLat,
            lng: bookingData.pickupLng
        }
    };

    // Send receipt
    const response = await fetch('/api/receipt-graph', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(receiptInput)
    });

    return await response.json();
}

// Example 3: cURL command for testing
/*
curl -X POST http://localhost:3000/api/receipt-graph \
  -H "Content-Type: application/json" \
  -d @sample-trip.json
*/
