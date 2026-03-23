import { NextResponse } from 'next/server';
import Stripe from 'stripe';

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY || 'sk_test_placeholder', {
    apiVersion: '2023-10-16' as any,
});

export async function POST(req: Request) {
    try {
        const body = await req.json();
        const { 
            customerName, 
            customerEmail, 
            customerPhone, 
            pickup, 
            dropoff, 
            appointmentStart, 
            price, 
            passengers,
            tripDistance,
            tripDuration
        } = body;

        // Convert formatted price string (e.g., "$100.00") to number for Stripe
        const amountNum = parseFloat(price.replace(/[^0-9.]/g, ''));
        const amountCents = Math.round(amountNum * 100);

        const session = await stripe.checkout.sessions.create({
            payment_method_types: ['card'],
            customer_email: customerEmail,
            line_items: [
                {
                    price_data: {
                        currency: 'usd',
                        product_data: {
                            name: 'SummitOS Booking',
                            description: `${pickup} \n-> ${dropoff}`,
                        },
                        unit_amount: amountCents,
                    },
                    quantity: 1,
                },
            ],
            mode: 'payment',
            success_url: `${req.headers.get('origin')}/book/success?session_id={CHECKOUT_SESSION_ID}`,
            cancel_url: `${req.headers.get('origin')}/book?payment_cancelled=true`,
            metadata: {
                customerName,
                customerEmail,
                customerPhone,
                pickup,
                dropoff,
                appointmentStart,
                passengers: passengers.toString(),
                tripDistance: tripDistance || 'N/A',
                tripDuration: tripDuration || 'N/A',
                fareString: price
            }
        });

        return NextResponse.json({ id: session.id, url: session.url });
    } catch (err: any) {
        console.error("Stripe Checkout Error:", err);
        return NextResponse.json({ error: err.message }, { status: 500 });
    }
}
