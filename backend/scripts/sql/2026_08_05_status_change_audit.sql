-- Audit columns for deliberate PaymentStatus transitions.
--
-- A status change that records only the NEW value destroys the fact it replaced.
-- Forgiving a balance, comping a ride and cancelling a booking all land in the
-- same field, and afterwards nothing distinguishes "was never billed" from "was
-- billed and written off" — which is exactly the question an accountant asks.
--
-- These three columns are deliberately generic rather than forgiveness-specific.
-- The cancellation-reason vocabulary planned for PR 2 (customer-cancelled |
-- duplicate | driver-unavailable | never-created) writes to the same columns, so
-- the shape is chosen once here instead of twice.
--
--   PriorPaymentStatus   the value being replaced. Captured BEFORE the overwrite.
--                        Cancelled-after-paid is real on the Stripe path and a
--                        refund needs to know money was actually taken.
--   StatusChangedAt      when the row was WRITTEN (server clock, UTC).
--   StatusEffectiveDate  when the DECISION took effect. Deliberately separate:
--                        a decision made on the evening of 08-04 Mountain is
--                        08-05 UTC, and backfilling history days later must not
--                        silently restamp the decision date to the write date.
--   StatusChangeReason   short code. Free text is unqueryable six months later.
--
-- NOT recorded here and deliberately so: nothing is deleted, DeletedAt is not
-- touched, and Driver_Earnings is untouched. Past rides were real work; the
-- revenue was earned and stays in DailyKPIs. Only the receivable is forgiven.
--
-- ROLLBACK:
--   -- restore the prior values, then drop:
--   UPDATE Rides.Rides SET PaymentStatus = PriorPaymentStatus
--   WHERE PriorPaymentStatus IS NOT NULL AND StatusChangeReason = 'jackie-forgiven-2026-08-05';
--   ALTER TABLE Rides.Rides DROP COLUMN PriorPaymentStatus;
--   ALTER TABLE Rides.Rides DROP COLUMN StatusChangedAt;
--   ALTER TABLE Rides.Rides DROP COLUMN StatusEffectiveDate;
--   ALTER TABLE Rides.Rides DROP COLUMN StatusChangeReason;

IF COL_LENGTH('Rides.Rides', 'PriorPaymentStatus') IS NULL
    ALTER TABLE Rides.Rides ADD PriorPaymentStatus NVARCHAR(20) NULL;

IF COL_LENGTH('Rides.Rides', 'StatusChangedAt') IS NULL
    ALTER TABLE Rides.Rides ADD StatusChangedAt DATETIME2 NULL;

IF COL_LENGTH('Rides.Rides', 'StatusEffectiveDate') IS NULL
    ALTER TABLE Rides.Rides ADD StatusEffectiveDate DATE NULL;

IF COL_LENGTH('Rides.Rides', 'StatusChangeReason') IS NULL
    ALTER TABLE Rides.Rides ADD StatusChangeReason NVARCHAR(64) NULL;
