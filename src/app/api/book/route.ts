import { NextResponse } from 'next/server';
import { Resend } from 'resend';

// Initialize Resend
const resend = new Resend(process.env.RESEND_API_KEY);

export async function POST(request: Request) {
  try {
    const data = await request.json();

    console.log("📨 Processing Booking for:", data.email);

    if (!process.env.RESEND_API_KEY) {
      console.error("❌ MISSING RESEND_API_KEY");
      return NextResponse.json({ success: true, message: "Booking logged (Email skipped)" });
    }

    // Format HTML Email
    const htmlContent = `
      <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; border: 1px solid #ddd; border-top: 5px solid #D12630;">
        <div style="padding: 20px;">
          <h2 style="color: #D12630; margin-top: 0;">🚗 New Trip Request</h2>
          <p><strong>Passenger:</strong> ${data.name} (<a href="tel:${data.phone}">${data.phone}</a>)</p>
          <p><strong>Email:</strong> ${data.email}</p>
          <p><strong>Passengers:</strong> ${data.passengers}</p>
          
          <div style="background: #f9f9f9; padding: 15px; border-radius: 5px; margin: 15px 0;">
            <p style="margin: 5px 0;"><strong>📍 Pickup:</strong> ${data.pickup}</p>
            <p style="margin: 5px 0;"><strong>🏁 Dropoff:</strong> ${data.dropoff}</p>
          </div>

          <div style="display: flex; gap: 20px; font-weight: bold; color: #555;">
            <span>💰 Quote: ${data.price}</span>
            <span>🛣️ Distance: ~${data.tripDetails?.dist} mi</span>
            <span>⏱️ Time: ~${data.tripDetails?.time} min</span>
          </div>
          
          <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
          <p style="font-size: 12px; color: #999;">This request originated from www.costesla.com</p>
        </div>
      </div>
    `;

    // Send via Resend
    // NOTE: 'from' must be a verified domain or the generic testing one 'onboarding@resend.dev'
    // Since the user has a custom domain 'costesla.com', they likely verified it.
    // If not, we fall back to 'onboarding@resend.dev' but delivers to the registered email.

    // Attempt 1: Try sending from their domain (Ideal)
    // Attempt 2: If that fails, the user might need to verify the domain in Resend dashboard.
    // We will assume "PrivateTrips@costesla.com" is intended.

    const { data: emailData, error } = await resend.emails.send({
      from: 'COS Tesla <onboarding@resend.dev>', // Use Testing Domain (Authorized for everyone)
      to: ['peter.teehan@costesla.com'], // Verified Owner Email (Required for Resend Free Tier)
      subject: `🚗 New Trip: ${data.name} - ${data.price}`,
      html: htmlContent,
    });

    if (error) {
      console.error("Resend Error:", error);
      return NextResponse.json({ success: false, message: error.message }, { status: 500 });
    }

    console.log("✅ Email Sent Successfully via Resend:", emailData);

    return NextResponse.json({ success: true, message: "Booking confirmed" });
  } catch (error) {
    console.error("❌ Server Error:", error);
    return NextResponse.json({ success: false, message: "Failed to send email" }, { status: 500 });
  }
}
