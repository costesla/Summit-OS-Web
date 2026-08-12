---
name: booking-lifecycle
description: Procedures for creating, querying, and deleting bookings in SummitOS across Azure SQL (Rides.Rides), Microsoft Graph Calendar, and Tessie drive classifications.
---

# SummitOS Booking Lifecycle & Deletion Protocol

This skill details how private bookings and unpaid invoices are stored, managed, and deleted across the SummitOS system.

---

## 1. System Architecture & Components

When a booking is created or deleted in SummitOS, three data stores are involved:

1. **Azure SQL (`Rides.Rides`)**:
   - Primary database table storing trip records, fare, payment status (`Pending`, `Paid`), and driver earnings.
   - Deletion route: `DELETE /api/operations/delete-trip/{ride_id}` (physically removes the row or sets `DeletedAt`).

2. **Microsoft Graph API / Outlook Calendar**:
   - `GraphClient` handles creation (`create_appointment`) and deletion (`delete_calendar_event`).
   - Mapped via `Bookings.CalendarIdempotency` (`IdempotencyKey` → `EventId`) or `Sidecar_Artifact_JSON` (`calendar_event_id`).

3. **Tessie Drive Tagging & Classification**:
   - When a booking is tied to a vehicle drive (`Tessie_DriveID`), deleting the booking must check if any other trips are linked.
   - If no other trips remain mapped to that `Tessie_DriveID`, reset the drive's classification back to `'Untagged'` and set `TripType = NULL`.

---

## 2. Booking Deletion Requirements

Whenever implementing or modifying booking deletion:

- **Two-Way Cleanup**: Deleting a booking must purge both the database record in `Rides.Rides` **and** any corresponding calendar event in Microsoft Graph.
- **Tessie Drive Reset**: Verify if `Tessie_DriveID` is non-null. Count other mapped trips (`SELECT COUNT(*) FROM Rides.Rides WHERE Tessie_DriveID = ? AND RideID <> ?`). If 0, reset `Classification = 'Untagged'`.
- **Idempotency Lookup**: Query `Bookings.CalendarIdempotency` using `ride_id` as the key to retrieve the `EventId` if `calendar_event_id` is missing from `Sidecar_Artifact_JSON`.
- **UI Confirmation & State Sync**:
  - Always require explicit confirmation (`window.confirm`) before sending `DELETE` requests.
  - Immediately filter out deleted items from React component state and call `fetchAllData()` to recalculate daily earnings/kpis.
