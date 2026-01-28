import { NextResponse } from 'next/server';

export async function GET(request: Request) {
    const { searchParams } = new URL(request.url);
    const bookingId = searchParams.get('id');

    if (!bookingId) {
        return new NextResponse("Missing Booking ID", { status: 400 });
    }

    // Confirm in Backend
    const functionUrl = process.env.AZURE_FUNCTION_URL + "/api/update-payment";
    const functionKey = process.env.AZURE_FUNCTION_KEY;

    try {
        await fetch(functionUrl, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "x-functions-key": functionKey || ""
            },
            body: JSON.stringify({ bookingId, paymentMethod: "Cash (Confirmed)" })
        });
    } catch (e) {
        console.error("Failed to confirm cash payment in backend", e);
    }

    // Return HTML Success Page
    const html = `
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Payment Confirmed</title>
        <style>
            body { font-family: system-ui, -apple-system, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; background: #ecfdf5; color: #065f46; }
            .card { background: white; padding: 40px; border-radius: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.1); text-align: center; max-width: 400px; width: 90%; }
            .icon { font-size: 64px; margin-bottom: 20px; display: block; }
            h1 { margin: 0 0 10px; color: #059669; }
            p { margin: 0; color: #4b5563; }
        </style>
    </head>
    <body>
        <div class="card">
            <span class="icon">✅</span>
            <h1>Payment Confirmed</h1>
            <p>Thank you! Your cash payment has been verified.</p>
        </div>
    </body>
    </html>
  `;

    return new NextResponse(html, {
        headers: { 'Content-Type': 'text/html' },
    });
}
