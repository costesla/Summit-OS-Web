export interface TripParams {
    distanceMiles: number;
    deadheadMiles: number; // Distance from Driver's "Home Base" to Pickup
    stops: number;
    isTellerCounty: boolean;
    isAirport: boolean; // Airport Flag
    isDenverAirport?: boolean;
    waitTimeHours: number;
    isOutOfCounty?: boolean;
}

export interface PriceBreakdown {
    baseFare: number;
    mileageFare: number;
    stopFee: number;
    tellerFee: number;
    tollFee: number;
    waitFee: number;
    corridorAdjustment: number;
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
 * SummitOS Pricing Engine v3.0 (Effective September 1, 2026)
 * - Base Fare: $25.00
 * - Road Mileage: $2.00 per mile (calculated via Google Distance Matrix API)
 * - Denver Airport (DEN) Corridor Floor: $225.00 Minimum
 * - Toll Pass-Through (DEN / E-470): $20.00
 * - Mountain Surcharge (Teller County): $15.00
 * - Intermediate Waypoints: $5.00 / stop
 * - Driver Standby / Wait Time: $25.00 / hour
 */
export function calculateTripPrice(params: TripParams): PriceBreakdown {
    const { distanceMiles, stops, isTellerCounty, isDenverAirport, waitTimeHours } = params;

    // 1. Base & Distance Fare ($2.00/mile from mile 0)
    const fixedBase = 25.00;
    const RATE_PER_MILE = 2.00;
    const DEN_FLOOR = 225.00;

    const mileageCharge = Number((distanceMiles * RATE_PER_MILE).toFixed(2));

    // 2. Extra Fees & Surcharges
    const stopFee = stops * 5.00;
    const tellerFee = isTellerCounty ? 15.00 : 0;
    const tollFee = isDenverAirport ? 20.00 : 0;
    const waitFee = waitTimeHours * 25.00;

    const subtotal = fixedBase + mileageCharge + stopFee + tellerFee + tollFee + waitFee;

    // 3. Corridor Floor Adjustment (Guarantees $225 min floor for DEN Airport)
    let corridorAdjustment = 0;
    if (isDenverAirport && subtotal < DEN_FLOOR) {
        corridorAdjustment = Number((DEN_FLOOR - subtotal).toFixed(2));
    }

    const total = subtotal + corridorAdjustment;

    return {
        baseFare: Number(fixedBase.toFixed(2)),
        mileageFare: Number(mileageCharge.toFixed(2)),
        stopFee: Number(stopFee.toFixed(2)),
        tellerFee: Number(tellerFee.toFixed(2)),
        tollFee: Number(tollFee.toFixed(2)),
        waitFee: Number(waitFee.toFixed(2)),
        corridorAdjustment: Number(corridorAdjustment.toFixed(2)),
        total: Number(total.toFixed(2))
    };
}

/**
 * Daily Exclusivity Bundle
 * Option to add a $100 flat-rate bundle that includes the first 50 miles.
 */
export function calculateBundlePrice(params: TripParams): PriceBreakdown {
    const { distanceMiles, stops, isTellerCounty } = params;

    // 1. Base & Distance Fare
    const BUNDLE_PRICE = 100.00;
    const RATE_PER_MILE = 1.50;
    const FREE_MILES = 50.0;

    const billableMiles = Math.max(0, distanceMiles - FREE_MILES);
    const mileageCharge = billableMiles * RATE_PER_MILE;

    // 2. Extra Fees
    // Teller fee still applies? I'll assume standard routing rules apply but base is 100.
    const tellerFee = isTellerCounty ? 15.00 : 0;
    // Disabling stop fees since local trips are unlimited on-call for 8 hours
    const stopFee = 0; 
    const deadheadFee = 0;
    const waitFee = 0; // Wait time is included up to 8 hours

    // 3. Total
    const total = BUNDLE_PRICE + mileageCharge + tellerFee;

    return {
        baseFare: Number(BUNDLE_PRICE.toFixed(2)),
        overage: Number(mileageCharge.toFixed(2)),
        deadheadFee: Number(deadheadFee.toFixed(2)),
        stopFee: Number(stopFee.toFixed(2)),
        tellerFee: Number(tellerFee.toFixed(2)),
        waitFee: Number(waitFee.toFixed(2)),
        total: Number(total.toFixed(2))
    };
}

