import { NextResponse } from 'next/server';

export async function POST(request: Request) {
    try {
        const { bookingId, paymentMethod } = await request.json();

        if (!bookingId || !paymentMethod) {
            return NextResponse.json({ success: false, error: "Missing fields" }, { status: 400 });
        }

        console.log(`💸 Updating payment for ${bookingId} to ${paymentMethod}`);

        // Call Azure Function
        const functionUrl = process.env.AZURE_FUNCTION_URL + "/api/update-payment";
        const functionKey = process.env.AZURE_FUNCTION_KEY;

        const response = await fetch(functionUrl, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "x-functions-key": functionKey || ""
            },
            body: JSON.stringify({ bookingId, paymentMethod })
        });

        if (!response.ok) {
            console.error("⚠️ Failed to update payment in backend:", await response.text());
        }

        return NextResponse.json({ success: true });

    } catch (error) {
        console.error("❌ Payment Update Error:", error);
        return NextResponse.json({ success: false, error: "Internal Server Error" }, { status: 500 });
    }
}
