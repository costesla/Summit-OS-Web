# Return-trip engine — repository findings (deliverable 1)

**Branch:** `feat/booking-multileg-final-dropoff` (Phase 2 work is in this tree, uncommitted)
**Scope of this document:** step 1 of the approved implementation prompt — inspect
the repository, identify what exists, and reuse established patterns.

Everything below was read from the repo. I did not open the SharePoint or
Outlook links in the review; the AeroAPI billing point is taken as given and is
reflected in the polling design.

---

## 1. What the prompt asked me to find

| # | Prompt asks for | Status | Where |
|---|---|---|---|
| 1 | Booking API routes + persistence layer | **Exists** (two paths) | `backend/api/bookings.py`, `backend/api/checkout.py`, `services/finalize_service.py` |
| 2 | Trip lifecycle / status model | **Does not exist** | — |
| 3 | Passenger account / customer-token model | **Does not exist** | — |
| 4 | Notification service + channels | **Partial** — email only | `services/graph.py` `send_mail`, `services/push_sender.py` |
| 5 | FlightAware / Flightradar24 integration | **Exists, already abstracted** | `services/flight.py`, `services/flightaware.py`, `services/flightradar24.py` |
| 6 | Driver calendar integration | **Exists** | `services/bookings.py` → `services/graph.py` `create_calendar_event` |
| 7 | Background job / scheduler / queue | **Partial** — timers, no queue | `api/timer_*.py`, `@bp.timer_trigger` |
| 8 | Conventions: validation, logging, migrations, tests, auth, config | **Mostly exist; no migrations** | see §3 |

---

## 2. The five assumptions that do not hold

These are load-bearing. Building the prompt as written would create foreign keys
to tables that don't exist — which is precisely the "parallel booking system" the
prompt forbids.

### 2.1 🔴 There is no trip completion event to hook

The prompt's §1 opens with *"Detect a transition of an eligible trip into the
completed state."* **No such transition exists.**

`Rides.Rides` carries exactly two status-ish columns: `PaymentStatus`
(`'Pending'` / `'Paid'`, `database.py:73-86`) and `Classification`. There is no
trip state, no completion timestamp, and nothing that flips when a trip ends.

Worse, the two things that would have to be joined are never reconciled:

- **At booking time**, `api/bookings.py:710` writes a `Rides` row with
  `classification = "Private_Booking"` and `RideID = build_invoice_id(...)`.
- **After the drive**, the nightly Tessie sync writes/updates rows keyed by
  Tessie drive ID.

Nothing links the two. `Private_Booking` appears in only those two write sites
and is never read back for reconciliation. So today the system cannot answer
"did booking X actually happen?" — which is the trigger the whole workflow hangs
from. **This is the one genuine fork and I need your call on it (see §5).**

### 2.2 🔴 There is no passenger account or saved-location model

Zero hits for `Customers`, `PassengerAccount`, `SavedLocation`, `CustomerId`,
`AccountId` anywhere in the backend. The only customer-shaped thing is
`services/customer_pricing.py`, which is grandfathered pricing keyed off an
email **string**.

Bookings carry `name` / `email` / `phone` as free text, and — per
`backend/tests/test_cabin_trip.py` — *"There is no bookings table — the cabin
token IS the trip's identity."*

So `passengerAccountId`, `originalPickupLocationId`, and "approved saved-location
ID" have nothing to point at.

**Proposed resolution (no new account model needed):** the `ReturnTripWorkflow`
row itself becomes the identity anchor. It stores the outbound pickup/drop-off
strings and the contact email, and the opaque token references the *workflow*,
not a passenger. This satisfies the prompt's real requirement — no PII in the
URL — without inventing an accounts subsystem. Locations stay server-side and
the browser only ever sees a masked label.

### 2.3 🟡 There is no migration system

Schema changes are inline, idempotent DDL executed inside the method that needs
them:

```python
IF NOT EXISTS (SELECT * FROM sys.columns
               WHERE object_id = OBJECT_ID('Rides.CabinTokens') AND name = 'FlightNumber')
    ALTER TABLE Rides.CabinTokens ADD FlightNumber NVARCHAR(16) NULL;
```

(`services/database.py:1002-1007`; same pattern at `:491`, `:991`, `:1101`,
`:1504`.) There is no Alembic, no migration directory, no version table.

**Proposed resolution:** follow the existing pattern rather than introducing a
migration framework mid-feature. `test_cabin_trip.py` already pins that the DDL
is idempotent (`test_columns_are_added_idempotently`), so the convention is
testable and I'll extend that.

### 2.4 🟡 There is no queue or outbox infrastructure

No Service Bus, no `queue_trigger`, no existing outbox. What exists is Azure
Functions timer triggers: `api/timer_nightly_sync.py`, `timer_payment_sync.py`,
`timer_reports.py`, `automation.py`, `pre_shift_check.py`.

**Proposed resolution:** implement the outbox as a SQL table drained by a timer
trigger, with `UPDATE ... OUTPUT` used to atomically claim rows. That is exactly
the pattern `api/bookings.py` already uses for calendar idempotency and
`finalize_service.py` uses for `_claim_session` — so the concurrency primitive
is already proven in this codebase, and I'd reuse it rather than invent one.

### 2.5 🟡 The only passenger channel is email

`services/push_sender.py` `notify_driver` is **driver-only and deliberately
content-free** — `docs/security-notes.md` §1 records why (the push route is
publicly reachable and its principal header is forgeable). Passenger contact is
Graph `send_mail` with an SMTP fallback (`api/bookings.py:636-665`).

**Proposed resolution:** the return reminder is an email. No SMS provider is
configured; adding one is out of scope unless you want it.

---

## 3. What already exists and should be reused

**Flight provider abstraction is largely built.** `FlightStatusService.get_flight_status()`
(`services/flight.py:63`) already merges FlightAware (schedule/status/delay) with
FR24 (live position), and already takes the booking context the prompt wants:

```python
get_flight_status(flight_number, expected_destination=None, when=None, dest_country=None)
```

`FlightAwareClient.flight_info()` (`services/flightaware.py:302-336`) already does
canonical ident resolution **and a destination guard** — it exists specifically
because `SWA250` resolved to the wrong leg. `_airport_matches()` handles
IATA/ICAO/LID. `when=` already scopes to a date.

**This means the prompt's §4/§5 are mostly a formalisation, not new work:** the
"flight number alone is not unique" problem the review correctly identifies is
*already solved* server-side, and there are 7 passing tests pinning it
(`backend/tests/test_flightaware_resolution.py`). What's missing is exposing an
occurrence *list* for the ambiguity case rather than a single best match.

**Concurrency primitives exist.** `_claim_session` / `_release_claim`
(`finalize_service.py:21-90`) is an atomic SQL claim with release-on-failure, and
Graph's `transactionId` gives provider-level idempotency on calendar creates
(409 on duplicate). Both are directly reusable for reminder dispatch.

**Normalisation conventions exist.** `.strip().upper()` bounded to column width,
`None` rather than `""` for absent values — established in `create_cabin_token`
and matched by the Phase 2 work.

---

## 4. Revised architecture summary

Same shape as the approved prompt, with the corrections above:

```
outbound trip completes  ──►  ReturnTripWorkflow (SQL, DB = source of truth)
   (trigger: see §5)               │
                                   ├─► timer worker claims due reminder atomically
                                   │      └─► email w/ opaque single-use token
                                   │
   passenger opens link  ──────────┤
                                   ├─► POST /api/return-trips/resolve-flight
                                   │      flightNumber + serviceDate
                                   │      └─► FlightDataProvider (wraps existing
                                   │            FlightStatusService)
                                   │            → 1 occurrence  → verification row
                                   │            → N occurrences → 409 Ambiguous
                                   │
                                   └─► POST /api/return-trips/confirm
                                          token + verificationId + idempotencyKey
                                          └─ single transaction:
                                               booking + flight binding
                                               + telemetry subscription
                                               + OutboxEvent(calendar)
                                               + token consumed
                                          └─ timer drains outbox → Graph calendar
                                               (calendarHoldStatus: Pending → Synced)
```

Unchanged from the prompt and non-negotiable in my reading: DB is authoritative,
calendar is a projection, no PII in URLs, no provider credentials client-side,
confirmation re-reads server-side verification rather than trusting the browser,
UTC persistence + IANA tz retained, bounded polling with backoff.

---

## 5. Decisions taken (2026-07-28)

- **Completion trigger: driver-confirmed**, with a time-based safety net so a
  forgotten tap doesn't lose the return. Requires a new `/driver-dashboard`
  control and endpoint — Stage 3.
- **Stage 1 built first**, since it depends on neither open question.

The options considered are kept below for the record.

## 5a. The completion-trigger decision

**How should the system know an outbound trip is complete?** There is no existing
signal (§2.1), and the three options differ in reliability and in what else they
require:

| Option | How it works | Cost | Risk |
|---|---|---|---|
| **A. Time-based** | Workflow arms when `appointmentStart + duration` has passed | Lowest — no new plumbing | Fires for no-shows and cancellations; reminder to someone who never travelled |
| **B. Driver-confirmed** | Driver taps "trip complete" on `/driver-dashboard` | Medium — new dashboard control + endpoint | Most reliable; depends on the driver remembering |
| **C. Tessie reconciliation** | Match the booking to an actual drive by time + endpoints | Highest — builds the booking↔drive linkage that doesn't exist | Fuzzy matching; but it fixes a real gap the whole system has |

My recommendation is **B**, with A as a safety net: the driver is already in the
dashboard after every trip, it produces an unambiguous auditable event, and it
does not require solving reconciliation first. C is the "right" long-term answer
and would benefit reporting well beyond this feature, but it is its own project
and shouldn't block this one.

---

## 6. Staging

This is multi-session work — the prompt specifies ~10 entities, 2 state machines,
an outbox, a token service, a scheduler, provider adapters, and ~25 test
scenarios. Proposed order, each independently shippable:

1. ~~**Foundation:** `FlightDataProvider` interface + adapter, occurrence
   resolution with ambiguity, normalised flight types, typed domain errors,
   both state machines.~~ ✅ **Delivered** — `backend/services/return_trip/`,
   95 tests in `backend/tests/test_return_trip_stage1.py`. Also extracted
   `FlightAwareClient.flight_candidates()` and `.flight_by_fa_id()` so the
   adapter can see occurrence candidates rather than a pre-selected leg.
2. **Persistence:** workflow / verification / binding / telemetry / audit /
   outbox tables via the inline-idempotent-DDL convention.
3. **Trigger + scheduler:** completion detection (per §5) and the reminder worker.
4. **Token service + the two routes** (`resolve-flight`, `confirm`).
5. **Outbox drain → calendar**, then telemetry polling with AeroAPI cost controls.

Stage 1 depends on none of the open questions and is the natural next step.
