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

**Named config invariant — check on every deploy, forever:** App Service Authentication must stay enabled on `summitos-api`. This one flag is what makes `x-ms-client-principal` unforgeable; if it is ever off, every header-trusting endpoint becomes spoofable everywhere, silently.

```
az webapp auth show --name summitos-api -g rg-summitos-prod --query enabled -o tsv    # must return: true
```

## 2. Cabin access is token-based, not Easy Auth

`/cabin` authenticates with a per-booking `?token=` code (backend-issued, stored in `create_cabin_token`), not Easy Auth. The B3 owner "lock" on the tokenless entry path is a **visibility gate only** (hides the code form behind `/.auth/me`); the token remains the real authorization. Retirement path to role-based auth is in `identity-spec.md`.

### 2a. The cabin allow-list is NOT comfort-only — it includes `open_trunk`

**Corrected 2026-07-15.** Earlier notes in this repo (including a previous version of this file) claimed the cabin was "comfort-only — no drive, unlock, trunk, or horn." **That was wrong and was never verified against the code.** The actual server-side allow-list (`backend/api/cabin.py`) is:

```python
ALLOWED_COMMANDS = {
    "seat_heater", "vent_windows", "close_windows",
    "start_climate", "stop_climate", "set_temp",
    "open_trunk",          # <-- physical access, not comfort
}
```

`open_trunk` calls Tessie's `activate_rear_trunk`. So **anyone holding a cabin link can open the vehicle's rear trunk**, and the token remains valid until roughly 6 hours after the trip start — i.e. after the passenger has left, while the car may be parked elsewhere carrying someone else's luggage. Links can be forwarded or screenshotted.

This may well be **deliberate** (a passenger loading bags needs the trunk), so it is documented, not removed. But treat it accurately:

- The cabin token is a **bearer capability granting physical cargo access**, not merely climate control.
- Doors, frunk, drive, and horn are genuinely **not** exposed (`open_frunk` exists in `services/tessie.py` but is absent from `ALLOWED_COMMANDS`).
- If trunk access should be time-boxed more tightly than comfort controls, that is a backend change to `cabin.py` — split the allow-list, or gate `open_trunk` on the active trip window (`services/trip_window.py`) rather than the 6h token.

## 3. Secrets never live in the repo

VAPID private key, function keys, connection strings, client secrets → Function App settings / Key Vault only. The OneDrive project root is **not** a git repo (the repo is the `Summit-OS-Web-master/` subfolder), but do not rely on that as a safety net — keep generated secret files out of the tree and delete them once vaulted.
