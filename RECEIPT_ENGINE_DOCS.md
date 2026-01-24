# Private Trip Receipt Engine - Documentation

## Overview

The Private Trip Receipt Engine is a production-ready system for generating and sending business-grade passenger receipts for COS Tesla LLC private trips. It integrates with Google Places API (New) for contextual imagery and uses authenticated SMTP via Microsoft 365.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    API Endpoint                              │
│              /api/receipt/generate (POST)                    │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                  Receipt Engine                              │
│         (receipt-engine.ts)                                  │
│  • Validates input                                           │
│  • Orchestrates photo fetch                                  │
│  • Generates HTML/text                                       │
│  • Builds SMTP send block                                    │
└──────┬──────────────────────────┬──────────────────────┬────┘
       │                          │                      │
       ▼                          ▼                      ▼
┌─────────────┐         ┌──────────────────┐    ┌──────────────┐
│   Google    │         │     Receipt      │    │     SMTP     │
│   Places    │         │    Generator     │    │    Sender    │
│             │         │                  │    │              │
│ • Details   │         │ • HTML Template  │    │ • Nodemailer │
│ • Search    │         │ • Text Template  │    │ • Office 365 │
│ • Photos    │         │ • Inline CSS     │    │ • Inline CID │
└─────────────┘         └──────────────────┘    └──────────────┘
```

## Files Created

### Core Library Files

1. **`src/types/receipt-types.ts`**
   - TypeScript interfaces for all data structures
   - `ReceiptInput`, `TripData`, `FareData`, `PaymentData`, etc.
   - Google Places API response types
   - SMTP send block types

2. **`src/lib/google-places.ts`**
   - Google Places API (New) integration
   - `getPlaceDetails(placeId)` - Fetch place with photos
   - `searchPlaceByText(query, geo?)` - Text search with location bias
   - `getPhotoMedia(photoName)` - Retrieve base64 JPEG
   - `getContextualPhoto(...)` - Smart photo selection

3. **`src/lib/receipt-generator.ts`**
   - HTML and text template generators
   - `generateReceiptHTML(data)` - Outlook-compatible HTML
   - `generateReceiptText(data)` - Plain text fallback
   - Inline CSS, table-based layout, mobile-first

4. **`src/lib/receipt-engine.ts`**
   - Main orchestrator
   - `generatePrivateTripReceipt(input)` - Entry point
   - Input validation
   - Photo fetching with graceful fallback
   - SMTP block construction

5. **`src/lib/receipt-smtp.ts`**
   - Email delivery via nodemailer
   - `sendReceiptEmail(sendBlock)` - SMTP send
   - Microsoft 365 configuration
   - Inline attachment handling

### API Endpoint

6. **`src/app/api/receipt/generate/route.ts`**
   - POST endpoint `/api/receipt/generate`
   - Request validation
   - Error handling (400, 500)
   - Success response with message ID

### Testing

7. **`test-receipt-generator.js`**
   - Sample trip data
   - End-to-end test script
   - Run with: `node test-receipt-generator.js`

## Environment Variables

Add these to `.env.local`:

```bash
# Google Places API (New) - Required for contextual imagery
GOOGLE_PLACES_API_KEY=your_google_places_api_key_here

# Private Trips SMTP - Required for email delivery
PRIVATE_TRIPS_SMTP_PASSWORD=your_app_password_here
```

### Getting Google Places API Key

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create or select a project
3. Enable **Places API (New)**
4. Create API key in Credentials
5. Restrict key to Places API (New) only
6. Add to `.env.local`

**Cost Estimate:** ~$0.02-$0.056 per receipt

### Getting SMTP App Password

1. Go to [Microsoft Account Security](https://account.microsoft.com/security)
2. Sign in as `PrivateTrips@costesla.com`
3. Navigate to **Security** → **Advanced security options**
4. Under **App passwords**, create new password
5. Label it "SummitOS Receipt Engine"
6. Copy the generated password to `.env.local`

## API Usage

### Request Format

**Endpoint:** `POST /api/receipt/generate`

**Headers:**
```
Content-Type: application/json
```

**Body:**
```json
{
  "TripData": {
    "Id": "PT-20260120-072315",
    "DateLocal": "Mon, Jan 20, 2026",
    "StartTimeLocal": "7:23 AM",
    "EndTimeLocal": "7:43 AM",
    "PickupArea": "Northgate (near Voyager Pkwy)",
    "DropoffArea": "Banning Lewis Ranch",
    "PickupAddress": "1234 Example St, Colorado Springs, CO 80907",
    "DropoffAddress": "9876 Sample Ave, Colorado Springs, CO 80920",
    "Distance": { "mi": 15.54 },
    "Duration": { "min": 20 },
    "Notes": "Optional trip notes",
    "Pickup": { "PlaceId": "" },
    "Dropoff": { "PlaceId": "" }
  },
  "FareData": {
    "Base": "20.00",
    "TimeDistance": "5.50",
    "Extras": "0.00",
    "Discount": "2.50",
    "Subtotal": "23.00",
    "Tax": "1.84",
    "Tip": "5.00",
    "Total": "29.84"
  },
  "PaymentData": {
    "Method": "Venmo",
    "Last4": "1234",
    "AuthCode": "PRVT-OK-7A23"
  },
  "PassengerData": {
    "firstName": "Alex",
    "email": "alex@example.com"
  },
  "GeoData": {
    "city": "Colorado Springs",
    "region": "CO",
    "country": "US",
    "lat": 38.8339,
    "lng": -104.8214
  },
  "Now": { "Year": 2026 }
}
```

### Response Format

**Success (200):**
```json
{
  "success": true,
  "messageId": "<smtp-message-id>",
  "to": "alex@example.com",
  "tripId": "PT-20260120-072315",
  "hasPhoto": true
}
```

**Validation Error (400):**
```json
{
  "error": {
    "code": 400,
    "message": "Invalid ReceiptInput: TripData.PickupAddress is required"
  }
}
```

**Server Error (500):**
```json
{
  "error": {
    "code": 500,
    "message": "SMTP send failure: Authentication failed"
  }
}
```

## Business Requirements

### What's Included in Receipts

✅ **Passenger Information:**
- First name only (optional, for greeting)
- Email address (for delivery)

✅ **Trip Details:**
- Trip ID
- Date and time span
- **Full pickup street address** (required for tax/reimbursement)
- **Full dropoff street address** (required for tax/reimbursement)
- Distance (miles)
- Duration (minutes)
- Optional notes

✅ **Fare Breakdown:**
- Base fare
- Time & distance charges
- Extras (tolls, parking)
- Discounts (if applicable)
- Subtotal
- Tax
- Tip
- **Total** (prominently displayed)

✅ **Payment Information:**
- Payment method
- Last 4 digits (if available)
- Authorization code

✅ **Contextual Imagery:**
- Google Places photo (pickup or dropoff area)
- Attribution text (required by Google)

❌ **Excluded (Internal Only):**
- Internal operational metrics (SOC, energy, platform cut)
- Offer card details
- Driver information
- Full passenger names (last name)

### Privacy Separation

**Passenger Receipts (this system):**
- Official business documents
- Include full addresses for tax/reimbursement
- Include passenger first name
- Suitable for accounting, expense reports, IRS

**Internal SummitOS Logs:**
- Use redacted areas only (e.g., "Northgate area")
- No full addresses
- Operational data only

## Testing

### Local Testing

1. **Start development server:**
   ```bash
   npm run dev
   ```

2. **Run test script:**
   ```bash
   node test-receipt-generator.js
   ```

3. **Check email:**
   - Verify receipt arrives at test email
   - Confirm inline image displays
   - Check attribution text
   - Verify full addresses present

### Manual API Testing

Using curl:
```bash
curl -X POST http://localhost:3000/api/receipt/generate \
  -H "Content-Type: application/json" \
  -d @sample-trip.json
```

Using Postman:
1. Create POST request to `http://localhost:3000/api/receipt/generate`
2. Set body to raw JSON
3. Paste sample trip data
4. Send request
5. Check response and email inbox

## Error Handling

The system handles errors gracefully:

1. **Missing Google API Key:**
   - Proceeds without photo
   - Sends receipt with text only
   - Logs warning

2. **Google Places API Failure:**
   - Proceeds without photo
   - Sends receipt with text only
   - Logs error details

3. **Missing SMTP Password:**
   - Returns 500 error
   - Does not attempt to send
   - Clear error message

4. **SMTP Send Failure:**
   - Returns 500 error with details
   - Logs full error for debugging
   - Includes authentication/connection errors

5. **Invalid Input:**
   - Returns 400 error
   - Specifies which field is missing
   - Does not attempt generation

## Email Compatibility

The HTML template is designed for maximum compatibility:

✅ **Tested with:**
- Gmail (web, mobile)
- Outlook (desktop, web, mobile)
- Apple Mail (macOS, iOS)
- Yahoo Mail
- ProtonMail

✅ **Features:**
- Inline CSS only (no external stylesheets)
- Table-based layout (Outlook/Word rendering engine)
- Mobile-first responsive design
- UTF-8 character encoding
- Plain text fallback
- Proper MIME multipart structure

## Support

For issues or questions:
- **Support Email:** peter.teehan@costesla.com
- **System:** SummitOS Receipt Engine
- **Provider:** COS Tesla LLC

## License

Proprietary - COS Tesla LLC © 2026
