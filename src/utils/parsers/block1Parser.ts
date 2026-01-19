import * as XLSX from 'xlsx';

export interface ParsedUberTrip {
    tripNumber: number;
    startTime: string; // "2:16 PM"
    endTime: string;   // "2:51 PM"
    rider: string;
    pickup: string;
    dropoff: string;
    fare: number;      // Rider Payment
    earnings: number;  // Driver Total
    tip: number;
    fees: number;      // Uber Cut
    distance: number;
    duration: number;
}

export const parseBlock1 = async (fileBuffer: ArrayBuffer) => {
    const workbook = XLSX.read(fileBuffer, { type: 'array' });

    // 1. Parse Trips (Compact)
    const tripSheet = workbook.Sheets['Trips (Compact)'];
    if (!tripSheet) throw new Error("Missing 'Trips (Compact)' sheet");

    const rawTrips = XLSX.utils.sheet_to_json<any[]>(tripSheet, { header: 1 });
    // Assuming Row 0 is headers
    const headers = rawTrips[0] as string[];
    const rows = rawTrips.slice(1);

    const parsedTrips: ParsedUberTrip[] = rows.map(row => {
        // Map based on known schema index or header name?
        // Using index for robustness if names change slightly, but checking header is safer.
        // Based on schema output:
        // 0: Trip #
        // 1: Time (Start-End)
        // 2: Rider
        // 4: Pickup
        // 5: DropOff
        // 8: Rider Payment
        // 9: Uber Cut
        // 12: Driver Total
        // 13: Tip (might be column K or L depending on index, schema showed 11 as empty in example)

        // Helper to parse currency string "$12.34" or number
        const val = (idx: number) => {
            const v = row[idx];
            if (typeof v === 'number') return v;
            if (typeof v === 'string') return parseFloat(v.replace(/[$,]/g, '')) || 0;
            return 0;
        };

        const timeStr = row[1] as string; // "2:16–2:51 PM" or sometimes "2:16-2:51 PM"
        let start = '', end = '';
        if (timeStr) {
            // Split by en-dash or hyphen
            const parts = timeStr.split(/[–-]/);
            if (parts.length === 2) {
                start = parts[0].trim(); // "2:16" (might lack PM if same as end)
                end = parts[1].trim();   // "2:51 PM"

                // Propagate AM/PM to start if missing
                if (!start.match(/[AP]M/i) && end.match(/[AP]M/i)) {
                    const meridiem = end.match(/[AP]M/i)![0];
                    start += ` ${meridiem}`;
                }
            }
        }

        return {
            tripNumber: row[0],
            startTime: start,
            endTime: end,
            rider: row[2],
            pickup: row[4],
            dropoff: row[5],
            fare: val(8), // Rider Payment
            fees: val(9), // Uber Cut
            earnings: val(12), // Driver Total
            tip: val(11),      // Tip
            distance: val(6),
            duration: val(7)
        };
    }).filter(t => t.tripNumber); // Filter empty rows

    // 2. Extract Date from "Filenames Log" if possible to auto-detect
    const fileSheet = workbook.Sheets['Filenames Log'];
    let detectedDate: string | null = null;
    if (fileSheet) {
        const fileRows = XLSX.utils.sheet_to_json<any[]>(fileSheet, { header: 1 });
        // Look for filenames like "B1_Sweep1_20250829_1509.jpg"
        for (const r of fileRows) {
            const fname = r[4] as string; // Index 4 based on schema
            if (fname && typeof fname === 'string') {
                const match = fname.match(/(\d{8})/); // Match 20250829
                if (match) {
                    const ds = match[1]; // "20250829"
                    // Format to YYYY-MM-DD
                    detectedDate = `${ds.substring(0, 4)}-${ds.substring(4, 6)}-${ds.substring(6, 8)}`;
                    break;
                }
            }
        }
    }

    return { trips: parsedTrips, detectedDate };
};
