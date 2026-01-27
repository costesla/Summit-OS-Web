
import { NextResponse } from 'next/server';

export const runtime = 'edge'; // Use Edge for speed

export async function GET() {
    try {
        const apiKey = process.env.TESSIE_API_KEY;
        const vin = process.env.TESSIE_VIN;

        if (!apiKey || !vin) {
            console.error("Missing Tessie credentials");
            return NextResponse.json({ error: "Configuration Error" }, { status: 500 });
        }

        // 1. Fetch State from Tessie
        const response = await fetch(`https://api.tessie.com/${vin}/state`, {
            headers: {
                "Authorization": `Bearer ${apiKey}`
            }
        });

        if (!response.ok) {
            console.error("Tessie API Error:", response.status, await response.text());
            return NextResponse.json({ error: "Vehicle Unreachable" }, { status: 502 });
        }

        const data = await response.json();
        const driveState = data.drive_state;

        if (!driveState) {
            // Car likely asleep -> Assume parked at home for safety
            return NextResponse.json({
                privacy: true,
                status: "Vehicle is engaging Start-up Systems..."
            });
        }

        // 2. Privacy Geofence Logic
        const HOME_LAT = 38.886637;
        const HOME_LONG = -104.804107;
        const currentLat = driveState.latitude;
        const currentLong = driveState.longitude;

        // Haversine Distance in Miles
        const R = 3959.87433; // Earth radius in miles
        const dLat = (currentLat - HOME_LAT) * Math.PI / 180;
        const dLon = (currentLong - HOME_LONG) * Math.PI / 180;
        const a =
            Math.sin(dLat / 2) * Math.sin(dLat / 2) +
            Math.cos(HOME_LAT * Math.PI / 180) * Math.cos(currentLat * Math.PI / 180) *
            Math.sin(dLon / 2) * Math.sin(dLon / 2);
        const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
        const distanceMiles = R * c;

        // 0.25 mile radius
        if (distanceMiles < 0.25) {
            return NextResponse.json({
                privacy: true,
                status: "Vehicle is currently docked."
            });
        }

        // 3. Return Public Data
        return NextResponse.json({
            lat: currentLat,
            long: currentLong,
            speed: driveState.speed || 0,
            heading: driveState.heading,
            updatedAt: new Date().toISOString()
        });

    } catch (error) {
        console.error("Tracker Error:", error);
        return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
    }
}
