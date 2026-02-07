# Environment Variable Update - GOOGLE_MAPS_API_KEY

## ✅ Update Complete

All code and documentation has been updated to use your existing **`GOOGLE_MAPS_API_KEY`** Vercel environment variable instead of creating a new `GOOGLE_PLACES_API_KEY`.

### API Key Details

**Variable Name:** `GOOGLE_MAPS_API_KEY`  
**Value:** `AIzaSyA5xhbpf14ajrT1axR8iaMw9m2u_jpMGpE`  
**Status:** ✅ Already configured in Vercel

### Why This Works

Google Maps API keys work for **both** Google Maps AND Google Places API (New) when properly configured. Your existing key can handle:

- ✅ Google Maps JavaScript API
- ✅ Google Maps Distance Matrix API
- ✅ **Google Places API (New)** ← Used by receipt engine
- ✅ Geocoding API
- ✅ Directions API

### Files Updated

1. **`src/lib/google-places.ts`** - Changed to `process.env.GOOGLE_MAPS_API_KEY`
2. **`src/lib/receipt-combined-handler.ts`** - Changed to `process.env.GOOGLE_MAPS_API_KEY`
3. **`RECEIPT_QUICK_START.md`** - Updated examples
4. **`GRAPH_API_MIGRATION.md`** - Updated setup instructions
5. **`.env.receipt-engine.template`** - Updated with actual key value

### Required Environment Variables

For local development (`.env.local`):

```bash
# Google Maps/Places API (already in Vercel)
GOOGLE_MAPS_API_KEY=AIzaSyA5xhbpf14ajrT1axR8iaMw9m2u_jpMGpE

# Microsoft Graph API OAuth (need to add)
OAUTH_TENANT_ID=your_tenant_id_here
OAUTH_CLIENT_ID=your_client_id_here
OAUTH_CLIENT_SECRET=your_client_secret_here
```

### Vercel Deployment

**No action needed for Google Maps API** - already configured!

Only need to add Graph API credentials:

```bash
vercel env add OAUTH_TENANT_ID
vercel env add OAUTH_CLIENT_ID
vercel env add OAUTH_CLIENT_SECRET
```

### Verification

To verify the key works with Places API (New):

```bash
curl "https://places.googleapis.com/v1/places/ChIJN1t_tDeuEmsRUsoyG83frY4?fields=displayName&key=AIzaSyA5xhbpf14ajrT1axR8iaMw9m2u_jpMGpE"
```

Expected response:
```json
{
  "displayName": {
    "text": "Google Sydney",
    "languageCode": "en"
  }
}
```

If you get an error about "Places API (New) not enabled", you'll need to:

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Select your project
3. Navigate to **APIs & Services** → **Library**
4. Search for "Places API (New)"
5. Click **Enable**

### Cost Estimate

Using the same API key for both Maps and Places:

**Google Maps API (existing usage):**
- Distance Matrix, Directions, etc.

**Google Places API (New) - Receipt Engine:**
- ~$0.02-$0.056 per receipt
- 100 receipts/month = $2-$5.60
- 1000 receipts/month = $20-$56

All charges appear on the same Google Cloud billing account.

---

## Next Steps

1. ✅ **Google Maps API** - Already configured
2. ⏳ **Enable Places API (New)** - If not already enabled
3. ⏳ **Configure Graph API OAuth** - See GRAPH_API_MIGRATION.md
4. ⏳ **Test receipt generation** - Run `node test-receipt-generator.js`

---

**Status:** Ready for Graph API OAuth setup!

---

# Environment Variable Update - Power BI Intranet Dashboard

## ✅ New Configuration Required

To enable the new Intranet Dashboard with Power BI embedding, the following environment variables need to be added to your `.env.local` and Vercel project settings.

### Microsoft Entra ID (Azure AD) Details
These are required for the `AuthProvider` to sign in users.

- `NEXT_PUBLIC_AZURE_AD_CLIENT_ID`: The Application (client) ID of your Azure App Registration.
- `NEXT_PUBLIC_AZURE_AD_TENANT_ID`: The Directory (tenant) ID.

### Power BI Configuration
These are required to fetch and embed the correct report.

- `NEXT_PUBLIC_POWERBI_REPORT_ID`: The UUID of the Power BI Report you want to display.
- `NEXT_PUBLIC_POWERBI_GROUP_ID`: (Optional) The UUID of the Workspace (Group). Recommended for better performance and explicit context.

### Example `.env.local` additions

```bash
# Power BI / Azure AD Intranet Auth
NEXT_PUBLIC_AZURE_AD_CLIENT_ID=a7d212ac-dd2b-4910-a62a-b623a8ac250c
NEXT_PUBLIC_AZURE_AD_TENANT_ID=1cd94367-e5ad-4827-90a9-cc4c6124a340
NEXT_PUBLIC_POWERBI_REPORT_ID=your-report-id-guid
NEXT_PUBLIC_POWERBI_GROUP_ID=your-workspace-id-guid
```

### Reference
- **App Registration**: Ensure the registered app has "Single-page application" platform added with Redirect URI `http://localhost:3000/` (for local) and your production URL.
- **Permissions**: `User.Read` is sufficient for basic login.
