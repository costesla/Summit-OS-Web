# Skill: Microsoft Graph Mail Dispatch (`microsoft-graph-mail-dispatch`)

A specialized operational skill and architectural reference for sending transactional and executive emails with attachments via Microsoft Graph API using Azure App Registrations and Client Credentials flow.

---

## 1. Overview & Authentication Architecture

Microsoft Graph API requires specific application-level permissions and exact JSON payload structures when sending unattended server-to-server emails from serverless environments (e.g., Azure Functions).

### Identity & OAuth Setup
* **Flow**: OAuth 2.0 Client Credentials Grant (`grant_type=client_credentials`).
* **Endpoint**: `https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token`
* **Scope**: `https://graph.microsoft.com/.default`
* **Required Permission**: `Mail.Send` (Application permission type, granted by Tenant Admin).
* **Target Endpoint**: `POST https://graph.microsoft.com/v1.0/users/{from_email}/sendMail`

> [!IMPORTANT]
> When using `Mail.Send` application permissions, the application can **send** on behalf of any tenant mailbox, but **cannot read** `SentItems` unless `Mail.Read.All` is also granted. Do not attempt `GET /mailFolders/SentItems/messages` without `Mail.Read.All` permissions.

---

## 2. Strict Payload Schema Guidelines

Microsoft Graph's `sendMail` endpoint is strictly typed. Any malformed property causes an immediate `HTTP 400 RequestBodyRead` error.

### Correct JSON Payload Structure
```json
{
  "message": {
    "subject": "Executive Briefing - September 6, 2026",
    "body": {
      "contentType": "HTML",
      "content": "<html><body>...</body></html>"
    },
    "toRecipients": [
      { "emailAddress": { "address": "primary@client.com" } }
    ],
    "ccRecipients": [
      { "emailAddress": { "address": "audit@costesla.com" } }
    ],
    "replyTo": [
      { "emailAddress": { "address": "support@costesla.com" } }
    ],
    "internetMessageHeaders": [
      { "name": "X-Mailer", "value": "SummitOS Dispatch Engine" }
    ],
    "attachments": [
      {
        "@odata.type": "#microsoft.graph.fileAttachment",
        "name": "Report-2026-09-06.pdf",
        "contentType": "application/pdf",
        "contentBytes": "<BASE64_STRING>"
      }
    ]
  },
  "saveToSentItems": true
}
```

### Critical Rules:
1. **`saveToSentItems` Placement**: Must reside at the **root** of the payload object alongside `"message"`. Placing `saveToSentItems` inside `"message"` will throw `400 RequestBodyRead: The property 'saveToSentItems' does not exist on type 'microsoft.graph.message'`.
2. **Boolean Type**: `saveToSentItems` accepts boolean `true`/`false` or string `"true"`/`"false"`.
3. **Recipient Formats**: Every recipient in `toRecipients`, `ccRecipients`, `bccRecipients`, and `replyTo` must be wrapped in `{"emailAddress": {"address": "user@example.com"}}`.

---

## 3. Base64 Attachment Encoding Pattern

When attaching dynamically generated PDFs or ledgers:

```python
import base64
import os

attachments = []
if pdf_path and os.path.exists(pdf_path):
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()
    pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")
    filename = os.path.basename(pdf_path)
    
    attachments.append({
        "@odata.type": "#microsoft.graph.fileAttachment",
        "name": filename,
        "contentType": "application/pdf",
        "contentBytes": pdf_base64
    })

message_obj["attachments"] = attachments
```

---

## 4. Diagnostics & Live Verification CLI

To quickly verify tenant connectivity, token health, and send capability from the terminal:

```powershell
python -c "
import requests

tenant_id = '1cd94367-e5ad-4827-90a9-cc4c6124a340'
client_id = '3908fbac-03a0-4670-acf9-3bb24188747b'
client_secret = 'YOUR_SECRET'
from_email = 'peter.teehan@costesla.com'

token_resp = requests.post(
    f'https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token',
    data={
        'client_id': client_id,
        'scope': 'https://graph.microsoft.com/.default',
        'client_secret': client_secret,
        'grant_type': 'client_credentials'
    }
)
token = token_resp.json().get('access_token')

url = f'https://graph.microsoft.com/v1.0/users/{from_email}/sendMail'
payload = {
    'message': {
        'subject': 'Graph Diagnostic Ping',
        'body': {'contentType': 'Text', 'content': 'Direct diagnostic test.'},
        'toRecipients': [{'emailAddress': {'address': from_email}}]
    },
    'saveToSentItems': True
}
resp = requests.post(url, headers={'Authorization': f'Bearer {token}'}, json=payload)
print('HTTP Status:', resp.status_code)
"
```
- A successful dispatch returns `HTTP 202 Accepted` with an empty response body.
