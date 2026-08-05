-- Link a booking row to the Microsoft Bookings appointment(s) it created.
--
-- Today /api/book calls create_appointment() twice — once for the outbound leg
-- and once for the return — and discards both return values. calendar_book (the
-- Stripe path) captures an eventId but never persists it. So no row in
-- Rides.Rides can be matched back to an appointment in Outlook, and a deletion
-- there is invisible here. That missing key is the actual defect behind the
-- phantom receivables; everything else is downstream of it.
--
-- TWO id columns, not one: a round trip is ONE Rides row and TWO appointments
-- (backend/api/bookings.py:413 outbound, :443 return, one save_trip at :718).
-- A single column would let the sweep adjudicate half a booking.
--
-- AppointmentSyncStatus exists because NULL alone is ambiguous, and the two
-- meanings need opposite handling by the reconciliation sweep:
--
--   NULL        legacy row, written before this column existed. The sweep can
--               never adjudicate it — no id was ever captured. Unverifiable
--               forever; must never be auto-cancelled.
--   'captured'  both applicable ids stored. Fully adjudicable.
--   'partial'   one leg captured, the other failed. Adjudicate only the leg
--               that has an id.
--   'failed'    Graph errored at booking time. The appointment may or may not
--               exist. Retryable — unlike NULL, this row is worth re-linking.
--
-- Existing booking rows are stamped 'legacy' rather than left NULL, so that
-- NULL carries exactly one meaning going forward. Left unstamped, NULL would
-- conflate three different facts:
--
--   1. a row written before the column existed          (unverifiable forever)
--   2. a crash between save_trip's commit and the       (a BUG — must alarm)
--      separate appointment-link UPDATE
--   3. a booking that never expected an appointment     (nothing is wrong)
--
-- Only (1) is unverifiable-forever, but all three read NULL. (3) now writes
-- 'none-expected' explicitly, and after this backfill (2) is the ONLY way a
-- booking row can hold NULL — which makes it detectable instead of hiding
-- inside a legitimate category. Sorting them out post-deploy would mean
-- inferring from CreatedAt against the deploy timestamp; doing it now costs
-- one UPDATE.
--
-- SCOPE: the booking domain is NOT 'INV-%'. The booking paths have minted
-- R- (save_trip's hash fallback), M- (manual dashboard entry) and, on an older
-- canonical_invoice_id, raw cs_live_* Stripe session ids. 365 rows are
-- TripType='Private' and not TESSIE-; scoping to INV- would leave 132 of them
-- unstamped and a post-deploy NULL there would not alarm. TESSIE- is excluded
-- because a telematics drive is not a booking and has no appointment concept,
-- even though 8850 of them carry TripType='Private'.
--
-- INVARIANT after this migration:
--   SELECT COUNT(*) FROM Rides.Rides
--   WHERE TripType = 'Private' AND RideID NOT LIKE 'TESSIE-%'
--     AND AppointmentSyncStatus IS NULL;
--   -- must be 0. Anything else is a dropped write.
--
-- ROLLBACK:
--   ALTER TABLE Rides.Rides DROP COLUMN AppointmentID;
--   ALTER TABLE Rides.Rides DROP COLUMN ReturnAppointmentID;
--   ALTER TABLE Rides.Rides DROP COLUMN AppointmentSyncStatus;

IF COL_LENGTH('Rides.Rides', 'AppointmentID') IS NULL
    ALTER TABLE Rides.Rides ADD AppointmentID NVARCHAR(256) NULL;

IF COL_LENGTH('Rides.Rides', 'ReturnAppointmentID') IS NULL
    ALTER TABLE Rides.Rides ADD ReturnAppointmentID NVARCHAR(256) NULL;

IF COL_LENGTH('Rides.Rides', 'AppointmentSyncStatus') IS NULL
    ALTER TABLE Rides.Rides ADD AppointmentSyncStatus NVARCHAR(16) NULL;
GO

-- Stamp every pre-existing booking row. Idempotent: re-running touches nothing,
-- because anything written after this point has a non-NULL status by design.
UPDATE Rides.Rides
SET AppointmentSyncStatus = 'legacy'
WHERE TripType = 'Private'
  AND RideID NOT LIKE 'TESSIE-%'
  AND AppointmentSyncStatus IS NULL;
