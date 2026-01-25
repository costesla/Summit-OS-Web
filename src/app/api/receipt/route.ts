import { NextResponse } from 'next/server';
import { Resend } from 'resend';

export const dynamic = 'force-dynamic';

export async function POST(request: Request) {
    try {
        const body = await request.json();
        const { name, email, date, miles, price, paymentMethod, pickup, dropoff } = body;

        if (!process.env.RESEND_API_KEY) {
            return NextResponse.json({ success: true, message: 'Simulation: Receipt logged' });
        }

        const resend = new Resend(process.env.RESEND_API_KEY);

        // Helper to scrub PII (Remove house numbers)
        const scrubAddress = (addr: string) => {
            if (!addr) return '';
            // Regex: Remove starting digits and whitespace (e.g. "123 Main St" -> "Main St")
            return addr.replace(/^\d+\s+/, '');
        };

        const safePickup = scrubAddress(pickup);
        const safeDropoff = scrubAddress(dropoff);

        const { data, error } = await resend.emails.send({
            from: 'Costesla Receipts <onboarding@resend.dev>',
            to: ['peter.teehan@costesla.com'], // In prod, this would be [email]
            // cc: ['peter.teehan@costesla.com'],
            subject: `Receipt: Trip on ${date}`,
            html: `
            <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden;">
                <div style="background-color: #000; color: #fff; padding: 20px; text-align: center;">
                    <h1 style="margin: 0; font-size: 24px;">COSTESLA</h1>
                    <p style="margin: 5px 0 0; color: #ccc;">Premium Mobility Service</p>
                </div>
                
                <div style="padding: 30px;">
                    <h2 style="margin-top: 0; color: #333;">Your Ride Receipt</h2>
                    <p style="color: #666;">Thanks for riding with Peter. Here is the summary of your trip.</p>
                    
                    <div style="margin: 20px 0; border-top: 2px dashed #eee; border-bottom: 2px dashed #eee; padding: 20px 0;">
                        <table style="width: 100%; border-collapse: collapse;">
                            <tr>
                                <td style="padding: 8px 0; color: #666;">Date</td>
                                <td style="padding: 8px 0; text-align: right; font-weight: bold;">${date}</td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; color: #666;">Total Miles</td>
                                <td style="padding: 8px 0; text-align: right; font-weight: bold;">${miles} mi</td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; color: #666;">Payment Method</td>
                                <td style="padding: 8px 0; text-align: right; font-weight: bold;">${paymentMethod}</td>
                            </tr>
                            <tr>
                                <td style="padding: 15px 0 0; font-size: 18px; font-weight: bold; color: #333;">Total Paid</td>
                                <td style="padding: 15px 0 0; text-align: right; font-size: 18px; font-weight: bold; color: #000;">$${parseFloat(price).toFixed(2)}</td>
                            </tr>
                        </table>
                    </div>

                    <div style="background: #f9f9f9; padding: 15px; border-radius: 8px;">
                        <h3 style="margin: 0 0 10px; font-size: 14px; text-transform: uppercase; color: #999;">Route Details</h3>
                        <p style="margin: 5px 0;"><strong>Pickup:</strong> ${safePickup}</p>
                        <p style="margin: 5px 0;"><strong>Dropoff:</strong> ${safeDropoff}</p>
                    </div>
                </div>

                <div style="background-color: #f5f5f5; padding: 20px; text-align: center; color: #888; font-size: 12px;">
                    <p>&copy; ${new Date().getFullYear()} Costesla LLC</p>
                    <p>Issues with this receipt? Reply to this email.</p>
                </div>
            </div>
            `
        });

        if (error) {
            console.error(error);
            return NextResponse.json({ error: error.message }, { status: 500 });
        }

        return NextResponse.json({ success: true, data });
    } catch (e) {
        return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
    }
}
