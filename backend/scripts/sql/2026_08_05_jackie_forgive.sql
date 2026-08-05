-- JACKIE — forgive the outstanding balance. APPLIED TO PROD 2026-08-05 13:43:21 UTC.
--
-- This file is the record of a change that has already run. It is committed so the
-- repo explains prod's current shape; re-running it is a no-op because the WHERE
-- clause no longer matches (those rows are 'Forgiven' now, not Pending/Deferred).
--
-- BUSINESS CONTEXT: JACKIE is no longer a paying client. Any balance owed is
-- forgiven effective 2026-08-05. Future drives are non-chargeable and are still
-- logged in Tessie for the operator's daily structure.
--
-- WHAT THIS IS NOT: not a delete, not DeletedAt, not a Driver_Earnings edit. Past
-- rides were real work; the revenue was earned and stays in Reports.DailyKPIs.
-- Only the receivable is forgiven. Verified: KPI TotalEarnings and RideCount over
-- the affected dates read 180 / $2,228.83 both before and after.
--
-- SCOPE — 51 rows: Pending (33, $930.00) + Deferred (18, $540.00).
--
-- DELIBERATELY EXCLUDED, considered and left rather than missed:
--   Credit (10 rows, $0.00)  — the Jackie billing engine's marker for AA-tagged /
--                              over-cap legs. Means "never chargeable".
--   Comped (4 rows, $150.00) — means "deliberately not billed".
--   Paid   (7 rows, $210.00) — already settled; reclassifying real revenue
--                              retroactively would break the Phase 0 KPI
--                              reconciliation that was verified line by line.
--
-- The rule: 'Forgiven' may only overwrite states that still imply COLLECTION.
-- Pending implies it; Deferred implies it later. Credit and Comped are already
-- terminal non-collection states carrying a MORE SPECIFIC fact than 'Forgiven'
-- does. Overwriting them would replace precise history with vaguer history and
-- assert a debt that never existed. PriorPaymentStatus would preserve the old
-- value, but only for a reader who thinks to look for it.
--
-- MEASURED EFFECT (pre-registered, then verified):
--   open receivables  68 rows $2,500.62  ->  35 rows $1,570.62   (-33 rows, -$930.00)
--   KPI TotalEarnings $2,228.83 -> $2,228.83   (Reports.DailyKPIs has no
--   KPI RideCount     180 -> 180                PaymentStatus reference at all)
--   Only 33 of the 51 moved money; the 18 Deferred rows were never in the open set,
--   so that portion is pure relabeling.
--
-- WHY IT IS NOW SAFE FROM AUTO-COLLECT ON TWO LAYERS: every PaymentStatus predicate
-- in the backend is positive (equality or a positive IN list) — there is no NOT IN,
-- no <>, no != anywhere — so a new status value drops out by construction. Before
-- this, the only guard was the Python INACTIVE_CLIENTS check inside
-- _auto_collect_invoices.
--
-- ROLLBACK (restores both the status and clears the audit trail):
--   UPDATE Rides.Rides
--   SET PaymentStatus = PriorPaymentStatus,
--       PriorPaymentStatus = NULL, StatusChangedAt = NULL,
--       StatusEffectiveDate = NULL, StatusChangeReason = NULL
--   WHERE StatusChangeReason = 'jackie-forgiven-2026-08-05';

UPDATE Rides.Rides
SET PriorPaymentStatus  = PaymentStatus,
    PaymentStatus       = 'Forgiven',
    StatusChangedAt     = GETUTCDATE(),
    StatusEffectiveDate = '2026-08-05',
    StatusChangeReason  = 'jackie-forgiven-2026-08-05',
    LastUpdated         = GETUTCDATE()
WHERE RideID LIKE 'INV-JACKIE-%'
  AND DeletedAt IS NULL
  AND PaymentStatus IN ('Pending', 'Deferred');

-- Verification actually run after execution:
--   51 rows updated
--   PriorPaymentStatus preserved: 33 'Pending', 18 'Deferred'
--   JACKIE rows still Pending: 0
--   non-JACKIE rows carrying this reason code: 0
--   non-JACKIE rows now 'Forgiven': 0
--   forgiven rows also soft-deleted: 0
