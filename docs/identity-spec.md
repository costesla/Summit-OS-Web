# Identity spec — customer accounts (B6, design only)

**Status:** specification, not implemented. This is the keystone document for the app's next phase: three features that currently improvise around the absence of customer identity (in-app receipts, trip history, and the cabin token) converge on one identity architecture rather than each inventing its own.

**Hosting prerequisite — already satisfied:** custom OIDC on Azure Static Web Apps requires the **Standard** plan. `summitos-prod` is confirmed **Standard** (checked 2026-07-13), so this adds **no upgrade cost**.

---

## 1. Provider — Microsoft Entra External ID (custom OIDC)

Use Entra External ID (the successor to Azure AD B2C) as a **custom OpenID Connect provider** wired into the SWA's existing `/.auth/*` machinery — the same mechanism that already gates `/driver-dashboard`. No new auth stack; customers and the owner both flow through Easy Auth, distinguished by role (§4).

`staticwebapp.config.json` (additive — the file is load-bearing for the linked-backend proxy; never rewrite existing rules):

```jsonc
"auth": {
  "identityProviders": {
    "customOpenIdConnectProviders": {
      "entraExternal": {
        "registration": {
          "clientIdSettingName": "ENTRA_EXTERNAL_CLIENT_ID",
          "clientCredential": { "clientSecretSettingName": "ENTRA_EXTERNAL_CLIENT_SECRET" },
          "openIdConnectConfiguration": {
            "wellKnownOpenIdConfiguration": "https://<tenant>.ciamlogin.com/<tenant-id>/v2.0/.well-known/openid-configuration"
          }
        },
        "login": { "nameClaimType": "name", "scopes": ["openid", "profile", "email"] }
      }
    }
  }
}
```

Login/logout: `/.auth/login/entraExternal?post_login_redirect_uri=…`, `/.auth/logout`. Client id/secret live in SWA app settings, never in the repo (`security-notes.md` §3).

## 2. Sign-up / sign-in experience

- **Email one-time-passcode as the MFA factor — no SMS.** Entra External ID user flow: email + password (or email OTP passwordless), with email OTP as the second factor. Avoids SMS cost and SIM-swap risk for a consumer base that books occasionally.
- **Sign-up attributes collected:** email (identifier), display name, phone (optional, for trip contact). 
- **Marketing consent:** an explicit **unchecked-by-default** checkbox at sign-up — "Send me occasional offers and service updates." Store as a boolean user attribute; unchecked means no marketing sends. (Legal posture: opt-in, not opt-out.)

## 3. Receipts & trips API (replaces the email-only flow)

Today receipts are only emailed and there is no customer-facing list — `/api/receipt` does not exist, and the `/receipt` page is an orphan (finding C2). With identity, design these **new** endpoints, all carrying the endpoint-auth requirement in §5:

| Endpoint | Purpose |
|---|---|
| `GET /api/me/trips` | List the signed-in customer's trips (id, date, pickup→dropoff, fare, status) |
| `GET /api/me/trips/{id}/receipt` | Fetch/render a single receipt (the artifact today's email attaches) |
| `GET /api/me/profile` / `PATCH /api/me/profile` | View/update name, phone, marketing consent |

Data model: trips are already logged (`_log_trip` in `finalize_service.py`, and `log-private-trip`). Add a **customer key** — the Entra `sub` (subject) claim — to trip records at creation so trips can be queried per-customer. Historical trips predating identity won't have it; surface only post-launch trips in-app, keep email receipts for older ones. The More-tab "Trips & Receipts" placeholder (B4) becomes this list.

## 4. Roles — `rolesSource` function

SWA calls a backend **roles endpoint** after login to assign roles from claims. Add `GET /api/auth/roles` (SWA `rolesSource`) that returns:
- `owner` — when the authenticated principal matches the owner identity (email allowlist / a specific `sub`). Unlocks `/driver-dashboard`, the B5 driver notifications, and (see §6) the cabin console.
- `customer` — every other authenticated user. Unlocks `/api/me/*`.

`staticwebapp.config.json`: `"rolesSource": "/api/auth/roles"`, and route rules gate `/driver-dashboard*` on `owner` (tightening today's `authenticated`), `/api/me/*` on `customer`.

## 5. Endpoint auth requirement (from `security-notes.md` §1 — non-negotiable)

Every customer-facing endpoint here (`/api/me/*`) **carries real PII** and is reachable on the public `summitos-api` host, where `x-ms-client-principal` is forgeable. Therefore each of these endpoints **must validate the Entra-issued JWT directly inside the function** — verify **signature** (against the tenant JWKS), **issuer**, **audience**, and **expiry** — and derive the customer `sub` from the validated token, **not** from any proxy-injected header. This is the receipts API inheriting the B5 lesson on day one: proxy-header trust is acceptable only for content-free, non-sensitive actions, never for serving a customer their own data.

Implementation note: a small shared `verify_entra_jwt(req) -> claims | None` helper (JWKS cached, `PyJWT` or `msal`/`azure-identity`) used by every `/api/me/*` handler. The bearer token is the SWA-issued access token (or the Entra token) sent in `Authorization: Bearer …` by the authenticated frontend.

## 6. Cabin-token retirement path

The `/cabin` per-booking `?token=` system (and the B3 visibility lock) migrates here:
- **Owner** cabin access → gated by the `owner` role (§4), replacing the manual owner code path.
- **Passenger** cabin access for a specific trip → a signed, short-lived, trip-scoped token minted for the customer who booked it (they're now authenticated), replacing the shared 6-digit code. The token still authorizes the cabin commands, but it's bound to an identity and a trip instead of being a bearer code anyone with the link can use.
- Sequence: ship customer identity → issue trip-scoped tokens to authenticated bookers → deprecate the manual code form once no active bookings rely on it.

## 7. Rollout sequence

1. Entra External ID tenant + user flow + app registration; app settings populated.
2. `rolesSource` + role-gated routes (owner/customer).
3. `verify_entra_jwt` helper + `/api/me/*` endpoints (§5).
4. Frontend: real sign-in on More tab; "Trips & Receipts" list replaces the placeholder.
5. Cabin migration (§6).
6. Retire the orphaned `/receipt` page and the manual cabin code (cleanup phase).
