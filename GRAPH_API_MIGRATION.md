# Graph API Migration Guide

## Why Microsoft Graph API?

The receipt engine now uses **Microsoft Graph API** instead of SMTP for email delivery. This provides several advantages:

### Benefits of Graph API

✅ **Better Microsoft 365 Integration**
- Native Microsoft 365 API
- No SMTP port/firewall issues
- Automatic retry and delivery handling

✅ **Enhanced Security**
- OAuth 2.0 client credentials flow
- No password storage (uses client secret)
- Application-level permissions

✅ **Improved Reliability**
- 202 Accepted response (async processing)
- Automatic saving to Sent Items
- Better error reporting

✅ **Advanced Features**
- Rich internet message headers
- Inline attachments with CID
- HTML + plain text multipart

---

## Setup Instructions

### 1. Azure AD App Registration

1. Go to [Azure Portal](https://portal.azure.com)
2. Navigate to **Azure Active Directory** → **App registrations**
3. Click **New registration**
   - Name: "SummitOS Receipt Engine"
   - Supported account types: "Accounts in this organizational directory only"
   - Redirect URI: (leave blank)
4. Click **Register**

### 2. Note Credentials

After registration, copy these values:

- **Application (client) ID** → `OAUTH_CLIENT_ID`
- **Directory (tenant) ID** → `OAUTH_TENANT_ID`

### 3. Create Client Secret

1. In your app registration, go to **Certificates & secrets**
2. Click **New client secret**
   - Description: "Receipt Engine Secret"
   - Expires: 24 months (or custom)
3. Click **Add**
4. **IMMEDIATELY COPY** the secret value → `OAUTH_CLIENT_SECRET`
   - ⚠️ You cannot view this again!

### 4. Grant API Permissions

1. In your app registration, go to **API permissions**
2. Click **Add a permission**
3. Select **Microsoft Graph**
4. Select **Application permissions**
5. Search for and add: **Mail.Send**
6. Click **Add permissions**
7. Click **Grant admin consent for [Your Organization]**
   - ✅ Status should show green checkmark

### 5. Configure Environment Variables

Add to `.env.local`:

```bash
# Google Maps/Places API (existing Vercel variable)
GOOGLE_MAPS_API_KEY=your_google_maps_api_key_here

# Microsoft Graph API OAuth
OAUTH_TENANT_ID=your_tenant_id_here
OAUTH_CLIENT_ID=your_client_id_here
OAUTH_CLIENT_SECRET=your_client_secret_here
```

---

## Implementation Options

You have **two implementation options**:

### Option 1: Modular Approach (Recommended)

Uses separate modules for better maintainability:

**Files:**
- `src/lib/google-places.ts` - Google Places integration
- `src/lib/receipt-generator.ts` - HTML/text templates
- `src/lib/receipt-engine.ts` - Main orchestrator
- `src/lib/receipt-graph.ts` - Graph API sender
- `src/app/api/receipt/generate/route.ts` - API endpoint

**Benefits:**
- Easier to test individual components
- Better code organization
- Reusable modules

### Option 2: Combined Handler

Single file with all logic:

**File:**
- `src/lib/receipt-combined-handler.ts` - All-in-one handler

**Benefits:**
- Simpler deployment
- Fewer dependencies
- Easier to understand flow

**Usage:**
```typescript
import { generateAndSendReceipt } from '@/lib/receipt-combined-handler';

const result = await generateAndSendReceipt(receiptInput);
```

---

## API Comparison

### SMTP (Old)

```typescript
// Required env vars
PRIVATE_TRIPS_SMTP_PASSWORD=app_password

// Limitations
- Requires App Password (MFA complexity)
- Port 587 firewall issues
- No automatic Sent Items
- Manual retry logic needed
```

### Graph API (New)

```typescript
// Required env vars
OAUTH_TENANT_ID=tenant_id
OAUTH_CLIENT_ID=client_id
OAUTH_CLIENT_SECRET=client_secret

// Advantages
- OAuth 2.0 (no passwords)
- No firewall issues (HTTPS only)
- Automatic Sent Items
- Built-in retry/delivery
```

---

## Testing

### 1. Verify OAuth Setup

```bash
# Test token acquisition
curl -X POST "https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token" \
  -d "client_id={CLIENT_ID}" \
  -d "client_secret={CLIENT_SECRET}" \
  -d "scope=https://graph.microsoft.com/.default" \
  -d "grant_type=client_credentials"
```

Expected response:
```json
{
  "token_type": "Bearer",
  "expires_in": 3599,
  "access_token": "eyJ0eXAiOiJKV1QiLCJub..."
}
```

### 2. Test Receipt Generation

```bash
npm run dev
node test-receipt-generator.js
```

### 3. Verify Email Delivery

1. Check recipient inbox
2. Verify sender: "PrivateTrips@costesla.com"
3. Confirm inline image displays
4. Check Sent Items in PrivateTrips mailbox

---

## Troubleshooting

### "Invalid client secret"

- Client secret expired or incorrect
- Generate new secret in Azure Portal
- Update `OAUTH_CLIENT_SECRET` in `.env.local`

### "Insufficient privileges"

- Mail.Send permission not granted
- Admin consent not provided
- Grant admin consent in Azure Portal

### "Mailbox not found"

- Sender email doesn't exist
- Check `PrivateTrips@costesla.com` mailbox exists
- Verify mailbox is licensed

### "Token acquisition failed"

- Tenant ID incorrect
- Client ID incorrect
- Check credentials in Azure Portal

---

## Migration Checklist

If migrating from SMTP to Graph API:

- [ ] Create Azure AD app registration
- [ ] Note tenant ID, client ID
- [ ] Create client secret
- [ ] Grant Mail.Send permission
- [ ] Grant admin consent
- [ ] Add OAuth env vars to `.env.local`
- [ ] Remove `PRIVATE_TRIPS_SMTP_PASSWORD`
- [ ] Test token acquisition
- [ ] Test receipt generation
- [ ] Verify email delivery
- [ ] Check Sent Items
- [ ] Update production environment variables

---

## Production Deployment

### Vercel

```bash
# Add environment variables (GOOGLE_MAPS_API_KEY already exists)
vercel env add OAUTH_TENANT_ID
vercel env add OAUTH_CLIENT_ID
vercel env add OAUTH_CLIENT_SECRET

# Deploy
vercel --prod
```

### Other Platforms

Ensure these environment variables are set:
- `OAUTH_TENANT_ID`
- `OAUTH_CLIENT_ID`
- `OAUTH_CLIENT_SECRET`
- `GOOGLE_MAPS_API_KEY` (already configured)

---

## Security Best Practices

✅ **Client Secret Rotation**
- Rotate secrets every 6-12 months
- Use Azure Key Vault for production
- Never commit secrets to git

✅ **Least Privilege**
- Only grant Mail.Send permission
- Don't grant User.Read or other unnecessary permissions
- Use application permissions (not delegated)

✅ **Monitoring**
- Monitor token acquisition failures
- Track email delivery success rate
- Alert on permission errors

---

## Support

**Documentation:**
- [Microsoft Graph sendMail API](https://learn.microsoft.com/en-us/graph/api/user-sendmail)
- [Azure AD App Registration](https://learn.microsoft.com/en-us/azure/active-directory/develop/quickstart-register-app)
- [OAuth 2.0 Client Credentials](https://learn.microsoft.com/en-us/azure/active-directory/develop/v2-oauth2-client-creds-grant-flow)

**Contact:**
- Email: peter.teehan@costesla.com
- System: SummitOS Receipt Engine
