import { NextResponse } from 'next/server';
import { calculateTripPrice, TripParams } from '@/utils/pricing';
import { Client, UnitSystem } from "@googlemaps/google-maps-services-js";

// Initialize Google Maps Client
const client = new Client({});

// Admin Hub (The "Base")
const ADMIN_BASE_LOCATION = "North Carefree Circle, Colorado Springs, CO";

export const dynamic = 'force-dynamic';

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

    // Key Attempt Logic
    const PRIMARY_KEY = process.env.GOOGLE_MAPS_API_KEY;
    const FALLBACK_KEY = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY;

    // Helper to run Matrix Call with specific Key
    const runMatrix = async (origins: string[], destinations: string[], useKey: string | undefined, debugName: string) => {
      if (!useKey) throw new Error(`${debugName} Key Missing`);
      return await client.distancematrix({
        params: {
          origins,
          destinations,
          key: useKey,
          units: UnitSystem.imperial
        }
      });
    };

    // --- ADDRESS VALIDATION LOGIC (Local) ---
    const validate = async (addr: string) => {
      if (!addr || addr.trim() === "") return "";
      if (addr.includes(",")) return addr;
      const lower = addr.toLowerCase();
      if (!lower.includes(" co") && !lower.includes("colorado")) {
        if (/^\d+/.test(addr) && !lower.includes("springs")) {
          return `${addr}, Colorado Springs, CO`;
        }
        return `${addr}, CO`;
      }
      return addr;
    };

    const validPickup = await validate(pickup);
    const validDropoff = await validate(dropoff);
    const validStops = await Promise.all((stops || []).map((s: string) => validate(s)));

    // --- DISTANCE MATRIX CALLS (SMART RETRY) ---
    let leg1Res;
    let effectiveKey = "NONE";
    let keySource = "NONE";

    try {
      // Attempt 1: Primary Key
      if (!PRIMARY_KEY) throw new Error("Primary Key Config Missing");
      leg1Res = await runMatrix([validPickup], [validDropoff], PRIMARY_KEY, "Primary");
      effectiveKey = PRIMARY_KEY;
      keySource = "SERVER_PRIMARY";
    } catch (primaryError: any) {
      console.warn(`Primary Key Failed (${primaryError.message}). Attempting Fallback...`);
      // Attempt 2: Fallback Key (Client Key)
      if (!FALLBACK_KEY) throw new Error(`Primary Failed: ${primaryError.message} | Fallback Missing`);
      try {
        leg1Res = await runMatrix([validPickup], [validDropoff], FALLBACK_KEY, "Fallback");
        effectiveKey = FALLBACK_KEY;
        keySource = "FALLBACK_CLIENT";
      } catch (fallbackError: any) {
        const fbMsg = fallbackError?.response?.data?.error_message || fallbackError.message;
        const pMsg = primaryError?.response?.data?.error_message || primaryError.message;
        throw new Error(`All Keys Failed. Primary: ${pMsg} | Fallback: ${fbMsg}`);
      }
    }

    if (!leg1Res || leg1Res.data.status !== 'OK' || !leg1Res.data.rows[0].elements[0].distance) {
      console.error("Distance Matrix Invalid Response:", JSON.stringify(leg1Res?.data));
      throw new Error(`Route Invalid: ${leg1Res?.data?.status ?? 'UNKNOWN'}`);
    }

    const leg1DistanceMeters = leg1Res.data.rows[0].elements[0].distance.value;
    const leg1DistanceMiles = leg1DistanceMeters * 0.000621371;
    const leg1DurationText = leg1Res.data.rows[0].elements[0].duration.text;

    // Deadhead (Uses same effective key)
    let deadheadMiles = 0;
    try {
      const deadheadRes = await runMatrix([ADMIN_BASE_LOCATION], [pickup], effectiveKey, "Deadhead");
      if (deadheadRes.data.status === 'OK' && deadheadRes.data.rows[0].elements[0].distance) {
        deadheadMiles = deadheadRes.data.rows[0].elements[0].distance.value * 0.000621371;
      }
    } catch (dhError) {
      console.warn("Deadhead Calculation Failed (Non-Fatal):", dhError);
      // Continue with 0 deadhead
    }

    // ... (rest of logic same) ...
    const combinedText = (pickup + dropoff).toLowerCase();
    const isTellerCounty = combinedText.match(/woodland|divide|floroyant|cripple creek|teller/i) !== null;
    const isAirport = combinedText.includes("airport") || combinedText.includes("cos");

    let totalDistance = leg1DistanceMiles;
    let totalStops = parseInt(stops) || 0;

    if (tripType === 'round-trip') {
      totalDistance += leg1DistanceMiles;
      const returnStopCount = parseInt(returnStops) || 0;
      totalStops += returnStopCount;
      totalDistance += (totalStops * 3);
    } else {
      totalDistance += (totalStops * 3);
    }

    const finalWaitTime = tripType === 'round-trip' ? (parseFloat(layoverHours) || 0) : (simpleWaitTime ? 1 : 0);

    const priceParams: TripParams = {
      distanceMiles: totalDistance,
      deadheadMiles,
      stops: totalStops,
      isTellerCounty,
      isAirport,
      waitTimeHours: finalWaitTime
    };

    const quote = calculateTripPrice(priceParams);

    quote.debug = {
      origin: validPickup,
      destination: validDropoff,
      leg1Miles: leg1DistanceMiles.toFixed(1),
      deadheadMiles: deadheadMiles.toFixed(1),
      duration: leg1DurationText,
      isTellerCounty,
      validated: true,
      keySource // Debug info to verify which key worked
    };

    quote.distance = totalDistance;
    quote.time = parseInt(leg1DurationText) || 0;

    return NextResponse.json({
      success: true,
      quote
    });

  } catch (error: any) {
    console.error("Pricing Error:", error);

    // DEBUG: Key Metadata
    // We try to reconstruct what might have happened
    const pKey = process.env.GOOGLE_MAPS_API_KEY;
    const fKey = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY;
    const pPrefix = pKey ? pKey.substring(0, 5) + "..." : "MISSING";
    const fPrefix = fKey ? fKey.substring(0, 5) + "..." : "MISSING";

    const errorMessage = error?.response?.data?.error_message || error?.message || "Unknown error";
    const errorStatus = error?.response?.data?.status || "UNKNOWN_STATUS";

    return NextResponse.json({
      success: false,
      error: `Pricing Failed: ${errorMessage} (${errorStatus}) | P:${pPrefix} / F:${fPrefix}`,
      debug: {
        details: error?.response?.data || "No API response data"
      }
    }, { status: 500 });
  }
}
