import { NextResponse } from 'next/server';

export async function GET(request: Request) {
    const { searchParams } = new URL(request.url);
    const token = searchParams.get('token');

    // Verify token if needed (omitted for now)

    const functionUrl = process.env.AZURE_FUNCTION_URL + "/api/cabin-api";
    const functionKey = process.env.AZURE_FUNCTION_KEY;

    try {
        const res = await fetch(functionUrl, {
            headers: {
                "x-functions-key": functionKey || ""
            }
        });

        if (!res.ok) {
            throw new Error("Backend fetch failed");
        }

        const data = await res.json();
        return NextResponse.json(data);
    } catch (error) {
        console.error("Cabin State Error:", error);
        // Fallback Mock Data for Demo if Backend Fails
        return NextResponse.json({
            speed: 0,
            elevation: 6035,
            seats: { rl: 0, rr: 0 },
            windows_vented: false,
            mock: true
        });
    }
}
