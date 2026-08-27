# Booking Flow Redesign — Phase 1 Codebase Audit

**Branch:** `feat/booking-multileg-final-dropoff`
**Base:** `master` @ `fcd8576` (fresh clone of `costesla/Summit-OS-Web`)
**Status:** audit only — no code written, edited, or refactored.

> **Note:** the message said the full spec, execution prompt, and checklist would
> follow. They did not arrive. This audit answers the three load-bearing
> questions and the item-4 inventory as stated; anything the spec adds beyond
> that is unaudited.

---

## a. ROUTE MODEL

### How the trip is represented today

The trip is a **flat pickup/dropoff pair plus a decorative stop count**. There is
no route array anywhere in the system.

`frontend/src/components/BookingEngine.tsx:30-34`:

```ts
const [pickup, setPickup]   = useState("");
const [dropoff, setDropoff] = useState("");
const [stopCount, setStopCount]         = useState(0);      // $5/stop, 0..5
const [stopAddresses, setStopAddresses] = useState<string[]>([]);
```

Three things matter about this shape:

1. **`stopAddresses` is optional and cosmetic.** The UI labels the fields
   "Stop Addresses *(optional)*" (`BookingEngine.tsx:268`), and the quote body
   sends `stopAddresses.length > 0 ? stopAddresses : Array(stopCount).fill('')`
   (`:83`) — i.e. a stop with no address is sent as an empty string, filtered out
   server-side, and the trip is priced as if it never existed except for the
   flat `$5 × stopCount` fee.
2. **Stops have Google Autocomplete on pickup/dropoff only.** Stop inputs are
   plain `<input>` with no `Autocomplete` wrapper (`:272-279`), so stop text is
   unvalidated free-form.
3. **Stops never reach the map or the booking.** `RouteMap` is called with
   `stops={[]}` and the comment *"Stops are now count-only; no addresses to
   display"* (`:357`). `CalendarBooking` is handed only `pickup` and `dropoff`
   (`:484-485`) — `stopAddresses` is **dropped entirely** at the hand-off to the
   booking step. Nothing downstream of the quote has ever seen a stop address.

Downstream, every consumer is a two-field pair:

| Layer | File | Shape |
|---|---|---|
| Booking UI | `CalendarBooking.tsx:13-14` | `pickup: string; dropoff: string` props |
| Unpaid POST | `CalendarBooking.tsx:232-233` | `{ pickup, dropoff }` |
| Paid POST | `CalendarBooking.tsx:270-271` | `{ pickup, dropoff }` |
| Stripe metadata | `backend/api/checkout.py:75-76` | `'pickup'`, `'dropoff'` |
| Calendar event | `backend/services/bookings.py:60-61` | `customer_data['pickup'/'dropoff']` |
| Trip DB row | `backend/services/database.py:301-302` | `Pickup_Location` / `Dropoff_Location` |

### What changes to make it `[pickup, ...stops, finalDropoff]`

The good news: **the fare path already routes an ordered sequence correctly** —
see §Fare-calc below. The ordering work is almost entirely in the UI state and
the persistence hop.

1. **`BookingEngine`** — replace `pickup`/`dropoff`/`stopCount`/`stopAddresses`
   with one ordered `legs: RoutePoint[]` (min length 2). Index `0` is the
   pickup, index `n-1` is the final drop-off, everything between is a stop. The
   `$5/stop` fee becomes `legs.length - 2`. Every stop input needs the same
   `Autocomplete` treatment pickup/dropoff already get, and stop addresses must
   become **required** — an ordered route cannot contain a blank waypoint.
2. **The quote call** (`:73-88`) already accepts `{pickup, dropoff, stops[]}` and
   Google preserves waypoint order (§Fare-calc). Mapping
   `legs → {pickup: legs[0], dropoff: legs.at(-1), stops: legs.slice(1,-1)}` is
   a pure derivation — **no backend pricing change is required for ordering**.
   Only the "blank stop still costs $5" behaviour needs a decision.
3. **`RouteMap`** already supports ordered waypoints
   (`RouteMap.tsx:98-103` → `waypoints: [{location, stopover:true}]`, and it does
   **not** pass `optimizeWaypoints`, so Google preserves order). Passing
   `stops={legs.slice(1,-1)}` instead of `[]` is a one-line change.
4. **`CalendarBooking`** — its `pickup`/`dropoff` props must become the ordered
   array (or gain a third `stops` prop) and forward it on both POST bodies.
   This is the hop where stop data is currently lost.
5. **Both backend creation paths** must carry the ordered route into the Graph
   body and the DB row (see §b, §Two surfaces).

**Cheapest correct cut:** keep `pickup` and `dropoff` on the wire as the first
and last elements (nothing downstream breaks), and add an **ordered `stops`
array** alongside them. Everything that only cares about endpoints keeps working
unchanged; only the display surfaces need to learn about the middle.

---

## b. GRAPH PAYLOAD

### Current shape

`backend/services/graph.py:120-159` — a standard **Graph Calendar `Event`**, not
a Bookings appointment. `services/bookings.py:54-55` says so explicitly:
*"Creates a new booking appointment using standard Graph Calendar API (Bypassing
Bookings API due to persistent 401 Service Principal issues)."*

```python
POST https://graph.microsoft.com/v1.0/users/{user_email}/calendar/events
{
  "subject":  "Booking: {name}",
  "body":     { "contentType": "HTML", "content": <HTML block> },
  "start":    { "dateTime": "...", "timeZone": "America/Denver" },
  "end":      { "dateTime": "...", "timeZone": "America/Denver" },
  "location": { "displayName": <pickup> },
  "categories": ["Private Trip", "SummitOS"],
  "showAs": "busy", "isReminderOn": true, "reminderMinutesBeforeStart": 30,
  "transactionId": <optional, Stripe session id — 409 on duplicate>
}
```

The route lives entirely inside the **HTML `body`** as two labelled lines
(`services/bookings.py:65-75`):

```html
<p><strong>Pickup:</strong> {pickup}</p>
<p><strong>Dropoff:</strong> {dropoff}</p>
```

and `location.displayName` is set to the pickup string (`:77`).

### Can it hold an ORDERED multi-stop route as-is? — **Yes.**

Two mechanisms in the existing payload, no schema change:

1. **`body.content` is free-form HTML.** An ordered `<ol>` of stops is a
   literal drop-in where the two `<p>` lines are today. Order is preserved by
   construction, and this is the field the owner actually reads in Outlook.
2. **Graph `Event` natively supports `locations` (plural) — an ordered array**
   of `location` objects, alongside the singular `location`. It is part of the
   same `Event` resource already being POSTed; adding it is adding a key to the
   dict at `graph.py:134`. This gives a *structured* ordered route Outlook
   renders as a location list, not just prose.

**Recommendation: use both, and do not invent a persistence schema.**
`locations[]` for structure, the HTML `<ol>` for legibility. The existing payload
is sufficient.

### The real persistence constraint is Stripe, not Graph

`backend/api/checkout.py:71-84` stuffs the whole booking into
**Stripe Checkout Session `metadata`**, and `finalize_service.py:214-226` reads
it back to build the calendar event. The paid path's booking data *only* exists
in Stripe metadata between checkout and finalize. Stripe metadata is capped at
**50 keys / 40-char keys / 500-char values**. Five autocompleted Colorado
addresses will not fit in one 500-char value.

This is the one place that genuinely needs a decision:
- serialise stops to JSON and **split across numbered keys** (`stop0`…`stop4`,
  ~14 keys free today), or
- write the route to SQL at checkout-session creation and put only a reference
  in metadata.

Note also that `metadata` has **no `stops` key at all today** — so even the
current cosmetic stop count is invisible to the paid path.

---

## c. AIRPORT DETECTION

### Does it exist? — **No. There is no airport-endpoint detection anywhere.**

Nothing in the codebase decides "this pickup/dropoff is an airport." What exists
is *downstream* airport machinery that assumes someone already decided:

| Exists | Where | What it actually does |
|---|---|---|
| Arrival hand-off state machine | `frontend/src/components/arrivalMode.ts` | Given a flight + `expectedDestination`, decides FLIGHT/LANDED/VEHICLE. Does **not** detect airports. |
| Airport **code** comparison | `arrivalMode.ts:58-61` `sameAirport()` | Compares two IATA/ICAO strings. Both must already be supplied. |
| Airport code matching (server) | `backend/services/flightaware.py:424-429` `_airport_matches()` | Matches an AeroAPI airport object against an expected code. |
| Destination guard | `flightaware.py:334-336` | Filters flight candidates by expected destination. |
| Storage columns | `database.py:1002-1007` | `Rides.CabinTokens.FlightNumber`, `.ExpectedDest`, added idempotently. |
| Fixed COS constant | `flightaware.py:38`, `flightradar24.py:45` | Hardcoded Colorado Springs ICAO for arrivals boards — not a detector. |

The only string-matching that touches the word "airport" is:
- `frontend/src/utils/distance.ts:22` — `["den","airport","dia"]`, a geocoding
  bias hint inside a **dead module** (see §Fare-calc), and
- `backend/services/ocr.py:235` — `/(Airport|DEN|DIA|MCO)/i` on scanned **Uber
  screenshots**, unrelated to bookings.

Neither is a usable endpoint detector.

### The gap is documented in the code itself

`frontend/src/app/cabin/page.tsx:216-222`:

> *"The flight number arrives on the cabin link (`?flight=DL4089`), **since a
> booking doesn't yet carry one**. When the booking↔flight linkage lands this…"*

And `docs/flight-data-spec.md:35` (status: **specification, not implemented**)
already scopes exactly this decision — and left it open:

> *"surfaced when the trip looks airport-bound (pickup or dropoff resolves to
> COS/DEN airport, **or a manual 'This is an airport pickup' toggle**)"*

**So: the source must be chosen before any arrival-workflow code is written.**
Three candidates, in order of my preference:

1. **Google Place `types`** — pickup/dropoff already go through
   `Autocomplete` (`BookingEngine.tsx:197-217`), so `place.types.includes("airport")`
   is free and works for any airport. **Blocker:** `autocompleteOptions.fields`
   (`:159`) currently requests only `["formatted_address","geometry","name"]`
   — `types` must be added, and the resolved Place must be stored in state
   (today only the address *string* survives).
2. **A small IATA allowlist** (COS, DEN, +Front Range) — trivial, no API cost,
   but silently fails outside the list.
3. **A registry/lookup service** — most robust, most work, unjustified at
   current volume.

A **manual toggle** is worth keeping regardless as the override, per the spec's
own wording — it is the only thing that handles a private-terminal or FBO pickup.

---

## 4. INVENTORY

### The two booking surfaces

Not two UIs — **two server-side creation paths**, both driven by the *same*
`CalendarBooking` component, diverging at `handleBooking(method)`
(`CalendarBooking.tsx:215`):

**Surface 1 — Unpaid (Invoice / Cash / Venmo)**
`CalendarBooking.tsx:225` → `POST /api/book` → `backend/api/bookings.py:317`
→ `BookingsClient.create_appointment()` (`bookings.py:388-405`)
Also: builds the receipt email inline, mints the cabin token (`:473`), logs the
trip, sets payment status `Pending`.

**Surface 2 — Paid (Stripe)**
`CalendarBooking.tsx:263` → `POST /api/create-checkout-session`
→ `backend/api/checkout.py` (route into Stripe metadata)
→ Stripe redirect → `/book/success` → finalize
→ `backend/services/finalize_service.py:214-226` → `BookingsClient.create_appointment()`

⚠️ **These duplicate the route-handling logic, including the return-leg
inversion** (`bookings.py:427-428` vs `finalize_service.py:252-253`, both
literally `pickup=dropoff, dropoff=pickup`). **Any route-model change must be
made in both, or paid and unpaid bookings will diverge.** There is also a third,
partial path: `api/bookings.py:80` `calendar-book`, which `finalize_service`
deliberately no longer calls (`:198-202` — it starved the Python worker) but
which is still registered and reachable.

**Dead surface:** `frontend/src/components/BookingForm.tsx` (297 lines) is
imported by **nothing** — only its CSS module is reused. It has its own
hardcoded `$30 / "Call for Quote"` pricing (`:58-59`). Confirm before touching.

### Fare-calc path

```
BookingEngine.tsx:73  fetch('/api/quote')            [500ms debounce]
  └─ SWA rewrite  frontend/public/staticwebapp.config.json:46-48
       → https://summitos-api.azurewebsites.net/api/quote
         └─ backend/api/pricing.py:18  quote()
              ├─ gmaps.directions(origin=pickup, destination=dropoff,
              │                   waypoints=valid_stops)          :40-46
              ├─ gmaps.geocode() ×2 → county (El Paso / Teller)   :116-136
              └─ services/pricing.py  PricingEngine.calculate_trip_price()
```

**Load-bearing for this redesign:** `gmaps.directions()` at `pricing.py:40-46`
does **not** pass `optimize_waypoints`. The Google client defaults it to
`False`, so **waypoint order is already preserved** and per-leg distances are
summed in order (`:55-56`). The fare engine is ordered-route-ready today. What
it lacks is per-leg output — it returns only a total (`:169-176`), so a
per-leg fare display would need new response fields.

Fare rules (`services/pricing.py`, mirrored in the dead TS): `$30` base, `$1.50/mi`
beyond 5 free miles **only when out-of-county**, `$5/stop`, `$15` Teller
surcharge, `$20/hr` wait.

**Dead code:** `frontend/src/utils/pricing.ts` — `calculateTripPrice()` and
`calculateBundlePrice()` are imported only by `test_pricing_v2.ts`.
`BookingEngine` imports **only the `PriceBreakdown` type** (`:8`). Its
`TripParams.isAirport` flag (`pricing.ts:6`) is **never read by anything** and is
not a detector. `frontend/src/utils/distance.ts` is likewise reachable only from
the dead `BookingForm`.

### FlightNumber / ExpectedDest / Rides.CabinTokens

Plumbed **end-to-end except for the one hop that fills it in.**

```
create_cabin_token(booking_id, valid_hours, expires_at,
                   flight_number=None, expected_dest=None)   database.py:959-961
  └─ single INSERT INTO Rides.CabinTokens (Token, BookingID, ExpiresAt,
                                           FlightNumber, ExpectedDest)   :1016-1025
     (columns ALTER-added idempotently, :1002-1007)
get_cabin_trip(token) → {flight_number, expected_dest}                   :1075-1082
  └─ GET /api/cabin/state → payload.flight_number / .expected_dest   api/cabin.py:335-336
     └─ cabin/page.tsx:222-223 → ArrivalMap expectedDestination
```

Covered by 9 tests in `backend/tests/test_cabin_trip.py` (single-INSERT,
normalisation, NULLs for non-airport, garbage idents survive, idempotent ALTERs,
DB-down fallback).

🔴 **Neither production caller passes them.** Both call sites omit both
arguments:
- `backend/api/bookings.py:473` — `create_cabin_token(booking_id, expires_at=token_expiry)`
- `backend/services/finalize_service.py:392` — `create_cabin_token(session.id, expires_at=token_expiry)`

So `FlightNumber` / `ExpectedDest` are **always NULL in production.** The booking
flow never captures a flight number — there is no such field in `BookingEngine`
or `CalendarBooking`. The console falls back to the hand-appended `?flight=`
URL parameter (`cabin/page.tsx:222`), defaulting `dest` to `"COS"` (`:223`).

Token lifetime is `CABIN_TOKEN_HOURS` after scheduled pickup; per
`docs/security-notes.md` §2a this token **grants trunk access** (`open_trunk` is
on the cabin allow-list), so anything that widens its window is a security
change.

### landed → Thor transition

"Thor" is the vehicle (Tesla Model Y, VIN pinned at `frontend/src/lib/tessie.ts:37`,
labelled in `LiveMap.tsx:141` and `track/page.tsx:142`).

State machine: `frontend/src/components/arrivalMode.ts` → `deriveMode()` (`:77-110`),
pure and injectable-clock, rendered by `ArrivalMap.tsx`, tested in
`arrivalMode.test.ts` / `ArrivalMap.test.tsx`.

`FLIGHT → LANDED → VEHICLE`, gated by four rules:

1. Airborne, or cancelled-and-not-on-ground → `FLIGHT` (`:87`).
2. **Diversion guard** (`:91-98`): if `expectedDestination` is set and
   `flight.landed_at` doesn't match it, or `flight.diverted`, stay on `FLIGHT`
   — never hand over to a driver at the wrong airport. Also requires `tripBound`.
3. **`ARRIVAL_SWITCH_DELAY_MIN = 15`** (`:56, :104`) — hold the flight view
   through deplaning and baggage claim. Measured from `on_ground_since`
   (real touchdown), **not** page load, so reopening the app can't restart the
   wait (`minutesSinceLanding`, `:67-73`; missing timestamp → `Infinity`, so a
   landed flight fails *open* to hand-over rather than hanging).
4. `LANDED` card shows `LANDED_CARD_MS = 5000` then auto-dissolves → `VEHICLE`
   (`ArrivalMap.tsx:149-157`, fires once per `flight_number` via `firedFor` ref).

Driver data is deliberately minutes-and-booleans only — `tessie.get_driver_dispatch()`
(`services/tessie.py:462-511`) does the airport-proximity comparison
**server-side** (`DISPATCH_MATCH_RADIUS_MI = 3.0`, sized for airport property,
`tessie.py:9-12`) so the car's nav destination — a customer's drop-off address —
never reaches the client. The card only claims an ETA the feed actually reports
(`ArrivalMap.tsx:180-182`).

⚠️ **Multi-stop relevance:** `expectedDestination` and the dispatch ETA both
assume a **single** endpoint. With `[pickup, ...stops, finalDropoff]`, "is the
driver heading to the right place" needs to mean *the current leg's* endpoint —
`heading_to_expected` will read false mid-route otherwise.

### Every customer-facing "Origin" label

Exactly **one**, and it is the field this redesign renames:

| # | Location | Text | Note |
|---|---|---|---|
| 1 | `BookingEngine.tsx:195` | `<label>Origin</label>` | 🔴 **The customer-facing label.** Its pair is `Destination` (`:288`). |

Everything else is internal or unrelated:

| Location | Occurrence | Why it's not customer-facing |
|---|---|---|
| `BookingEngine.tsx:355, 484` | `quote?.debug?.origin` | Server-validated address value, not a label |
| `BookingEngine.tsx:368` | `?origin=` | Google Maps deep-link URL param |
| `utils/pricing.ts:22` | `debug.origin` | Dead-code type field |
| `RouteMap.tsx:94-152` | `origin` | Internal Directions API variable |
| `FlightTracker.tsx:174` | `"Origin"` fallback | **Flight** origin city, not trip origin |
| `arrivalMode.ts:18`, `ArrivalMap.tsx:9` | `origin` | Flight origin airport |
| `CalendarBooking.tsx:280-281`, `create-checkout-session/route.ts:34,37` | `window.location.origin` | HTTP origin |
| `backend/api/pricing.py:61,105,127` | `actual_origin` | Server variable |

Adjacent labels the redesign will also touch: `Destination` (`:288`),
`Extra Stops` (`:236`), `Stop Addresses (optional)` (`:268`),
`Stop {n} address (optional)` (`:276`), and in `CalendarBooking` the
Pickup/Dropoff wording on the receipt emails
(`api/bookings.py:533,539`; `finalize_service.py:442,444`).

---

## Flags for the Phase 2 plan

1. **Stripe metadata is the only real persistence blocker** (§b). Graph is fine.
2. **Two creation paths must change together** or paid/unpaid bookings diverge.
3. **Airport detection source is an open decision** — must be made before any
   arrival-workflow code. My recommendation: Place `types` + manual override,
   which requires adding `types` to `autocompleteOptions.fields` and keeping the
   resolved Place in state.
4. **Stop addresses must become required.** An ordered route cannot contain a
   blank waypoint, and today they are explicitly optional and dropped at the
   `CalendarBooking` hand-off.
5. **`heading_to_expected` / `expectedDestination` are single-endpoint** and need
   a per-leg meaning under a multi-stop route.
6. **Dead code to confirm before deleting:** `BookingForm.tsx`,
   `utils/pricing.ts`, `utils/distance.ts`, and the now-unused `calendar-book`
   route.
7. **`redesign/dark-shell` is not on the remote** — only `origin/master` exists.
   If that unmerged dark redesign touches `BookingEngine`, it will conflict.
