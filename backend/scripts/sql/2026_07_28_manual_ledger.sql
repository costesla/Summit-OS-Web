/* ============================================================================
   2026_07_28_manual_ledger.sql
   Manual Ledger for Jackie & Luis

   WHAT THIS DOES
     Creates the manual-ledger tables and (in STEP 2, deliberately) activates
     Jackie and Luis with an opening balance of $0.00.

   WHAT THIS DOES NOT DO
     It does not delete, clear, overwrite or mutate ANY historical record.
     Finance.LuisBalanceLog and the Rides.Rides invoice rows are left exactly
     as they are, and remain queryable as audit history. The reset to $0.00 is
     an opening baseline — no offsetting "correction" transactions are written.

   WHY A BASELINE ID RATHER THAN A CUTOFF DATE
     Balances are computed as the active baseline's OpeningBalance plus the net
     of entries carrying that BaselineID (enforced by FOREIGN KEY). Legacy rows
     have no BaselineID, so no clock skew, replay, backfill or back-dated insert
     can leak them into a current balance. Isolation is structural.

   DEPLOYMENT
     Deploying the application code and applying this migration are SEPARATE
     controls. Application startup never activates a baseline. Run STEP 1
     (schema) with the release; run STEP 2 (activation) deliberately, once,
     when you intend the cutover. Both steps are idempotent and re-runnable.

   ROLLBACK
     See STEP 3. Deactivating restores the legacy display but does NOT by
     itself re-enable automatic Luis accrual — the code guard keys off the
     ManualOnly policy, so re-enabling accrual is an explicit code decision.
============================================================================ */

SET XACT_ABORT ON;
GO

/* ---------------------------------------------------------------------------
   STEP 1 — SCHEMA (safe to run with any release; creates nothing user-visible)
--------------------------------------------------------------------------- */
BEGIN TRANSACTION;

IF NOT EXISTS (SELECT * FROM sys.schemas WHERE name = 'Finance')
    EXEC('CREATE SCHEMA Finance');

IF OBJECT_ID('Finance.ManualLedgerBaseline', 'U') IS NULL
CREATE TABLE Finance.ManualLedgerBaseline (
    BaselineID      UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    PersonKey       VARCHAR(20)   NOT NULL,
    OpeningBalance  DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    Mode            VARCHAR(20)   NOT NULL DEFAULT 'ManualOnly',
    IsActive        BIT           NOT NULL DEFAULT 1,
    ActivatedAtUtc  DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME(),
    ActivatedBy     VARCHAR(100)  NOT NULL DEFAULT 'migration',
    LegacyCutoffRef VARCHAR(200)  NULL,
    RowVersion      ROWVERSION,
    CONSTRAINT CK_MLBaseline_PersonKey CHECK (PersonKey IN ('JACKIE','LUIS')),
    CONSTRAINT CK_MLBaseline_Mode      CHECK (Mode IN ('ManualOnly','Legacy'))
);

/* At most one ACTIVE baseline per person. */
IF NOT EXISTS (SELECT * FROM sys.indexes
               WHERE name = 'UX_MLBaseline_ActivePerson'
                 AND object_id = OBJECT_ID('Finance.ManualLedgerBaseline'))
    CREATE UNIQUE INDEX UX_MLBaseline_ActivePerson
    ON Finance.ManualLedgerBaseline (PersonKey) WHERE IsActive = 1;

IF OBJECT_ID('Finance.ManualLedgerEntry', 'U') IS NULL
CREATE TABLE Finance.ManualLedgerEntry (
    EntryID        UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    BaselineID     UNIQUEIDENTIFIER NOT NULL,
    PersonKey      VARCHAR(20)   NOT NULL,
    EntryType      VARCHAR(20)   NOT NULL,
    Amount         DECIMAL(10,2) NOT NULL,
    EffectiveDate  DATE          NOT NULL,
    Note           NVARCHAR(500) NULL,
    Source         VARCHAR(50)   NOT NULL DEFAULT 'Manual Ledger',
    RootEntryID    UNIQUEIDENTIFIER NULL,
    RevisionNumber INT           NOT NULL DEFAULT 1,
    IsCurrent      BIT           NOT NULL DEFAULT 1,
    VoidedAtUtc    DATETIME2     NULL,
    VoidedBy       VARCHAR(100)  NULL,
    IdempotencyKey VARCHAR(120)  NULL,
    CreatedAtUtc   DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME(),
    CreatedBy      VARCHAR(100)  NOT NULL DEFAULT 'unknown',
    UpdatedAtUtc   DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME(),
    RowVersion     ROWVERSION,
    CONSTRAINT FK_MLEntry_Baseline FOREIGN KEY (BaselineID)
        REFERENCES Finance.ManualLedgerBaseline (BaselineID),
    CONSTRAINT CK_MLEntry_PersonKey CHECK (PersonKey IN ('JACKIE','LUIS')),
    CONSTRAINT CK_MLEntry_EntryType CHECK (EntryType IN ('Charge','Payment','Credit')),
    CONSTRAINT CK_MLEntry_Amount    CHECK (Amount > 0)
);

IF NOT EXISTS (SELECT * FROM sys.indexes
               WHERE name = 'IX_MLEntry_Baseline_Current'
                 AND object_id = OBJECT_ID('Finance.ManualLedgerEntry'))
    CREATE INDEX IX_MLEntry_Baseline_Current
    ON Finance.ManualLedgerEntry (BaselineID, IsCurrent, VoidedAtUtc);

/* DB-backed idempotency: a replayed create collapses to a single entry. */
IF NOT EXISTS (SELECT * FROM sys.indexes
               WHERE name = 'UX_MLEntry_Idempotency'
                 AND object_id = OBJECT_ID('Finance.ManualLedgerEntry'))
    CREATE UNIQUE INDEX UX_MLEntry_Idempotency
    ON Finance.ManualLedgerEntry (IdempotencyKey) WHERE IdempotencyKey IS NOT NULL;

IF OBJECT_ID('Finance.ManualLedgerAudit', 'U') IS NULL
CREATE TABLE Finance.ManualLedgerAudit (
    AuditID        UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    EntryID        UNIQUEIDENTIFIER NOT NULL,
    EventType      VARCHAR(20)   NOT NULL,
    PreviousValues NVARCHAR(MAX) NULL,
    NewValues      NVARCHAR(MAX) NULL,
    Actor          VARCHAR(100)  NOT NULL DEFAULT 'unknown',
    CorrelationID  VARCHAR(120)  NULL,
    Reason         NVARCHAR(500) NULL,
    AtUtc          DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT CK_MLAudit_EventType CHECK (EventType IN ('Create','Edit','Void','Activate'))
);

COMMIT TRANSACTION;
GO

/* ---------------------------------------------------------------------------
   STEP 2 — ACTIVATION (deliberate cutover; run once, when intended)

   Seeds Jackie and Luis at OpeningBalance 0.00 in ManualOnly mode. After this
   runs, both dashboards show $0.00 and only manual entries move the number.
   Idempotent: re-running will not create a second active baseline.
--------------------------------------------------------------------------- */
BEGIN TRANSACTION;

INSERT INTO Finance.ManualLedgerBaseline (PersonKey, OpeningBalance, Mode, IsActive, ActivatedBy, LegacyCutoffRef)
SELECT p.PersonKey, 0.00, 'ManualOnly', 1, 'migration:2026_07_28', p.CutoffRef
FROM (VALUES
        ('JACKIE', 'legacy: Rides.Rides INV-JACKIE/INV-JACQUELYN deferred invoices retained as history'),
        ('LUIS',   'legacy: Finance.LuisBalanceLog accrual retained as history')
     ) AS p(PersonKey, CutoffRef)
WHERE NOT EXISTS (
    SELECT 1 FROM Finance.ManualLedgerBaseline b
    WHERE b.PersonKey = p.PersonKey AND b.IsActive = 1
);

INSERT INTO Finance.ManualLedgerAudit (EntryID, EventType, NewValues, Actor, Reason)
SELECT b.BaselineID, 'Activate',
       CONCAT('{"personKey":"', b.PersonKey, '","openingBalance":"0.00","mode":"ManualOnly"}'),
       'migration:2026_07_28',
       'Manual ledger cutover — legacy history preserved, not mutated'
FROM Finance.ManualLedgerBaseline b
WHERE b.IsActive = 1
  AND NOT EXISTS (
      SELECT 1 FROM Finance.ManualLedgerAudit a
      WHERE a.EntryID = b.BaselineID AND a.EventType = 'Activate'
  );

COMMIT TRANSACTION;
GO

/* ---------------------------------------------------------------------------
   STEP 3 — ROLLBACK (run only deliberately)

   Deactivates the baselines, which restores the legacy Receivables/Luis
   display. Entries are retained. Drop the tables only if you are certain no
   manual entries need keeping — that IS destructive to manual data, which is
   why it is commented out rather than executable by default.

   NOTE: deactivating does not silently restore automatic Luis accrual; the
   producer guard keys off the ManualOnly policy in code.

   UPDATE Finance.ManualLedgerBaseline SET IsActive = 0 WHERE PersonKey IN ('JACKIE','LUIS');

   -- DROP TABLE Finance.ManualLedgerAudit;
   -- DROP TABLE Finance.ManualLedgerEntry;
   -- DROP TABLE Finance.ManualLedgerBaseline;
--------------------------------------------------------------------------- */

/* ---------------------------------------------------------------------------
   VERIFICATION (read-only; expect both balances to be exactly 0.00 at cutover)
--------------------------------------------------------------------------- */
SELECT b.PersonKey,
       b.OpeningBalance,
       b.Mode,
       b.ActivatedAtUtc,
       CAST(b.OpeningBalance
            + ISNULL(SUM(CASE WHEN e.EntryType = 'Charge' THEN e.Amount
                              WHEN e.EntryType IN ('Payment','Credit') THEN -e.Amount END), 0)
            AS DECIMAL(10,2)) AS CurrentBalance
FROM Finance.ManualLedgerBaseline b
LEFT JOIN Finance.ManualLedgerEntry e
       ON e.BaselineID = b.BaselineID
      AND e.IsCurrent = 1
      AND e.VoidedAtUtc IS NULL
WHERE b.IsActive = 1
GROUP BY b.PersonKey, b.OpeningBalance, b.Mode, b.ActivatedAtUtc;
GO
