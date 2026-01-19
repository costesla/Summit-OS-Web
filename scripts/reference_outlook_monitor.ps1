# SummitOS Outlook Integration Script
$TenantId = "1cd94367-e5ad-4827-90a9-cc4c6124a340"
$ClientId = "YOUR_APP_ID_HERE"
$ClientSecret = "YOUR_CLIENT_SECRET_HERE"

# 1. Connect to Microsoft Graph
$Body = @{
    grant_type    = "client_credentials"
    scope         = "https://graph.microsoft.com/.default"
    client_id     = $ClientId
    client_secret = $ClientSecret
}
$TokenResponse = Invoke-RestMethod -Method Post -Uri "https://login.microsoftonline.com/$TenantId/oauth2/v2.0/token" -Body $Body
$AccessToken = $TokenResponse.access_token

# 2. Fetch Today's Private Trips
$Today = (Get-Date).ToString("yyyy-MM-ddT00:00:00Z")
$URL = "https://graph.microsoft.com/v1.0/users/peter.teehan@costesla.com/calendar/events?`$filter=start/dateTime ge '$Today'"

$Events = Invoke-RestMethod -Method Get -Uri $URL -Headers @{Authorization = "Bearer $AccessToken"}

# 3. Logistical Check: Match with Tessie Location
# If Thor's destination matches an event location, activate the Fairness Engine
foreach ($Trip in $Events.value) {
    Write-Host "Monitoring Booking: $($Trip.subject) at $($Trip.location.displayName)" -ForegroundColor Cyan
}
