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
-- All three columns are nullable with no default and no backfill: existing rows
-- stay NULL, which is the correct statement about them.
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
