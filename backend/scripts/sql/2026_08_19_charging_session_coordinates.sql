-- Persist where a charging session happened.
--
-- Rides.ChargingSessions stores Location_Name (a street address from Tessie)
-- and nothing else about place. Supercharger classification was therefore a
-- substring test for "supercharger" against an address that never contains
-- the word, so every Supercharger session was reported as other-charging and
-- supercharger_cost read $0.00 regardless of spend.
--
-- Tessie already sends latitude/longitude on every session; save_charge simply
-- discarded them. These columns keep what was already being received.
--
-- Additive and nullable: existing rows stay valid and read as UNKNOWN until
-- backfilled. Backfill is a re-run of TessieSyncService.sync_day over the
-- desired range — save_charge MERGEs on SessionID, so replaying is safe.
--
-- STEP 1 — schema (idempotent; safe to re-run)

IF COL_LENGTH('Rides.ChargingSessions', 'Latitude') IS NULL
    ALTER TABLE Rides.ChargingSessions ADD Latitude DECIMAL(9,6) NULL;
GO

IF COL_LENGTH('Rides.ChargingSessions', 'Longitude') IS NULL
    ALTER TABLE Rides.ChargingSessions ADD Longitude DECIMAL(9,6) NULL;
GO

-- Tessie states outright whether a session was at a Supercharger. Keeping its
-- answer beats inferring one: the coordinate registry earns its place by
-- GROUPING a station whose address reverse-geocodes four different ways
-- (215 / 219 / 2611 / 2727 N Cascade Ave are one site), not by guessing a fact
-- the source already reports.
IF COL_LENGTH('Rides.ChargingSessions', 'IsSupercharger') IS NULL
    ALTER TABLE Rides.ChargingSessions ADD IsSupercharger BIT NULL;
GO

-- STEP 2 — verification. Coverage climbs as sync_day replays history.
SELECT
    COUNT(*)                                                        AS total_sessions,
    SUM(CASE WHEN Latitude IS NOT NULL THEN 1 ELSE 0 END)           AS with_coordinates,
    SUM(CASE WHEN Cost IS NULL OR Cost = 0 THEN 1 ELSE 0 END)       AS zero_or_null_cost,
    MIN(Start_Time)                                                 AS earliest,
    MAX(Start_Time)                                                 AS latest
FROM Rides.ChargingSessions;
GO

-- ROLLBACK (only if these columns must be withdrawn; drops captured data)
-- ALTER TABLE Rides.ChargingSessions DROP COLUMN Latitude;
-- ALTER TABLE Rides.ChargingSessions DROP COLUMN Longitude;
