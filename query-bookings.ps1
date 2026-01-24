# Bookings Recovery Script
$tenant = 'YOUR_TENANT_ID_HERE'
$client = 'YOUR_CLIENT_ID_HERE'
$secret = 'YOUR_CLIENT_SECRET_HERE'

Write-Host 'Getting access token...'
$body = @{
    client_id     = $client
    scope         = 'https://graph.microsoft.com/.default'
    client_secret = $secret
    grant_type    = 'client_credentials'
}
$tokenResp = Invoke-RestMethod -Method Post -Uri \"https://login.microsoftonline.com/$tenant/oauth2/v2.0/token\" -Body $body
$token = $tokenResp.access_token

Write-Host 'Querying Bookings...'
$headers = @{ Authorization = \"Bearer $token\" }
try {
    $bookings = Invoke-RestMethod -Uri 'https://graph.microsoft.com/v1.0/solutions/bookingBusinesses' -Headers $headers
    $bookings | ConvertTo-Json -Depth 10 | Out-File 'bookings-result.json'
    Write-Host \"Found $($bookings.value.Count) businesses\"
    $bookings.value | ForEach-Object { Write-Host \"  - $($_.displayName) ($($_.email))\" }
}
catch {
    Write-Host \"Error: $($_.Exception.Message)\"
}
