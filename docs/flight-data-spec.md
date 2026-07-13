# Flight-data spec — flight-aware bookings (B6, design only)

**Status:** specification, not implemented. Aviationstack is **already integrated** server-side (`backend/api/bookings.py` → `flight-status` route → `AviationStackClient`), and the homepage `FlightTracker` component already calls it. This spec wraps that working client behind a swappable interface and designs the booking-flow integration that's actually missing.

**Decision on record:** FlightAware (or any second provider) is **not purchased** — this is an interface + UX spec only, built so a provider swap is a one-file change.

---

## 1. Provider interface (make the existing client swappable)

Define a thin `FlightProvider` protocol and make `AviationStackClient` its first implementation — no behavior change, just an interface seam:

```python
class FlightProvider(Protocol):
    def get_flight_status(self, flight_number: str, date: str | None = None) -> FlightInfo | None: ...

@dataclass
class FlightInfo:
    flight_number: str
    status: str                 # scheduled | active | landed | cancelled | diverted
    scheduled_arrival: datetime | None
    estimated_arrival: datetime | None   # the field that actually matters for pickup timing
    origin: str | None
    destination: str | None
    gate: str | None
    provider: str               # "aviationstack" | "flightaware" — for logging/debug
```

- `AviationStackClient` adapts to this (maps its response into `FlightInfo`).
- A future `FlightAwareClient` implements the same protocol; selection via a `FLIGHT_PROVIDER` app setting (default `aviationstack`). FlightAware's AeroAPI gives more reliable `estimatedArrival` and push webhooks (§4) — the reason to keep the seam.
- `flight-status` route and any booking logic depend on `FlightProvider`, never on a concrete client.

## 2. Booking-flow field (the missing piece)

Add an **optional flight number** field to the booking flow (`CalendarBooking` / `BookingEngine`), surfaced when the trip looks airport-bound (pickup or dropoff resolves to COS/DEN airport, or a manual "This is an airport pickup" toggle):

- Input: flight number (e.g. `UA1234`), validated against the provider on blur — show airline, origin, scheduled arrival as confirmation.
- Stored on the booking so dispatch sees it.
- Errors never block booking: an unrecognized flight number warns but still lets the customer book (they may have a typo or a codeshare).

## 3. Suggest, don't move — pickup adjustment

When a tracked flight's `estimated_arrival` differs from the booked pickup time, the app **suggests** an adjustment; it never silently moves the pickup:

- Delay: "UA1234 is now landing ~40 min late (5:10 PM). Shift your pickup to ~5:40 PM?" with Accept / Keep buttons.
- Early: same pattern.
- Only the customer (or owner, dispatch-side) confirms the change. Rationale: an auto-moved pickup that's wrong is worse than a late one the customer expected — and a single-vehicle operation can't absorb surprise reschedules without the owner's say.

## 4. Freshness: polling now, webhooks later

- **v1 (Aviationstack):** poll `estimated_arrival` on a schedule for flights within a pickup window — reuse the existing timer-function pattern, poll only bookings with a flight number in the next N hours. Aviationstack has no push.
- **v2 (FlightAware):** AeroAPI **Alerts** push status changes to a webhook (`POST /api/flight-webhook`), eliminating polling and its rate cost. The `FlightProvider` seam plus a nullable `supports_webhooks()` capability lets v2 drop in without touching booking logic.

## 5. Dispatch / SummitOS exposure

- The flight number, live status, and estimated arrival appear on the owner's `/driver-dashboard` trip card and in the SummitOS operational view, so dispatch sees "flight landed / gate / ETA" without leaving the console.
- Feeds the B5 driver notification path *by reference only*: a flight-status change fires a **content-free** push ("A tracked pickup's flight status changed — tap to view") per `security-notes.md` §1 — details stay behind the authenticated dashboard.

## 6. Not in scope here

Baggage-claim timing, multi-leg itineraries, terminal-level routing, and any customer-facing flight display beyond the booking-time confirmation. Revisit after v1 ships and real airport-pickup volume justifies it.
