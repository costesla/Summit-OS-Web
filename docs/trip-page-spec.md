# Trip page spec — the receipt email as a live URL (B-series, design only)

**Status:** specification, not implemented. Turns today's static receipt/confirmation email into a single per-booking web page that is, in sequence, a **payment page → live trip console → permanent receipt** — one URL whose contents change with the booking's lifecycle.

**Relationship to existing code:** reuses the booking data model already written (`_log_trip` / `log-private-trip` records), the per-booking cabin token (`create_cabin_token`, valid until ~6 h after trip start), the Stripe pay-link generator (`create_stripe_payment_link`), and the comfort-only cabin commands (`/api/cabin/command`: `seat_heater`, `start_climate`/`stop_climate`, `set_temp`, `vent_windows`/`close_windows`, with venting server-blocked while moving). It **shares its data model with the owner booking-detail page** (`/driver-dashboard`) — same trip record, different projections.

---

## 1. The link — a per-booking capability URL

- **Shape:** `https://www.costesla.com/t/{token}` — `{token}` is a **long, unguessable capability token** (≥128 bits entropy, URL-safe base64, ~22+ chars), generated server-side at booking creation and stored on the trip record. This is distinct from the 6-digit cabin code: the trip page exposes payment options, contact details, and (once paid) a receipt, so it needs password-grade entropy, not a typeable code.
- **The token is the auth.** There is no login (pre-B6). Possessing the URL authorizes reading exactly one trip and acting on it. This is a bearer capability — treated like a secret in a URL, with the mitigations in §6.
- **Delivery:** the booking email links to it ("View your trip & pay") instead of embedding a Stripe button and payment instructions inline. The email becomes a thin pointer; the page is the source of truth.
- **Backend:** `GET /api/trip/{token}` → the trip projection (§5 data model). The token scopes the read; no `x-ms-client-principal` involved (capability auth, not session auth — see `security-notes.md` for why session headers aren't the model here).

## 2. Trip summary (always visible)

Route (pickup → dropoff, any stops), scheduled pickup time in local tz, passenger count, vehicle ("Tesla Model Y"), fare, and current status (`Scheduled` / `En route` / `Completed`). Read-only. This is the same summary the owner sees on the booking-detail page, minus owner-only fields (internal notes, deadhead math, margin).

## 3. Payment section (visible until paid)

Actionable payment options, each a single tap. Amount is the fare formatted to 2 decimals; the memo/note is `COS Tesla — {pickup}→{dropoff} {date}` (URL-encoded). Handles/cashtags come from owner config (app settings), never hardcoded.

**Owner payment config (app settings, to be populated):**

| Setting | Value |
|---|---|
| `ZELLE_RECIPIENT` | `peter.teehan@costesla.com` (Zelle-registered work email) |
| `VENMO_HANDLE` | `costeslallc` (profile `https://www.venmo.com/u/costeslallc`) |
| `CASHAPP_CASHTAG` | `$COSTesla` → link `https://cash.app/$COSTesla/{amount}` |
| Stripe / Cash | Stripe via existing keys; cash needs no config |

**Deep-link formats:**

| Method | Primary (mobile, opens app) | Fallback (desktop / app absent) | Note prefill? |
|---|---|---|---|
| **Venmo** | `venmo://paycharge?txn=pay&recipients=costeslallc&amount={amount}&note={note}` | `https://www.venmo.com/u/costeslallc` (profile; web prefill unreliable) | Yes (app); show handle + amount as text too |
| **Cash App** | `https://cash.app/$COSTesla/{amount}` (universal link — opens app or web, amount prefilled) | same URL renders a web pay page | **No** — cashtag URL can't carry a note; show the memo as copyable text |
| **Zelle** | *(no public deep link exists)* | Show **`peter.teehan@costesla.com`** (`ZELLE_RECIPIENT`), the **amount**, and the **memo** as three copy-to-clipboard fields + "Open your banking app to send" | N/A — honest limitation; do not fake a `zelle://` link |
| **Stripe (card/Apple Pay)** | Button → the server-generated pay link from `create_stripe_payment_link` (`https://buy.stripe.com/…`) | same URL | Handled by Stripe |
| **Cash** | Static note: "Pay the driver directly in cash — exact fare appreciated." | — | — |

Client detection: on mobile, try the app deep link (`venmo://`, and `cash.app` universal link); on desktop, show the web/URL forms. Always render the raw handle/cashtag/amount as selectable text beside each button so a failed deep link is never a dead end.

**Paid transition:** when the trip record flips to paid (Stripe webhook for card; owner marks Zelle/Venmo/Cash/CashApp received from the dashboard), the payment section **collapses to "Paid ✔ · {method} · {date}"** and the receipt (§5) becomes available.

## 4. Cabin section (activates only during the trip window)

- **Server-enforced window.** The section is inert outside the trip window and active only from shortly before pickup through the end of the ride — enforced by the backend (the existing cabin token's time-box: valid until ~6 h after trip start), **not** by client-side time checks. The page asks the server "is the cabin live for this trip right now?" and renders accordingly.
- **Time-boxed access code.** During the window, cabin control uses the booking's cabin token/code (already minted at booking time). The trip page surfaces the cabin controls inline rather than sending the passenger to `/cabin?token=`.
- **Existing allow-list only.** Exactly the set the backend already permits (`backend/api/cabin.py`): climate on/off, target temp, rear seat heaters, window vent/close (venting is server-blocked while moving) — **plus `open_trunk`**. Doors, frunk, drive, and horn are *not* exposed. The allow-list is enforced server-side; the client never widens it.
  > ⚠️ **Corrected 2026-07-15:** an earlier draft of this spec claimed "no drive, unlock, trunk, or horn." Trunk **is** allowed today — see `security-notes.md` §2a. That makes the cabin token a bearer capability for physical cargo access, which matters for how long this page keeps it live. If trunk should be tighter than comfort, gate it on the active trip window rather than the 6h token.
- **After the window:** the section deactivates automatically (token expired, server refuses commands), no matter what the client shows.

## 5. Data model & the receipt

**Shared trip record** (owner booking-detail and this page read the same row; this page gets a capability-scoped projection):

```
trip: {
  token,                       # capability token for /t/{token}  (page auth)
  cabin_token,                 # existing time-boxed cabin code    (cabin auth)
  status,                      # scheduled | en_route | completed
  customer: { name, email, phone },     # phone/email shown to the customer (their own)
  route: { pickup, stops[], dropoff },
  scheduled_pickup, tz,
  passengers, vehicle,
  fare, payment_method, payment_status, paid_at,
  receipt_ready: bool,
  cabin_window: { active: bool, opens_at, closes_at }   # server-computed
}
```

- **Receipt:** once `payment_status = paid`, the page renders the receipt (the same artifact today's paid-receipt email contains) with a print/save action. No separate `/receipt` route needed — the trip page *is* the receipt after payment. (This retires the orphaned `/receipt` Venmo form noted in the cleanup list.)

## 6. Security & privacy

- **Entropy & transport:** ≥128-bit token, HTTPS only. Brute-forcing one valid token is infeasible; still rate-limit `GET /api/trip/{token}` to blunt enumeration and log anomalies.
- **No indexing:** serve the page and endpoint with `X-Robots-Tag: noindex, nofollow` **and** a `<meta name="robots" content="noindex,nofollow">`; keep `/t/*` out of any sitemap.
- **No token leakage to payment sites:** the page must set `Referrer-Policy: no-referrer` (overriding the site's global `strict-origin-when-cross-origin` for this route) and use `rel="noopener noreferrer"` on every outbound payment link, so the capability URL never rides along in a `Referer` header to Venmo/Stripe/etc.
- **Capability scope:** the token authorizes read of one trip and the actions on this page only (payment display, and cabin comfort commands *during the window*). It grants nothing else; the cabin allow-list and window are server-enforced regardless of client.
- **PII discipline:** the page shows the customer their *own* contact details and fare — never anyone else's; the endpoint returns only the single scoped trip. No PII in query strings (token is a path segment; still treated as secret).

## 7. Lifecycle summary (one URL, four states)

1. **Unpaid, pre-trip:** trip summary + payment options prominent; cabin inert.
2. **Paid, pre-trip:** payment collapses to "Paid ✔"; receipt available; cabin inert.
3. **During trip window:** cabin section live (comfort commands); summary shows "En route".
4. **After completion:** cabin deactivates; page settles into its **permanent form — the receipt** (summary + paid receipt). The token stays valid as the durable receipt URL; only the cabin capability has expired.

## 8. B6 identity integration (forward path)

When customer accounts ship (`identity-spec.md`):
- The same trip appears under `GET /api/me/trips`, and the trip page becomes reachable **either** by capability link (unchanged, backwards-compatible) **or** by an authenticated account that owns the booking.
- `/api/trip/{token}` gains an alternative auth path: a valid Entra JWT whose `sub` matches the trip's customer key (validated in-function per `security-notes.md` §5 / `identity-spec.md` §5) authorizes the same read without the token.
- New bookings can then de-emphasize the raw capability URL in favor of "sign in to view your trips," while old links keep working. Capability tokens for cabin/window control remain as-is.

## 9. Not in scope here

Live driver-location on the trip page (that's `/track`), tipping, rebooking/repeat-trip, multi-passenger sub-links, or editing a booking from this page. Revisit after the page ships and real usage shows what's wanted.
