export interface Drive {
    id: string;
    startTime: number;
    endTime: number;
    durationMinutes: number;
    distanceMiles: number;
    startAddress: string;
    endAddress: string;
    startOdometer: number;
    endOdometer: number;
    path: string;
    cost: number;

    // Categorization (Added via Excel Match)
    category?: 'Business' | 'Personal' | 'Uncategorized';

    // Uber Financials (from Excel)
    uberData?: {
        tripId?: string;
        passenger?: string;
        offer?: number;
        earnings?: number;
        riderPayment?: number;
        fees?: number;
        tips?: number;
        uberMiles?: number;
        uberDuration?: string;
    };

    // Audit Flags
    audit?: {
        mileageMismatch: boolean; // True if Tessie vs Uber > 10% diff
        durationMismatch: boolean;
    };
}
