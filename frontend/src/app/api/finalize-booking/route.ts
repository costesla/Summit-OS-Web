import { NextResponse } from 'next/server';
import Stripe from 'stripe';
import { sendReceiptEmail, sendAdminNotification } from '@/lib/email';

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY || 'sk_test_placeholder', {
    apiVersion: '2023-10-16' as any,
});

export async function POST(req: Request) {
    try {
        const body = await req.json();
        const { session_id } = body;

        if (!session_id) {
            return NextResponse.json({ error: "No session ID" }, { status: 400 });
        }

        const session = await stripe.checkout.sessions.retrieve(session_id);

        if (session.payment_status !== 'paid') {
            return NextResponse.json({ error: "Payment not completed" }, { status: 400 });
        }

        const meta = session.metadata;
        if (!meta) {
            return NextResponse.json({ error: "No metadata found" }, { status: 400 });
        }

        // We only want to book this ONCE. Stripe sessions don't prevent re-polling
        // Ideally we'd have a database or idempotency check, but for now we simply log it.
        
        // 1. Create calendar booking
        const bookingRes = await fetch("https://summitos-api.azurewebsites.net/api/calendar-book", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                customerName: meta.customerName,
                customerEmail: meta.customerEmail,
                customerPhone: meta.customerPhone,
                pickup: meta.pickup,
                dropoff: meta.dropoff,
                appointmentStart: meta.appointmentStart,
                duration: 60,
                price: meta.fareString,
                passengers: parseInt(meta.passengers || '1'),
                paymentMethod: 'Stripe'
            }),
        });
        
        const bookingData = await bookingRes.json();
        if (!bookingData.success) {
            console.error("Calendar Booking Failed", bookingData);
            return NextResponse.json({ error: "Booking Failed on Backend" }, { status: 500 });
        }

        // 2. Log to SQL Database
        try {
            await fetch("https://summitos-api.azurewebsites.net/api/log-private-trip", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    customerName: meta.customerName,
                    customerEmail: meta.customerEmail,
                    customerPhone: meta.customerPhone,
                    pickup: meta.pickup,
                    dropoff: meta.dropoff,
                    fare: parseFloat(meta.fareString.replace(/[^0-9.]/g, '')),
                    appointmentTime: meta.appointmentStart,
                    calendarEventId: bookingData.eventId,
                    passengers: parseInt(meta.passengers || '1'),
                }),
            });
        } catch (dbError) {
            console.warn("Failed to log to database:", dbError);
        }

        // 3. Send Receipt Email via local Nodemailer logic
        try {
            const receiptData = {
                customerName: meta.customerName || "Customer",
                customerEmail: meta.customerEmail || "",
                pickup: meta.pickup || "N/A",
                dropoff: meta.dropoff || "N/A",
                date: meta.appointmentStart ? new Date(meta.appointmentStart).toLocaleString() : "To be scheduled",
                distance: meta.tripDistance ? `${meta.tripDistance} miles` : 'N/A',
                duration: meta.tripDuration ? `${meta.tripDuration} mins` : 'N/A',
                priceCheckdown: {
                    base: "-",
                    mileage: "-",
                    wait: "-",
                    total: meta.fareString || "$0.00",
                },
                bookingId: bookingData.eventId || "Pending",
                paymentMethod: 'Stripe',
            };
            await sendReceiptEmail(receiptData);
            await sendAdminNotification(receiptData);
        } catch (e) {
            console.warn("Failed to send receipt:", e);
        }

        return NextResponse.json({ success: true, eventId: bookingData.eventId });
    } catch (err: any) {
        console.error("Finalize Booking Error:", err);
        return NextResponse.json({ error: err.message }, { status: 500 });
    }
}
