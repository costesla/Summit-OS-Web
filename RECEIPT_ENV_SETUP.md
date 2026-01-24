# Environment Variables for Receipt Engine

## Current Variables (from .env.local)
✅ AVIATIONSTACK_API_KEY - Present
✅ NEXT_PUBLIC_GOOGLE_MAPS_API_KEY - Present  
✅ RESEND_API_KEY - Present

## ⚠️ MISSING - Required for Receipt Handler

Add these to your `.env.local` file:

```bash
# Google Places API (New API)
GOOGLE_PLACES_API_KEY="your-google-places-api-key"

# Microsoft Graph OAuth2 (for sendMail)
OAUTH_TENANT_ID="your-azure-tenant-id"
OAUTH_CLIENT_ID="your-azure-app-client-id"
OAUTH_CLIENT_SECRET="your-azure-app-client-secret"
```

## How to Get These Values

### 1. Google Places API Key
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Enable "Places API (New)"
3. Create API key or use existing one
4. Copy the key to `GOOGLE_PLACES_API_KEY`

### 2. Microsoft Graph OAuth Credentials
1. Go to [Azure Portal](https://portal.azure.com/)
2. Navigate to "Azure Active Directory" → "App registrations"
3. Create new app or select existing
4. Copy:
   - **Directory (tenant) ID** → `OAUTH_TENANT_ID`
   - **Application (client) ID** → `OAUTH_CLIENT_ID`
5. Go to "Certificates & secrets" → "New client secret"
6. Copy the secret value → `OAUTH_CLIENT_SECRET`
7. Under "API permissions", add:
   - `Mail.Send` (Application permission)
   - Grant admin consent

### 3. Mailbox Configuration
The handler sends from `PrivateTrips@costesla.com`. Ensure:
- This mailbox exists in your Microsoft 365 tenant
- The Azure app has permission to send on behalf of this mailbox
