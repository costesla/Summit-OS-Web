import { NextResponse } from 'next/server';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function POST(req: Request) {
    try {
        const input = await req.json();

        // Test environment variables
        const envCheck = {
            GOOGLE_PLACES_API_KEY: !!process.env.GOOGLE_PLACES_API_KEY,
            OAUTH_TENANT_ID: !!process.env.OAUTH_TENANT_ID,
            OAUTH_CLIENT_ID: !!process.env.OAUTH_CLIENT_ID,
            OAUTH_CLIENT_SECRET: !!process.env.OAUTH_CLIENT_SECRET,
        };

        return NextResponse.json({
            success: true,
            message: 'Test endpoint working',
            envCheck,
            receivedData: {
                tripId: input.TripData?.Id,
                email: input.PassengerData?.email
            }
        });

    } catch (error: any) {
        return NextResponse.json(
            { error: error.message, stack: error.stack },
            { status: 500 }
        );
    }
}
