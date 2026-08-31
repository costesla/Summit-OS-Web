---
name: godaddy-dns-automation
description: Automated GoDaddy REST API DNS administration for email deliverability (DMARC, DKIM, SPF) and domain routing using Personal Access Tokens (PAT) or sso-key.
---

# GoDaddy DNS Automation & Email Deliverability Skill

This skill provides step-by-step procedures, authentication standards, and API patterns for querying and updating GoDaddy DNS records automatically via the GoDaddy REST API.

---

## 1. Authentication Patterns

GoDaddy supports two authentication formats for its REST API (`https://api.godaddy.com`):

### Option A: Personal Access Token (PAT / v1 & v3)
```python
headers = {
    "Authorization": f"Bearer {GODADDY_PAT}",
    "Content-Type": "application/json"
}
```

### Option B: API Key and Secret (v1)
```python
headers = {
    "Authorization": f"sso-key {API_KEY}:{API_SECRET}",
    "Content-Type": "application/json"
}
```

---

## 2. Core API Endpoints

### Retrieve All DNS Records for a Domain
```http
GET https://api.godaddy.com/v1/domains/{domain}/records
```

### Retrieve Specific Record Type and Name
```http
GET https://api.godaddy.com/v1/domains/{domain}/records/{type}/{name}
```

### Replace/Update Specific Record (e.g. DMARC)
```http
PUT https://api.godaddy.com/v1/domains/{domain}/records/{type}/{name}
Content-Type: application/json

[
  {
    "data": "v=DMARC1; p=none; adkim=r; aspf=r; rua=mailto:dmarc_rua@onsecureserver.net;",
    "ttl": 600
  }
]
```

### Append/Patch New Records (e.g. DKIM CNAMEs)
```http
PATCH https://api.godaddy.com/v1/domains/{domain}/records
Content-Type: application/json

[
  {
    "type": "CNAME",
    "name": "selector1._domainkey",
    "data": "selector1-costesla-com._domainkey.costesla.onmicrosoft.com",
    "ttl": 3600
  },
  {
    "type": "CNAME",
    "name": "selector2._domainkey",
    "data": "selector2-costesla-com._domainkey.costesla.onmicrosoft.com",
    "ttl": 3600
  }
]
```

---

## 3. Email Deliverability Standards (Gmail & Yahoo Compliance)

1. **SPF Record:** Must authorize outbound transport (e.g. `include:spf.protection.outlook.com` for Microsoft 365 or `include:spf.em.secureserver.net` for GoDaddy Webmail).
2. **DMARC Policy:**
   - Use `p=none` during onboarding and DKIM stabilization.
   - Avoid `p=reject` unless all sending services are actively DKIM-signed.
3. **DKIM Alignment:**
   - Microsoft 365 requires two CNAME selectors pointing to `onmicrosoft.com` tenant selectors.
   - Once CNAMEs are active, enable DKIM signing in Microsoft Defender Security / Exchange Admin Center.

---

## 4. Verification Workflow

Always verify both API response and global DNS propagation:
```powershell
Resolve-DnsName -Name "_dmarc.{domain}" -Type TXT
Resolve-DnsName -Name "selector1._domainkey.{domain}" -Type CNAME
Resolve-DnsName -Name "selector2._domainkey.{domain}" -Type CNAME
```
