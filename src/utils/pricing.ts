export interface TripParams {
    distanceMiles: number;
    deadheadMiles: number; // Distance from Driver's "Home Base" to Pickup
    stops: number;
    isTellerCounty: boolean;
    isAirport: boolean; // NEW: Airport Flag
    waitTimeHours: number;
}

export interface PriceBreakdown {
    baseFare: number;
    overage: number;
    deadheadFee: number;
    stopFee: number;
    tellerFee: number;
    waitFee: number;
    total: number;
    distance?: number; // Trip distance in miles
    time?: number; // Estimated trip time in minutes
    debug?: {
        origin: string;
        destination: string;
        validated: boolean;
        isTellerCounty: boolean;
        deadheadMiles: string;
        leg1Miles: string;
        duration: string;
    };
}

/**
 * SummitOS Pricing Engine v2.0
 * High-precision tiered pricing for El Paso County.
 * 
 * Logic:
 * 1. Base Engagement: $15.00 (Fixed for first 5.0 miles)
 * 2. Tier 1: $1.75 per mile (Miles 5.1 - 20.0)
 * 3. Tier 2: $1.25 per mile (Miles 20.1+)
 */
export function calculateTripPrice(params: TripParams): PriceBreakdown {
    const { distanceMiles, stops, isTellerCounty, waitTimeHours } = params;

    // 1. Calculate Base & Distance Fare (Tiered)
    let baseFare = 0;
    let tier1Charge = 0;
    let tier2Charge = 0;

    if (distanceMiles <= 5.0) {
        // FLAT BASE
        baseFare = 15.00;
    } else if (distanceMiles <= 20.0) {
        // TIER 1 ZONE
        baseFare = 15.00;
        const tier1Miles = distanceMiles - 5.0;
        tier1Charge = tier1Miles * 1.75;
    } else {
        // TIER 2 ZONE (Long Haul)
        baseFare = 15.00;
        const tier1Miles = 15.0; // Full 15 miles of Tier 1 (5.0 to 20.0)
        tier1Charge = tier1Miles * 1.75; // $26.25

        const tier2Miles = distanceMiles - 20.0;
        tier2Charge = tier2Miles * 1.25;
    }

    // Combine into a single "Base Fare" for display, or separate if UI supports it.
    // For now, consistent with interface, we sum them into baseFare or distribute.
    // The previous interface only had 'baseFare' and 'overage'. 
    // We will put the fixed $15 in baseFare and the mileage charges in 'overage' for clarity, 
    // OR sum everything into baseFare if the UI expects a single line item.
    // Looking at BookingEngine.tsx: it displays "Base Fare" and "Mileage Overage".
    // Let's call the $15 "Base Fare" and the variable portion "Mileage Overage" to be transparent.

    const fixedBase = 15.00;
    const mileageCharge = (distanceMiles <= 5.0) ? 0 : (tier1Charge + tier2Charge);

    // 2. Extra Fees
    const deadheadFee = 0; // Deprecated
    const stopFee = stops * 5.00;
    const tellerFee = isTellerCounty ? 15.00 : 0;
    const waitFee = waitTimeHours * 20.00;

    // 3. Total
    const total = fixedBase + mileageCharge + deadheadFee + stopFee + tellerFee + waitFee;

    return {
        baseFare: Number(fixedBase.toFixed(2)),
        overage: Number(mileageCharge.toFixed(2)), // Tiers 1 & 2 combined
        deadheadFee: Number(deadheadFee.toFixed(2)),
        stopFee: Number(stopFee.toFixed(2)),
        tellerFee: Number(tellerFee.toFixed(2)),
        waitFee: Number(waitFee.toFixed(2)),
        total: Number(total.toFixed(2))
    };
}
