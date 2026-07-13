# Security notes — standing constraints

Short, load-bearing security facts that outlive any single feature. Read this before adding a backend endpoint that touches PII or performs a sensitive action.

---

## 1. `x-ms-client-principal` — trustworthy TODAY only because Easy Auth is enabled; do not depend on it alone for PII

This section was revised 2026-07-13 after a live probe corrected an earlier assumption.

**What we assumed:** that on a direct request to `summitos-api.azurewebsites.net`, a client could forge `x-ms-client-principal` and impersonate the owner.

**What the probe showed:** App Service Authentication **is enabled** on `summitos-api` (`az webapp auth show` → `enabled: true`). With Easy Auth on, the Azure platform **strips client-supplied `x-ms-client-principal` (and related reserved headers) from inbound requests** before they reach function code. Verified: a forged principal header sent directly to `https://summitos-api.azurewebsites.net/api/push/subscribe` returns **401** (the function never sees it), while anonymous routes like `vehicle-location` still return 200 (host reachable). Through the SWA front door a forged header is likewise stripped → 401.

**So the push endpoints' header check is a valid gate as currently deployed** — the platform guarantees the header is present only when a request is genuinely authenticated, on both the front door and the direct host.

**But the safety rests entirely on a platform config that lives outside the code.** If App Service Authentication is ever disabled on `summitos-api` (config drift, a migration, a new slot), every endpoint that trusts the header silently becomes spoofable — with no code change to signal it. Treat that as the standing risk.

**Rules that follow:**
- The multi-consumer reality still holds: the frontend calls `summitos-api` directly from the browser (12 call sites: map, weather, battery, flight, dashboard, booking) and Copilot Studio calls it from Microsoft's cloud, so there is **no "SWA-only" network boundary** and network access restriction is not a mitigation. (Also confirmed: SWA does **not** inject Azure Functions keys — the live FUNCTION-level route `log-private-trip` 401s even through the front door — so "require a function key" is not a drop-in fix either.)
- For actions with **non-sensitive payloads** (e.g. push), keep the payload **content-free** regardless — carry no PII, link into an Easy-Auth-gated page for details. This is defense-in-depth that survives the config-drift risk above. (Applied to B5 push: notifications say only that a booking occurred; name/route/price stay behind `/driver-dashboard`.)
- For endpoints that **serve or mutate PII** (receipts, trips, profile), **validate a real bearer token inside the function** — verify the Entra JWT's signature, issuer, audience, expiry — and do **not** rely solely on the platform stripping the header. This removes the config-drift dependency for the endpoints that matter most. See `identity-spec.md` §5.

## 2. Cabin access is token-based, not Easy Auth

`/cabin` authenticates with a per-booking `?token=` code (backend-issued, stored in `create_cabin_token`), not Easy Auth. The B3 owner "lock" on the tokenless entry path is a **visibility gate only** (hides the code form behind `/.auth/me`); the token remains the real authorization. Retirement path to role-based auth is in `identity-spec.md`.

## 3. Secrets never live in the repo

VAPID private key, function keys, connection strings, client secrets → Function App settings / Key Vault only. The OneDrive project root is **not** a git repo (the repo is the `Summit-OS-Web-master/` subfolder), but do not rely on that as a safety net — keep generated secret files out of the tree and delete them once vaulted.
