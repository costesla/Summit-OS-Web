import { NextResponse } from 'next/server';
import { calculateTripPrice, TripParams } from '@/utils/pricing';
import { Client, UnitSystem } from "@googlemaps/google-maps-services-js";

// Initialize Google Maps Client
const client = new Client({});
const GOOGLE_MAPS_API_KEY = process.env.GOOGLE_MAPS_API_KEY || process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY;

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
    const validate = async (addr: string) => {
      if (!addr || addr.trim() === "") return "";

      // AUTO-CONTEXT: Default to Colorado Springs if no city/state looks present
      // This allows users to type "1194 Magnolia" and get "1194 Magnolia St, Colorado Springs, CO"
      let searchAddr = addr;
      const lower = addr.toLowerCase();

      // If it doesn't have "CO" or "colorado", append context
      if (!lower.includes(" co") && !lower.includes("colorado")) {
        // If it looks like just a street address (starts with number), assume Colorado Springs
        if (/^\d+/.test(addr) && !lower.includes("springs") && !lower.includes("denver") && !lower.includes("pueblo")) {
          searchAddr = `${addr}, Colorado Springs, CO`;
        } else {
          searchAddr = `${addr}, CO`;
        }
      }

      try {
        const response = await fetch(`https://addressvalidation.googleapis.com/v1:validateAddress?key=${GOOGLE_MAPS_API_KEY}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            address: {
              regionCode: 'US',
              addressLines: [searchAddr]
            },
            enableUspsCass: true
          })
        });

        if (!response.ok) {
          console.warn(`Validation API Error: ${response.status} ${response.statusText}`);
          return searchAddr; // Fallback to our enhanced search address
        }

        const data = await response.json();
        return data.result?.address?.formattedAddress || searchAddr;
      } catch (error) {
        console.warn(`Address Validation Failed for '${addr}':`, error);
        return searchAddr; // Fallback to our enhanced search address
      }
    };

    // Parallel Validation
    const [validPickup, validDropoff] = await Promise.all([
      validate(pickup),
      validate(dropoff)
    ]);

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

  } catch (error) {
    console.error("Pricing Error:", error);
    return NextResponse.json({ success: false, error: "Failed to calculate quote. Please verify address." }, { status: 500 });
  }
}
