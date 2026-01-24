/**
 * API Endpoint: /api/receipt/generate
 * POST endpoint to generate and send private trip receipts
 */

import { NextRequest, NextResponse } from 'next/server';
import { generatePrivateTripReceipt } from '@/lib/receipt-engine';
import { sendReceiptEmailGraph } from '@/lib/receipt-graph';
import { ReceiptInput } from '@/types/receipt-types';

export async function POST(request: NextRequest) {
    try {
        // Parse request body
        const body: ReceiptInput = await request.json();

        // Generate receipt
        const result = await generatePrivateTripReceipt(body);

        // Check for validation errors
        if ('error' in result) {
            return NextResponse.json(result, { status: result.error.code });
        }

        // Send email via Microsoft Graph API
        const sendResult = await sendReceiptEmailGraph(result.send);

        if (!sendResult.success) {
            return NextResponse.json(
                {
                    error: {
                        code: 500,
                        message: `Graph API send failure: ${sendResult.error}`,
                    },
                },
                { status: 500 }
            );
        }

        // Return success response
        return NextResponse.json({
            success: true,
            messageId: sendResult.messageId,
            to: body.PassengerData.email,
            tripId: body.TripData.Id,
            hasPhoto: !!result.send.attachments_inline,
        });
    } catch (error) {
        console.error('Receipt generation error:', error);

        const errorMessage = error instanceof Error ? error.message : 'Unknown error';

        return NextResponse.json(
            {
                error: {
                    code: 500,
                    message: `Internal server error: ${errorMessage}`,
                },
            },
            { status: 500 }
        );
    }
}
