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
 * The "Ohana" Pricing Algorithm
 * Protecting margins while staying fair.
 */
export function calculateTripPrice(params: TripParams): PriceBreakdown {
    // 1. Tiered Base Fare
    let baseFare = 20.00;

    // Check for Denver (Pickup or Dropoff implied by distance/context, but simplistic check here)
    // NOTE: isAirport is currently mainly for COS, we need a better check.
    // For now, let's use distance as a proxy if > 60 miles, likely Denver/Pueblo.
    // Ideally, we'd pass a specific "isDenver" flag, but we can infer from distance for now.

    if (params.distanceMiles > 60 || params.isAirport && params.distanceMiles > 50) {
        // DENVER / LONG HAUL CAP
        // User requested: "Denver capped at $100"
        baseFare = 100.00;
    } else if (params.distanceMiles > 30) {
        // LONG DISTANCE (Non-Denver, e.g. Pueblo, Castle Rock)
        // Rate: $2.00 / mile
        baseFare = params.distanceMiles * 2.00;
    } else {
        // LOCAL TIERS (< 30 miles)
        if (params.distanceMiles < 5) {
            baseFare = 10.00;
        } else if (params.distanceMiles < 12) {
            baseFare = 15.00;
        } else {
            baseFare = 20.00;
        }
    }

    // 2. Mileage Overage: REMOVED per user request
    const overage = 0;

    // 3. Deadhead Fee: REMOVED per user request
    const deadheadFee = 0;

    // 4. Stop Fee: $5.00 per extra stop
    const stopFee = params.stops * 5.00;

    // 5. Teller County Surcharge: $15.00 flat
    const tellerFee = params.isTellerCounty ? 15.00 : 0;

    // 6. Wait Time: $20.00 per hour (Pro-rated)
    const waitFee = params.waitTimeHours * 20.00;

    // Total Calculation
    const total = baseFare + overage + deadheadFee + stopFee + tellerFee + waitFee;

    return {
        baseFare: Number(baseFare.toFixed(2)),
        overage: Number(overage.toFixed(2)),
        deadheadFee: Number(deadheadFee.toFixed(2)),
        stopFee: Number(stopFee.toFixed(2)),
        tellerFee: Number(tellerFee.toFixed(2)),
        waitFee: Number(waitFee.toFixed(2)),
        total: Number(total.toFixed(2))
    };
}
