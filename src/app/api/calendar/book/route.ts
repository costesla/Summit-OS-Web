import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';
import { calculateBuffers, isWithinHours } from '@/lib/calendar';

/**
 * POST /api/calendar/book
 * Creates a calendar appointment with buffers
 */
export async function POST(request: Request) {
    try {
        const data = await request.json();
        const {
            customerName,
            customerEmail,
            customerPhone,
            pickup,
            dropoff,
            appointmentStart,
            duration = 60,
            price,
            passengers,
        } = data;

        // Validate required fields
        if (!customerName || !customerEmail || !appointmentStart || !pickup || !dropoff) {
            return NextResponse.json(
                { success: false, error: 'Missing required fields' },
                { status: 400 }
            );
        }

        const startTime = new Date(appointmentStart);

        // Validate time is within hours of operation
        if (!isWithinHours(startTime)) {
            return NextResponse.json(
                { success: false, error: 'Selected time is outside hours of operation' },
                { status: 400 }
            );
        }

        // Calculate buffer times
        const { bufferStart, appointmentEnd, bufferEnd } = calculateBuffers(startTime, duration);

        // Create calendar event via Microsoft Graph
        const calendarEvent = await createCalendarEvent({
            subject: `Private Trip: ${pickup} → ${dropoff}`,
            body: `
        <h2>Private Trip Booking</h2>
        <p><strong>Customer:</strong> ${customerName}</p>
        <p><strong>Email:</strong> ${customerEmail}</p>
        <p><strong>Phone:</strong> ${customerPhone}</p>
        <p><strong>Passengers:</strong> ${passengers}</p>
        <p><strong>Pickup:</strong> ${pickup}</p>
        <p><strong>Dropoff:</strong> ${dropoff}</p>
        <p><strong>Price:</strong> ${price}</p>
        <hr>
        <p><strong>Appointment Time:</strong> ${startTime.toLocaleString()}</p>
        <p><strong>Buffer Start (Arrival):</strong> ${bufferStart.toLocaleString()}</p>
        <p><strong>Buffer End (Break):</strong> ${bufferEnd.toLocaleString()}</p>
      `,
            start: bufferStart,
            end: bufferEnd,
            location: pickup,
            attendeeEmail: customerEmail,
            categories: ['Private Trip', 'SummitOS'],
        });

        console.log('✅ Calendar event created:', calendarEvent.id);

        return NextResponse.json({
            success: true,
            eventId: calendarEvent.id,
            appointmentStart: startTime.toISOString(),
            bufferStart: bufferStart.toISOString(),
            bufferEnd: bufferEnd.toISOString(),
        });

    } catch (error: any) {
        console.error('❌ Booking Error:', error);
        return NextResponse.json(
            { success: false, error: error.message },
            { status: 500 }
        );
    }
}

/**
 * Create calendar event via Microsoft Graph
 */
async function createCalendarEvent(details: {
    subject: string;
    body: string;
    start: Date;
    end: Date;
    location: string;
    attendeeEmail: string;
    categories: string[];
}) {
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

    // Create calendar event
    const eventUrl = 'https://graph.microsoft.com/v1.0/users/peter.teehan@costesla.com/calendar/events';

    const eventPayload = {
        subject: details.subject,
        body: {
            contentType: 'HTML',
            content: details.body,
        },
        start: {
            dateTime: details.start.toISOString(),
            timeZone: 'America/Denver',
        },
        end: {
            dateTime: details.end.toISOString(),
            timeZone: 'America/Denver',
        },
        location: {
            displayName: details.location,
        },
        attendees: [
            {
                emailAddress: {
                    address: details.attendeeEmail,
                },
                type: 'required',
            },
        ],
        categories: details.categories,
        showAs: 'busy',
        isReminderOn: true,
        reminderMinutesBeforeStart: 30,
    };

    const eventResponse = await fetch(eventUrl, {
        method: 'POST',
        headers: {
            Authorization: `Bearer ${accessToken}`,
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(eventPayload),
    });

    if (!eventResponse.ok) {
        const errorData = await eventResponse.json();
        throw new Error(`Failed to create calendar event: ${JSON.stringify(errorData)}`);
    }

    return await eventResponse.json();
}
