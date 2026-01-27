import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

export async function POST(request: Request) {
    try {
        const body = await request.json();
        const { flightNumber } = body;

        // --- DEMO MODE (Simulated Data) ---
        // If no API key is set, we return this simulated response to show the UI working.
        if (!process.env.AVIATIONSTACK_API_KEY) {
            console.log("Demo Mode: Returning simulated flight data for " + flightNumber);

            // Simulate network delay
            await new Promise(resolve => setTimeout(resolve, 800));

            return NextResponse.json({
                success: true,
                data: {
                    flight_status: "active",
                    departure: {
                        iata: "SFO",
                        airport: "San Francisco International",
                        scheduled: new Date().toISOString()
                    },
                    arrival: {
                        iata: "DEN",
                        airport: "Denver International",
                        scheduled: new Date(Date.now() + 3600000).toISOString(), // +1 hour
                        estimated: new Date(Date.now() + 3600000).toISOString()
                    },
                    airline: {
                        name: "United Airlines",
                    },
                    flight: {
                        iata: flightNumber || "UA123"
                    }
                }
            });
        }

        // --- REAL API MODE ---
        // Only runs if AVIATIONSTACK_API_KEY is present in .env.local
        const apiKey = process.env.AVIATIONSTACK_API_KEY;
        const url = `http://api.aviationstack.com/v1/flights?access_key=${apiKey}&flight_iata=${flightNumber}&limit=1`;

        const res = await fetch(url);
        const data = await res.json();

        if (data.data && data.data.length > 0) {
            return NextResponse.json({ success: true, data: data.data[0] });
        } else {
            return NextResponse.json({ success: false, error: "Flight not found" }, { status: 404 });
        }

    } catch (err) {
        console.error('Flight API Error:', err);
        return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
    }
}
