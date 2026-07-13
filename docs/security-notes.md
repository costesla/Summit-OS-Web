# Security notes — standing constraints

Short, load-bearing security facts that outlive any single feature. Read this before adding a backend endpoint that touches PII or performs a sensitive action.

---

## 1. Do not trust proxy-injected headers as authentication (`x-ms-client-principal`)

**Constraint:** While `summitos-api.azurewebsites.net` is publicly reachable, **no endpoint may treat `x-ms-client-principal` — or any other proxy-injected header — as proof of identity for sensitive data or actions.**

**Why:**
- The frontend reaches the backend two ways: through the Azure SWA front door (`www.costesla.com/api/*`, linked-backend proxy) **and** directly from the browser to `summitos-api.azurewebsites.net` (the live map, weather, battery, flight tracker, dashboard, and booking all call the host directly — 12 call sites). The Copilot Studio agent also calls it from Microsoft's cloud. It is a **multi-consumer public API by design.**
- Through the SWA front door, `x-ms-client-principal` is trustworthy: SWA strips any client-supplied copy and injects its own after validating the Easy Auth session.
- On a **direct** request to `summitos-api.azurewebsites.net`, nothing strips or validates the header — it is just a base64 string the caller sets. **It is forgeable.**
- Because legitimate traffic arrives from end-user browsers on arbitrary IPs, there is **no "SWA-only" network boundary** that can be drawn around the host. Network access restrictions are not an available mitigation.

**Evidence (probe, 2026-07-13):** the one FUNCTION-level route already live, `log-private-trip`, returns **401 even through the SWA front door** — proving the SWA linked backend does **not** inject Azure Functions keys. So "just require a function key" is also not a drop-in fix: SWA won't supply it, and legitimate browser calls would break.

**What to do instead:**
- For endpoints that only *act on the owner's behalf with non-sensitive payloads* (e.g. push notifications), keep the payload **content-free** — carry no PII, link into an Easy-Auth-gated page for details. (This is the mitigation applied to the B5 push feature: notifications say only that a booking occurred; name/route/price live behind `/driver-dashboard`.)
- For endpoints that *serve or mutate PII* (receipts, trips, customer profile), **validate a real bearer token inside the function** — verify the Entra-issued JWT's signature, issuer, audience, and expiry. Never rely on a proxy header. See `identity-spec.md` §"Endpoint auth requirement."

## 2. Cabin access is token-based, not Easy Auth

`/cabin` authenticates with a per-booking `?token=` code (backend-issued, stored in `create_cabin_token`), not Easy Auth. The B3 owner "lock" on the tokenless entry path is a **visibility gate only** (hides the code form behind `/.auth/me`); the token remains the real authorization. Retirement path to role-based auth is in `identity-spec.md`.

## 3. Secrets never live in the repo

VAPID private key, function keys, connection strings, client secrets → Function App settings / Key Vault only. The OneDrive project root is **not** a git repo (the repo is the `Summit-OS-Web-master/` subfolder), but do not rely on that as a safety net — keep generated secret files out of the tree and delete them once vaulted.
