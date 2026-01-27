import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

export async function GET() {
    process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0'; // Handle self-signed certs if needed locally

    try {
        const TESSIE_KEY = process.env.TESSIE_API_KEY;
        if (!TESSIE_KEY) {
            return NextResponse.json({ error: "Missing API Key" }, { status: 500 });
        }

        // 1. Get VIN (First Car)
        const vehiclesRes = await fetch('https://api.tessie.com/vehicles', {
            headers: { 'Authorization': `Bearer ${TESSIE_KEY}` }
        });

        if (!vehiclesRes.ok) throw new Error("Failed to fetch vehicles");

        const vehiclesData = await vehiclesRes.json();
        const car = vehiclesData.results?.[0]; // First car

        if (!car) {
            return NextResponse.json({ error: "No car found" }, { status: 404 });
        }

        // 2. Get State (Use Cache to be nice to battery)
        // ?use_cache=true is CRITICAL to avoid waking the car
        const stateRes = await fetch(`https://api.tessie.com/${car.vin}/state?use_cache=true`, {
            headers: { 'Authorization': `Bearer ${TESSIE_KEY}` }
        });

        const stateData = await stateRes.json();

        if (!stateRes.ok) {
            // Graceful fallback for Sleeping car (Tessie returns 400ish for "not active")
            if (stateData.error === "Vehicle is not active" || stateData.status === "asleep") {
                return NextResponse.json({
                    vin: car.vin,
                    name: car.display_name || "Tesla",
                    battery_level: null,
                    battery_range: null,
                    is_charging: false,
                    status: "Sleeping",
                    timestamp: new Date().toISOString()
                });
            }
            throw new Error(`Failed to fetch state: ${stateRes.status} - ${JSON.stringify(stateData)}`);
        }

        // Success Case (200 OK)
        const battery = stateData.charge_state;
        const isAsleep = stateData.status === 'asleep';

        // 3. Return Simplified JSON
        return NextResponse.json({
            vin: car.vin,
            name: car.display_name || "Tesla",
            battery_level: battery?.battery_level || null,
            battery_range: battery?.battery_range || null,
            is_charging: battery?.charging_state === 'Charging',
            status: isAsleep ? "Sleeping" : (battery ? "Active" : "Unknown"),
            timestamp: new Date().toISOString()
        });

    } catch (error: any) {
        console.error("Tessie API Error:", error);
        return NextResponse.json({ error: error.message || "Unknown Error" }, { status: 500 });
    }
}
