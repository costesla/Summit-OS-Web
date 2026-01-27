/**
 * TypeScript types for SummitOS LLC Private Trip Receipt System
 * These types match the ReceiptInput JSON contract for generating
 * business-grade passenger receipts with full addresses.
 */

export interface TripData {
    Id: string;
    DateLocal: string;
    StartTimeLocal: string;
    EndTimeLocal: string;
    PickupArea: string;
    DropoffArea: string;
    PickupAddress: string;  // Full street address (required for PAX receipts)
    DropoffAddress: string; // Full street address (required for PAX receipts)
    Distance: {
        mi: number;
    };
    Duration: {
        min: number;
    };
    Notes?: string;
    Pickup?: {
        PlaceId?: string;
    };
    Dropoff?: {
        PlaceId?: string;
    };
}

export interface FareData {
    Base: string;
    TimeDistance: string;
    Extras: string;
    Discount: string;
    Subtotal: string;
    Tax: string;
    Tip: string;
    Total: string;
}

export interface PaymentData {
    Method: string;
    Last4?: string;
    AuthCode: string;
}

export interface PassengerData {
    firstName?: string; // First name only (optional)
    email: string;
}

export interface GeoData {
    city: string;
    region: string;
    country: string;
    lat: number;
    lng: number;
}

export interface ReceiptInput {
    TripData: TripData;
    FareData: FareData;
    PaymentData: PaymentData;
    PassengerData: PassengerData;
    GeoData?: GeoData;
    Now?: {
        Year: number;
    };
}

// Google Places API response types
export interface PlacePhoto {
    name: string;
    widthPx: number;
    heightPx: number;
    authorAttributions: Array<{
        displayName: string;
        uri?: string;
        photoUri?: string;
    }>;
}

export interface PlaceDetails {
    displayName?: {
        text: string;
        languageCode: string;
    };
    photos?: PlacePhoto[];
    attributions?: string[];
}

export interface PlaceSearchResult {
    places: Array<{
        id: string;
        displayName?: {
            text: string;
            languageCode: string;
        };
        photos?: PlacePhoto[];
    }>;
}

export interface PhotoMediaResult {
    photoUri: string;
}

// Email generation types
export interface InlineAttachment {
    filename: string;
    content_id: string;
    mime_type: string;
    content_base64: string;
}

export interface SMTPSendBlock {
    smtp_host: string;
    smtp_port: number;
    smtp_encryption: string;
    smtp_username: string;
    smtp_password: string;
    from: string;
    reply_to: string;
    to: string;
    headers: {
        'List-Unsubscribe': string;
        'List-Unsubscribe-Post': string;
        'X-Mailer': string;
        'X-Sent-By': string;
        'Content-Type': string;
    };
    subject: string;
    html_body: string;
    text_body: string;
    attachments_inline?: InlineAttachment[];
}

export interface ReceiptOutput {
    html: string;
    text: string;
    send: SMTPSendBlock;
}

export interface ReceiptError {
    error: {
        code: number;
        message: string;
    };
}
