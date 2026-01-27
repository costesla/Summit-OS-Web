import { NextRequest, NextResponse } from 'next/server';
import handler from '@/lib/receipt-combined-handler';

// Force Node.js runtime (not Edge)
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

/**
 * POST /api/receipt-graph
 * Generates and sends a trip receipt via Microsoft Graph
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
                { error: (result as any).error },
                { status: (result as any).error.code || 500 }
            );
        }

        // Return success
        return NextResponse.json({
            success: true,
            send: (result as any).send,
            preview: {
                htmlLength: (result as any).html.length,
                textLength: (result as any).text.length
            }
        });

    } catch (error: any) {
        console.error('Receipt Graph API error:', error);
        return NextResponse.json(
            { error: error.message || 'Internal server error' },
            { status: 500 }
        );
    }
}
