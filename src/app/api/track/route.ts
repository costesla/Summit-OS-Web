import { NextResponse } from 'next/server';
import { calculateDistance } from '@/utils/distance';

export async function GET() {
    // Hardcoded for stability in V1
    const TESSIE_KEY = "0mBOWenSqEI1Fv7xCmSTnKpToUQ7Xr65";
    const VIN = "7SAYGDEEXRF075302"; // Thor
    const HOME_LAT = 38.886637;
    const HOME_LONG = -104.804107;

    if (!TESSIE_KEY) {
        return NextResponse.json({ error: "Missing API Key" }, { status: 500 });
    }

    try {
        const response = await fetch(`https://api.tessie.com/${VIN}/state`, {
            headers: {
                "Authorization": `Bearer ${TESSIE_KEY}`,
                "Accept": "application/json"
            },
            next: { revalidate: 15 } // Cache for 15s
        });

        if (!response.ok) {
            console.error("Tessie Error", response.status, response.statusText);
            throw new Error(`Tessie API error: ${response.status}`);
        }

        const data = await response.json();

        // Handle "Asleep" state where drive_state might be missing
        if (!data.drive_state) {
            // Return Privacy Mode if asleep (safest bet) or last known? 
            // Let's assume if sleeping, it's parked -> Privacy Mode.
            return NextResponse.json({
                privacy: true,
                status: "Vehicle is engaging Start-up Systems..." // Specialized message
            });
        }

        const driveState = data.drive_state;

        // --- Geofence Logic ---
        const dist = calculateDistance(HOME_LAT, HOME_LONG, driveState.latitude, driveState.longitude);

        // If within 0.25 miles of home, MASK DATA
        if (dist < 0.25) {
            return NextResponse.json({
                privacy: true,
                status: "Vehicle is currently docked."
            });
        }
        // ----------------------

        return NextResponse.json({
            lat: driveState.latitude,
            long: driveState.longitude,
            speed: driveState.speed || 0,
            heading: driveState.heading,
            ignition: driveState.shift_state !== null,
            updatedAt: new Date().toISOString()
        });

    } catch (error) {
        console.error("Tracking Error:", error);
        return NextResponse.json({ error: "Failed to fetch vehicle location" }, { status: 500 });
    }
}
