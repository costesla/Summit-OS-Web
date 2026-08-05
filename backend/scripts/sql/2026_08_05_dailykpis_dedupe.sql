-- Reports.DailyKPIs — stop counting soft-deleted rows and paired Tessie drives.
--
-- The view as it stood:
--
--   COUNT(CASE WHEN (Fare > 0 OR Classification = 'Manual_Entry'
--                    OR Classification = 'Uber_Matched') THEN 1 END) AS RideCount
--   FROM Rides.Rides
--   GROUP BY CAST(Timestamp_Start AS DATE);
--
-- Two defects, both observed in production 2026-08-04:
--
-- 1. No DeletedAt filter. Every other consumer of Rides.Rides filters
--    DeletedAt IS NULL — the dashboard trips view, unpaid invoices, the
--    auto-collect open set, the nightly pairing. This one did not, so rows
--    removed from the dashboard kept inflating the KPI behind it. Two
--    soft-deleted duplicate bookings were still counted on 2026-08-01.
--
-- 2. Tessie drives counted alongside the trips they belong to. The pairing
--    stamps a matched drive with Classification 'Uber_Matched' — the same
--    value the TRIP- row carries — so each Uber trip was counted twice, once
--    as its TRIP- row and once as its TESSIE- row. 2026-07-30 read 36 rides
--    against 19 actual: 17 TRIP + 2 INV + 17 TESSIE.
--
-- The count now excludes TESSIE- rows by RideID prefix rather than by
-- classification. Prefix is structural; classification is written by the
-- pairing and will drift again the next time its vocabulary changes.
--
-- Earnings and tips are unaffected by defect 2 (matched drives carry 0) but
-- were affected by defect 1, so the DeletedAt filter changes both.
--
-- This is a view, not a materialized table: correcting it corrects all history
-- at once, with no recompute pass and no seam between old and new rows.
--
-- ROLLBACK — the prior definition, verbatim:
--
--   CREATE OR ALTER VIEW Reports.DailyKPIs AS
--   SELECT
--       CAST(Timestamp_Start AS DATE) AS [Date],
--       SUM(ISNULL(Driver_Earnings, 0)) AS TotalEarnings,
--       SUM(ISNULL(Tip, 0)) AS TotalTips,
--       COUNT(CASE WHEN (Fare > 0 OR Classification = 'Manual_Entry' OR Classification = 'Uber_Matched') THEN 1 END) AS RideCount
--   FROM Rides.Rides
--   GROUP BY CAST(Timestamp_Start AS DATE);

CREATE OR ALTER VIEW Reports.DailyKPIs AS
SELECT
    CAST(Timestamp_Start AS DATE) AS [Date],
    SUM(ISNULL(Driver_Earnings, 0)) AS TotalEarnings,
    SUM(ISNULL(Tip, 0)) AS TotalTips,
    COUNT(CASE
              WHEN RideID NOT LIKE 'TESSIE-%'
                   AND (Fare > 0
                        OR Classification = 'Manual_Entry'
                        OR Classification = 'Uber_Matched')
              THEN 1
          END) AS RideCount
FROM Rides.Rides
WHERE DeletedAt IS NULL
GROUP BY CAST(Timestamp_Start AS DATE);
