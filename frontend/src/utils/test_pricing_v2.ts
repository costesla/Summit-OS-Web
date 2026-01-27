
import { calculateTripPrice, TripParams } from './pricing';

const runTest = (miles: number, description: string) => {
    const params: TripParams = {
        distanceMiles: miles,
        deadheadMiles: 0,
        stops: 0,
        isTellerCounty: false,
        isAirport: false,
        waitTimeHours: 0
    };
    const quote = calculateTripPrice(params);
    console.log(`[${description}] ${miles.toFixed(2)} miles`);
    console.log(`  Base: $${quote.baseFare}`);
    console.log(`  Overage: $${quote.overage} (Tier Charges)`);
    console.log(`  Total: $${quote.total}`);
    console.log('---');
};

console.log('=== SUMMIT OS V2.0 PRICING TEST ===\n');

// 1. Short Trip (Under 5 miles) - Should be $15.00
runTest(3.0, 'Grocery Run');

// 2. Border Trip (Exactly 5 miles) - Should be $15.00
runTest(5.0, 'Limit Test');

// 3. Medium Trip (10 miles)
// Base $15 + (5 * 1.75 = 8.75) = $23.75
runTest(10.0, 'Cross Town');

// 4. Long Trip (45 miles - e.g. Monument/North)
// Base $15
// Tier 1 (15mi * 1.75) = $26.25
// Tier 2 (25mi * 1.25) = $31.25
// Total = $15 + $26.25 + $31.25 = $72.50
runTest(45.0, 'Long Haul');

// 5. Marathon (80 miles - e.g. DIA)
// Base $15
// Tier 1 (15 * 1.75) = $26.25
// Tier 2 (60 * 1.25) = $75.00
// Total = $116.25
runTest(80.0, 'DIA Airport');
