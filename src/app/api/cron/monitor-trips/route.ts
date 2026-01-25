
import { NextResponse } from 'next/server';
import { TessieClient } from '@/lib/tessie';

export const dynamic = 'force-dynamic';

/**
 * CRON: Monitor Outlook Calendar & Correlate with Tessie
 * Run Frequency: Every 15 minutes (defined in vercel.json)
 */
export async function GET(request: Request) {
    // 1. Authenticate check (cron header)
    const authHeader = request.headers.get('authorization');
    if (authHeader !== `Bearer ${process.env.CRON_SECRET}` && process.env.NODE_ENV === 'production') {
        return new Response('Unauthorized', { status: 401 });
    }

    try {
        const tenantId = "1cd94367-e5ad-4827-90a9-cc4c6124a340";
        const clientId = process.env.AZURE_CLIENT_ID;
        const clientSecret = process.env.AZURE_CLIENT_SECRET;
        const tessieKey = process.env.TESSIE_API_KEY;

        if (!clientId || !clientSecret || !tessieKey) {
            console.error("Missing Environment Variables for SummitOS Outlook/Tessie Integration");
            return NextResponse.json({
                success: false,
                message: "Missing Configuration",
                missing: {
                    AZURE_CLIENT_ID: !!clientId,
                    AZURE_CLIENT_SECRET: !!clientSecret,
                    TESSIE_API_KEY: !!tessieKey
                }
            });
        }

        // 2. Microsoft Graph Auth (Client Credentials)
        // Note: For User Calendar access, this requires "Calendars.Read" Application Permission
        // OR we use a Refresh Token flow if it's a specific user. 
        // Given the script used Client Credentials, we assume App Permissions are set up.

        const tokenParams = new URLSearchParams();
        tokenParams.append('grant_type', 'client_credentials');
        tokenParams.append('scope', 'https://graph.microsoft.com/.default');
        tokenParams.append('client_id', clientId);
        tokenParams.append('client_secret', clientSecret);

        const tokenRes = await fetch(`https://login.microsoftonline.com/${tenantId}/oauth2/v2.0/token`, {
            method: 'POST',
            body: tokenParams
        });

        const tokenData = await tokenRes.json();
        const accessToken = tokenData.access_token;

        if (!accessToken) throw new Error("Failed to get MS Graph Token");

        // 3. Fetch Today's Events
        const today = new Date().toISOString().split('T')[0]; // YYYY-MM-DD
        const graphUrl = `https://graph.microsoft.com/v1.0/users/peter.teehan@costesla.com/calendar/events?$filter=start/dateTime ge '${today}T00:00:00Z'`;

        const eventsRes = await fetch(graphUrl, {
            headers: { Authorization: `Bearer ${accessToken}` }
        });
        const eventsData = await eventsRes.json();

        // 4. Fetch Tessie Location
        const vehicleVin = "5YJ3E1EA9NF288034"; // Thor (2024 Model Y)
        // For now, listing vehicles to find Thor
        const tessieRes = await fetch('https://api.tessie.com/vehicles', {
            headers: { Authorization: `Bearer ${tessieKey}` }
        });
        const tessieData = await tessieRes.json();

        // 5. Logic: Iterate events and compare with Tessie State
        const tessie = new TessieClient();
        const vehicleState = await tessie.getState();

        let logicLog: string[] = [];

        if (eventsData.value && vehicleState) {
            // const lat = vehicleState.drive_state.latitude;
            // const lng = vehicleState.drive_state.longitude;

            for (const event of eventsData.value) {
                // Check if event is "Now" (Active Trip)
                // const now = new Date(); // Use real time in prod
                // For MVP testing, we might want to log everything.
                const now = new Date();
                const start = new Date(event.start.dateTime);
                const end = new Date(event.end.dateTime);

                // If we are within the event window
                if (now >= start && now <= end) {
                    if (vehicleState.drive_state.speed > 0) {
                        // TRIP ACTIVE
                        logicLog.push(`Trip Active: ${event.subject}`);
                        // Optional: Ensure session exists or heat seats
                    }
                }

                // Check Logic: Did trip JUST finish? (End time < 15 mins ago)
                const timeDiff = (now.getTime() - end.getTime()) / (1000 * 60); // minutes since end

                if (timeDiff > 0 && timeDiff < 15) {
                    // TRIP JUST ENDED -> RESET PROTOCOL
                    logicLog.push(`Trip Finished: ${event.subject}. Executing Reset Protocol.`);

                    // 1. Reset Seats
                    await tessie.setSeatHeater('rear_left', 0);
                    await tessie.setSeatHeater('rear_right', 0);

                    // 2. Reset Windows
                    await tessie.setVentWindows('close');
                }
            }
        }

        return NextResponse.json({
            success: true,
            monitoredEvents: eventsData.value?.length || 0,
            tessieConnected: !!vehicleState,
            logicLog
        });

    } catch (error: any) {
        console.error("Cron Error:", error);
        return NextResponse.json({ success: false, error: error.message }, { status: 500 });
    }
}
