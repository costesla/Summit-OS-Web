-- Update DailyKPIs view to only count trips that have earnings or are manual entries
-- This ensures that only trips the user has "input" (via cards or dashboard) appear in the summary stats.

GO
CREATE OR ALTER VIEW Reports.DailyKPIs AS
SELECT 
    CAST(Timestamp_Start AS DATE) AS [Date],
    SUM(ISNULL(Driver_Earnings, 0)) AS TotalEarnings,
    SUM(ISNULL(Tip, 0)) AS TotalTips,
    COUNT(CASE WHEN (Fare > 0 OR Classification = 'Manual_Entry' OR Classification = 'Uber_Matched') THEN 1 END) AS RideCount
FROM Rides.Rides
GROUP BY CAST(Timestamp_Start AS DATE);
GO
