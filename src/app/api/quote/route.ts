import { NextResponse } from 'next/server';
import { calculateTripPrice, TripParams } from '@/utils/pricing';
import { Client, UnitSystem } from "@googlemaps/google-maps-services-js";

// Initialize Google Maps Client
const client = new Client({});
const GOOGLE_MAPS_API_KEY = process.env.Maps_SERVER_KEY || process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY;

// Admin Hub (The "Base")
const ADMIN_BASE_LOCATION = "North Carefree Circle, Colorado Springs, CO";

export async function POST(request: Request) {
  try {
    const {
      tripType,
      pickup,
      dropoff,
      stops,
      returnStops,
      layoverHours,
      simpleWaitTime
    } = await request.json();

    if (!GOOGLE_MAPS_API_KEY) {
      return NextResponse.json({ success: false, error: "Missing Google Maps API Key" }, { status: 500 });
    }

    // --- ADDRESS VALIDATION LOGIC ---
    // (Simplified: We trust the frontend Autocomplete + Distance Matrix will catch invalid addrs)
    const validate = async (addr: string) => {
      if (!addr || addr.trim() === "") return "";

      // If it has commas, it's likely from Autocomplete -> Trust it
      if (addr.includes(",")) return addr;

      // Fallback for manual entry: Auto-Context
      const lower = addr.toLowerCase();
      if (!lower.includes(" co") && !lower.includes("colorado")) {
        if (/^\d+/.test(addr) && !lower.includes("springs")) {
          return `${addr}, Colorado Springs, CO`;
        }
        return `${addr}, CO`;
      }
      return addr;
    };

    // Parallel Validation (Local String processing only)
    const validPickup = await validate(pickup);
    const validDropoff = await validate(dropoff);

    const validStops = await Promise.all((stops || []).map((s: string) => validate(s)));

    // --- REAL DISTANCE CALCULATION ---

    // 1. Calculate Leg 1 Distance (Pickup -> Dropoff)
    const leg1Res = await client.distancematrix({
      params: {
        origins: [validPickup],
        destinations: [validDropoff],
        key: GOOGLE_MAPS_API_KEY,
        units: UnitSystem.imperial
      }
    });

    if (leg1Res.data.status !== 'OK' || !leg1Res.data.rows[0].elements[0].distance) {
      throw new Error("Failed to calculate route distance");
    }

    const leg1DistanceMeters = leg1Res.data.rows[0].elements[0].distance.value;
    const leg1DistanceMiles = leg1DistanceMeters * 0.000621371;
    const leg1DurationText = leg1Res.data.rows[0].elements[0].duration.text;

    // 2. Calculate Deadhead Distance (Admin Base -> Pickup)
    const deadheadRes = await client.distancematrix({
      params: {
        origins: [ADMIN_BASE_LOCATION],
        destinations: [pickup],
        key: GOOGLE_MAPS_API_KEY,
        units: UnitSystem.imperial // CORRECTED: lowercase 'imperial'
      }
    });

    let deadheadMiles = 0;
    if (deadheadRes.data.status === 'OK' && deadheadRes.data.rows[0].elements[0].distance) {
      deadheadMiles = deadheadRes.data.rows[0].elements[0].distance.value * 0.000621371;
    }

    // 3. Teller County & Airport Detection
    const combinedText = (pickup + dropoff).toLowerCase();
    const isTellerCounty = combinedText.match(/woodland|divide|floroyant|cripple creek|teller/i) !== null;
    const isAirport = combinedText.includes("airport") || combinedText.includes("cos");

    // 4. Calculate Total Distance & Stops
    let totalDistance = leg1DistanceMiles;
    let totalStops = parseInt(stops) || 0;

    // Add Leg 2 if Round Trip
    if (tripType === 'round-trip') {
      totalDistance += leg1DistanceMiles; // Approximate return

      const returnStopCount = parseInt(returnStops) || 0;
      totalStops += returnStopCount;
      totalDistance += (totalStops * 3);
    } else {
      totalDistance += (totalStops * 3);
    }

    // 5. Determine Wait Time
    const finalWaitTime = tripType === 'round-trip' ? (parseFloat(layoverHours) || 0) : (simpleWaitTime ? 1 : 0);

    const priceParams: TripParams = {
      distanceMiles: totalDistance,
      deadheadMiles,
      stops: totalStops,
      isTellerCounty,
      isAirport, // Pass the flag
      waitTimeHours: finalWaitTime
    };

    const quote = calculateTripPrice(priceParams);

    // Attach validated address info for Frontend Map
    quote.debug = {
      origin: validPickup,
      destination: validDropoff,
      leg1Miles: leg1DistanceMiles.toFixed(1),
      deadheadMiles: deadheadMiles.toFixed(1),
      duration: leg1DurationText,
      isTellerCounty,
      validated: true
    };

    // Populate distance and time for email
    quote.distance = totalDistance;
    quote.time = parseInt(leg1DurationText) || 0; // Extract minutes from duration text

    return NextResponse.json({
      success: true,
      quote
    });

  } catch (error: any) {
    console.error("Pricing Error:", error);
    // Return the ACTUAL error message for debugging
    return NextResponse.json({
      success: false,
      error: error.message || "Unknown Error",
      details: JSON.stringify(error)
    }, { status: 500 });
  }
}
