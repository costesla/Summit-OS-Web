import { NextResponse } from 'next/server';
import { sendReceiptEmail, sendAdminNotification } from '@/lib/email';

export async function POST(request: Request) {
  try {
    const data = await request.json();

    console.log("📨 Processing Booking for:", data.email);

    // Prepare Receipt Data
    // Note: 'data.tripDetails' comes from frontend as { dist: '12.5', time: '25 min' }
    // We assume 'price' is a string like "$45.00"

    // Parse Price Breakdown (Simplified for now, as frontend sends total string)
    // Ideally frontend should send breakdown, but we can just put total in all fields or parse it if needed.
    // For now, we put total in 'total' and "-" in others to look clean, or just duplicate.
    // Actually, let's just use the Total for now.

    const receiptData = {
      customerName: data.name,
      customerEmail: data.email,
      pickup: data.pickup,
      dropoff: data.dropoff,
      date: new Date().toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' }),
      distance: data.tripDetails?.dist ? `${data.tripDetails.dist} mi` : "N/A",
      duration: data.tripDetails?.time ? `${data.tripDetails.time} min` : "N/A",
      priceCheckdown: {
        base: "-", // Frontend doesn't send breakdown yet
        mileage: "-",
        wait: "-",
        total: data.price
      },
      bookingId: Math.random().toString(36).substr(2, 9).toUpperCase()
    };

    // 1. Send Customer Receipt
    const customerResult = await sendReceiptEmail(receiptData);

    // 2. Send Admin Notification to Yourself
    const adminResult = await sendAdminNotification(receiptData);

    if (!customerResult.success && !adminResult.success) {
      console.error("❌ Both emails failed:", customerResult.error, adminResult.error);
      return NextResponse.json({ success: false, message: "Failed to send emails" }, { status: 500 });
    }

    console.log("✅ Emails Processed. Customer:", customerResult.success, "Admin:", adminResult.success);

    // 3. Sync to Summit OS Database (Azure Function)
    try {
      const functionUrl = process.env.AZURE_FUNCTION_URL + "/api/log-private-trip";
      const functionKey = process.env.AZURE_FUNCTION_KEY;

      const syncResponse = await fetch(functionUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-functions-key": functionKey || ""
        },
        body: JSON.stringify({
          ...data,
          bookingId: receiptData.bookingId
        })
      });

      if (!syncResponse.ok) {
        console.warn("⚠️ Failed to sync booking to central server:", await syncResponse.text());
      } else {
        console.log("🚀 Booking synced to Summit Command Center.");
      }
    } catch (syncError) {
      console.warn("⚠️ Error syncing booking (non-fatal):", syncError);
    }

    return NextResponse.json({ success: true, message: "Booking confirmed & Receipt Sent" });

  } catch (error) {
    console.error("❌ Server Error:", error);
    return NextResponse.json({ success: false, message: "Internal Server Error" }, { status: 500 });
  }
}
