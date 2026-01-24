/**
 * Example: Using the Receipt Handler Directly
 */

import handler from './src/lib/receipt-combined-handler';

const exampleTrip = {
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
        Duration: { min: 25 },
        Pickup: { PlaceId: "" },
        Dropoff: { PlaceId: "" }
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
        country: "US",
        lat: 38.8339,
        lng: -104.8214
    }
};

async function sendReceipt() {
    const result = await handler(exampleTrip);

    if ('error' in result) {
        console.error('Error:', result.error);
    } else {
        console.log('Receipt sent!', result.send);
    }
}

sendReceipt();
