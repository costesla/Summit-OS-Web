import { NextResponse } from 'next/server';

export async function POST(request: Request) {
    try {
        const body = await request.json();

        // Pass specific fields
        const payload = {
            command: body.command,
            seat: body.seat,
            level: body.level
        };

        const functionUrl = process.env.AZURE_FUNCTION_URL + "/api/cabin-api";
        const functionKey = process.env.AZURE_FUNCTION_KEY;

        const res = await fetch(functionUrl, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "x-functions-key": functionKey || ""
            },
            body: JSON.stringify(payload)
        });

        if (!res.ok) {
            throw new Error("Backend control failed");
        }

        return NextResponse.json({ success: true });

    } catch (error) {
        console.error("Cabin Control Error:", error);
        return NextResponse.json({ success: false, error: "Internal Server Error" }, { status: 500 });
    }
}
