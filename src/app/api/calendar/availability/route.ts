import { NextResponse } from 'next/server';
import { generateTimeSlotsForDay, calculateBuffers, timeRangesOverlap } from '@/lib/calendar';

/**
 * GET /api/calendar/availability
 * Returns available time slots for a given date
 */
export async function GET(request: Request) {
    try {
        const { searchParams } = new URL(request.url);
        const dateParam = searchParams.get('date');

        if (!dateParam) {
            return NextResponse.json({ error: 'Date parameter required' }, { status: 400 });
        }

        const requestedDate = new Date(dateParam);
        if (isNaN(requestedDate.getTime())) {
            return NextResponse.json({ error: 'Invalid date format' }, { status: 400 });
        }

        // Generate all possible time slots for the day
        const allSlots = generateTimeSlotsForDay(requestedDate);

        // Get existing calendar events for the day
        const existingEvents = await getCalendarEvents(requestedDate);

        // Filter out unavailable slots
        const availableSlots = allSlots.filter(slotStart => {
            const { bufferStart, bufferEnd } = calculateBuffers(slotStart);

            // Check if this slot conflicts with any existing event
            const hasConflict = existingEvents.some((event: any) => {
                return timeRangesOverlap(
                    bufferStart,
                    bufferEnd,
                    new Date(event.start.dateTime),
                    new Date(event.end.dateTime)
                );
            });

            return !hasConflict;
        });

        return NextResponse.json({
            success: true,
            date: requestedDate.toISOString(),
            slots: availableSlots.map(slot => ({
                start: slot.toISOString(),
                end: new Date(slot.getTime() + 60 * 60000).toISOString(), // 1 hour appointment
            })),
        });

    } catch (error: any) {
        console.error('❌ Availability Error:', error);
        return NextResponse.json(
            { success: false, error: error.message },
            { status: 500 }
        );
    }
}

/**
 * Get calendar events for a specific date using Microsoft Graph
 */
async function getCalendarEvents(date: Date) {
    const tenantId = process.env.OAUTH_TENANT_ID;
    const clientId = process.env.OAUTH_CLIENT_ID;
    const clientSecret = process.env.OAUTH_CLIENT_SECRET;

    if (!tenantId || !clientId || !clientSecret) {
        throw new Error('Missing Microsoft Graph credentials');
    }

    // Get access token
    const tokenUrl = `https://login.microsoftonline.com/${tenantId}/oauth2/v2.0/token`;
    const tokenBody = new URLSearchParams({
        client_id: clientId,
        scope: 'https://graph.microsoft.com/.default',
        client_secret: clientSecret,
        grant_type: 'client_credentials',
    });

    const tokenResponse = await fetch(tokenUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: tokenBody,
    });

    const tokenData = await tokenResponse.json();
    const accessToken = tokenData.access_token;

    // Query calendar events for the day
    const startOfDay = new Date(date);
    startOfDay.setHours(0, 0, 0, 0);

    const endOfDay = new Date(date);
    endOfDay.setHours(23, 59, 59, 999);

    const calendarUrl = `https://graph.microsoft.com/v1.0/users/peter.teehan@costesla.com/calendar/calendarView?startDateTime=${startOfDay.toISOString()}&endDateTime=${endOfDay.toISOString()}`;

    const eventsResponse = await fetch(calendarUrl, {
        headers: {
            Authorization: `Bearer ${accessToken}`,
            'Content-Type': 'application/json',
        },
    });

    if (!eventsResponse.ok) {
        throw new Error(`Failed to fetch calendar events: ${eventsResponse.statusText}`);
    }

    const eventsData = await eventsResponse.json();
    return eventsData.value || [];
}
