/**
 * Private Trip Receipt Engine for COS Tesla LLC
 * Main orchestrator for generating and sending business-grade passenger receipts
 */

import {
    ReceiptInput,
    ReceiptOutput,
    ReceiptError,
    InlineAttachment,
    SMTPSendBlock,
} from '@/types/receipt-types';
import { getContextualPhoto } from './google-places';
import { generateReceiptHTML, generateReceiptText } from './receipt-generator';

/**
 * Validate required fields in ReceiptInput
 */
function validateReceiptInput(input: ReceiptInput): string | null {
    const { TripData, FareData, PassengerData } = input;

    if (!TripData.Id) return 'TripData.Id is required';
    if (!TripData.DateLocal) return 'TripData.DateLocal is required';
    if (!TripData.StartTimeLocal) return 'TripData.StartTimeLocal is required';
    if (!TripData.EndTimeLocal) return 'TripData.EndTimeLocal is required';
    if (!TripData.PickupAddress) return 'TripData.PickupAddress is required';
    if (!TripData.DropoffAddress) return 'TripData.DropoffAddress is required';
    if (!FareData.Total) return 'FareData.Total is required';
    if (!PassengerData.email) return 'PassengerData.email is required';

    return null;
}

/**
 * Generate complete receipt output with SMTP send block
 * This is the main entry point for the receipt engine
 */
export async function generatePrivateTripReceipt(
    input: ReceiptInput
): Promise<ReceiptOutput | ReceiptError> {
    // Validate input
    const validationError = validateReceiptInput(input);
    if (validationError) {
        return {
            error: {
                code: 400,
                message: `Invalid ReceiptInput: ${validationError}`,
            },
        };
    }

    const { TripData, PassengerData, GeoData } = input;

    // Attempt to fetch contextual photo
    let photoBase64: string | null = null;
    let photoAttribution: string | null = null;

    try {
        const photoResult = await getContextualPhoto(
            TripData.PickupArea,
            TripData.DropoffArea,
            TripData.Pickup?.PlaceId,
            TripData.Dropoff?.PlaceId,
            GeoData
        );

        if (photoResult) {
            photoBase64 = photoResult.base64;
            photoAttribution = photoResult.attribution;
        }
    } catch (error) {
        console.warn('Failed to fetch contextual photo, proceeding without image:', error);
    }

    // Generate HTML and text bodies
    const templateData = {
        input,
        hasPhoto: !!photoBase64,
        photoAttribution: photoAttribution || undefined,
    };

    const htmlBody = generateReceiptHTML(templateData);
    const textBody = generateReceiptText(templateData);

    // Build inline attachments (only if photo available)
    const attachments: InlineAttachment[] = [];
    if (photoBase64) {
        attachments.push({
            filename: 'place.jpg',
            content_id: 'place_photo_1',
            mime_type: 'image/jpeg',
            content_base64: photoBase64,
        });
    }

    // Build SMTP send block
    const smtpPassword = process.env.PRIVATE_TRIPS_SMTP_PASSWORD;
    if (!smtpPassword) {
        return {
            error: {
                code: 500,
                message: 'SMTP configuration error: PRIVATE_TRIPS_SMTP_PASSWORD not set',
            },
        };
    }

    const sendBlock: SMTPSendBlock = {
        smtp_host: 'smtp.office365.com',
        smtp_port: 587,
        smtp_encryption: 'starttls',
        smtp_username: 'PrivateTrips@costesla.com',
        smtp_password: smtpPassword,
        from: 'SummitOS LLC — Receipts <PrivateTrips@costesla.com>',
        reply_to: 'peter.teehan@costesla.com',
        to: PassengerData.email,
        headers: {
            'List-Unsubscribe': '<mailto:peter.teehan@costesla.com?subject=unsubscribe>',
            'List-Unsubscribe-Post': 'List-Unsubscribe=One-Click',
            'X-Mailer': 'SummitOS Receipt Engine',
            'X-Sent-By': 'SummitOS LLC',
            'Content-Type': 'text/html; charset=UTF-8',
        },
        subject: `Your Private Trip Receipt — ${TripData.DateLocal}`,
        html_body: htmlBody,
        text_body: textBody,
    };

    // Add attachments only if photo exists
    if (attachments.length > 0) {
        sendBlock.attachments_inline = attachments;
    }

    // Return final output
    return {
        html: htmlBody,
        text: textBody,
        send: sendBlock,
    };
}
