# Receipt Engine Quick Reference

## 🚀 Quick Start

### 1. Add Environment Variables
Add to `.env.local`:
```bash
GOOGLE_PLACES_API_KEY="your-key"
OAUTH_TENANT_ID="your-tenant-id"
OAUTH_CLIENT_ID="your-client-id"
OAUTH_CLIENT_SECRET="your-secret"
```

See `RECEIPT_ENV_SETUP.md` for detailed setup instructions.

### 2. Test the Handler
```bash
node test-receipt-handler.js
```

### 3. Use the API Endpoint
```bash
POST /api/receipt-graph
Content-Type: application/json

{
  "TripData": { ... },
  "FareData": { ... },
  "PaymentData": { ... },
  "PassengerData": { ... }
}
```

## 📁 Files Created

- `src/lib/receipt-combined-handler.ts` - Main receipt engine
- `src/app/api/receipt-graph/route.ts` - API endpoint
- `test-receipt-handler.js` - Test script
- `RECEIPT_ENV_SETUP.md` - Environment setup guide
- `sample-trip.json` - Sample data for testing

## 🔧 Architecture

**Handler Flow:**
1. Validates input data
2. Fetches Google Places photo (if available)
3. Generates HTML + text receipts
4. Acquires Microsoft Graph OAuth token
5. Sends email via Graph API
6. Returns send status + receipt content

## ⚠️ Current Status

✅ Handler implemented with full type safety  
✅ API endpoint created at `/api/receipt-graph`  
✅ Test script ready  
⚠️ **Requires OAuth credentials to test email sending**  
⚠️ **Requires Google Places API key for photos**

## 📧 Email Configuration

- **From:** PrivateTrips@costesla.com
- **Reply-To:** peter.teehan@costesla.com
- **Transport:** Microsoft Graph API
- **Features:** Inline CID images, HTML + text fallback

## 🧪 Next Steps

1. Configure Azure AD app for Microsoft Graph
2. Add environment variables
3. Run test script to verify
4. Integrate with booking flow
