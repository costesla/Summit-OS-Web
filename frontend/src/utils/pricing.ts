export interface TripParams {
    distanceMiles: number;
    deadheadMiles: number; // Distance from Driver's "Home Base" to Pickup
    stops: number;
    isTellerCounty: boolean;
    isAirport: boolean; // Airport Flag
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
        keySource?: string;
    };
}

/**
 * SummitOS Pricing Engine v3.0
 * High-precision tiered pricing for El Paso County.
 *
 * Logic:
 * 1. Base Engagement: $30.00 (covers first 5.0 miles)
 * 2. Mileage: $1.75 per mile after the first 5.0 miles (no upper tier)
 */
export function calculateTripPrice(params: TripParams): PriceBreakdown {
    const { distanceMiles, stops, isTellerCounty, waitTimeHours } = params;

    // 1. Base & Distance Fare
    const fixedBase = 30.00;
    const RATE_PER_MILE = 1.75;
    const FREE_MILES = 5.0;

    const billableMiles = Math.max(0, distanceMiles - FREE_MILES);
    const mileageCharge = billableMiles * RATE_PER_MILE;

    // 2. Extra Fees
    const deadheadFee = 0; // Deprecated
    const stopFee = stops * 5.00;
    const tellerFee = isTellerCounty ? 15.00 : 0;
    const waitFee = waitTimeHours * 20.00;

    // 3. Total
    const total = fixedBase + mileageCharge + deadheadFee + stopFee + tellerFee + waitFee;

    return {
        baseFare: Number(fixedBase.toFixed(2)),
        overage: Number(mileageCharge.toFixed(2)),
        deadheadFee: Number(deadheadFee.toFixed(2)),
        stopFee: Number(stopFee.toFixed(2)),
        tellerFee: Number(tellerFee.toFixed(2)),
        waitFee: Number(waitFee.toFixed(2)),
        total: Number(total.toFixed(2))
    };
}

