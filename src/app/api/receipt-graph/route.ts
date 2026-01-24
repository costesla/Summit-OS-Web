import { NextRequest, NextResponse } from 'next/server';
import handler from '@/lib/receipt-combined-handler';

// Force Node.js runtime (not Edge)
export const runtime = 'nodejs';

/**
 * POST /api/receipt-graph
 * Generates and sends a trip receipt via Microsoft Graph (Option A1)
 * 
 * This is the NEW receipt engine using:
 * - Google Places API (New) for contextual photos
 * - Microsoft Graph sendMail for delivery
 * 
 * Body: ReceiptInput (see receipt-combined-handler.ts)
 */
export async function POST(req: NextRequest) {
    try {
        const input = await req.json();

        // Validate required fields
        if (!input.TripData || !input.FareData || !input.PaymentData || !input.PassengerData) {
            return NextResponse.json(
                { error: 'Missing required fields' },
                { status: 400 }
            );
        }

        // Call receipt handler
        const result = await handler(input);

        // Check for errors
        if ('error' in result) {
            return NextResponse.json(
                { error: result.error },
                { status: result.error.code || 500 }
            );
        }

        // Return success
        return NextResponse.json({
            success: true,
            send: result.send,
            preview: {
                htmlLength: result.html.length,
                textLength: result.text.length
            }
        });

    } catch (error: any) {
        console.error('Receipt Graph API error:', error);
        console.error('Error stack:', error.stack);
        console.error('Error details:', JSON.stringify(error, null, 2));
        return NextResponse.json(
            { error: error.message || 'Internal server error', details: error.stack },
            { status: 500 }
        );
    }
}
