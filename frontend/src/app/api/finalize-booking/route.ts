import { NextResponse } from 'next/server';
import Stripe from 'stripe';

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

        // 3. Send Receipt Email via Next.js
        try {
            await fetch(`${req.headers.get('origin') || process.env.NEXT_PUBLIC_BASE_URL || 'http://localhost:3000'}/api/book`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    name: meta.customerName,
                    email: meta.customerEmail,
                    phone: meta.customerPhone,
                    passengers: parseInt(meta.passengers || '1'),
                    pickup: meta.pickup,
                    dropoff: meta.dropoff,
                    price: meta.fareString,
                    appointmentStart: meta.appointmentStart,
                    tripDetails: {
                        dist: meta.tripDistance,
                        time: meta.tripDuration,
                    },
                }),
            });
        } catch (e) {
            console.warn("Failed to send receipt:", e);
        }

        return NextResponse.json({ success: true, eventId: bookingData.eventId });
    } catch (err: any) {
        console.error("Finalize Booking Error:", err);
        return NextResponse.json({ error: err.message }, { status: 500 });
    }
}
