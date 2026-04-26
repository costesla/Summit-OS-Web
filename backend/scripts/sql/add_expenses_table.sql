-- SummitOS: Add Manual Expenses Table
-- Version 1.1

IF OBJECT_ID('Rides.ManualExpenses', 'U') IS NULL
CREATE TABLE Rides.ManualExpenses (
    ExpenseID NVARCHAR(100) PRIMARY KEY,
    Category NVARCHAR(50), -- FastFood, Other
    Amount DECIMAL(10,2),
    Note NVARCHAR(500),
    Timestamp DATETIME DEFAULT GETDATE(),
    LastUpdated DATETIME DEFAULT GETDATE()
);
GO
