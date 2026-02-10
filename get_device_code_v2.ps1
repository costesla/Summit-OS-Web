$tenantId = "1cd94367-e5ad-4827-90a9-cc4c6124a340"
$clientId = "a7d212ac-dd2b-4910-a62a-b623a8ac250c"
$scope = "offline_access Bookings.ReadWrite.All User.Read"

# 1. Get Code
$url = "https://login.microsoftonline.com/$tenantId/oauth2/v2.0/devicecode"
$body = @{
    client_id = $clientId
    scope     = $scope
}
try {
    $resp = Invoke-RestMethod -Method Post -Uri $url -Body $body
}
catch {
    Write-Host "Fatal Error getting code: $_"
    exit 1
}

$deviceCode = $resp.device_code
$userCode = $resp.user_code
$verificationUri = $resp.verification_uri
$interval = $resp.interval
$expiresIn = $resp.expires_in

# Backup the secret device code immediately
$deviceCode | Out-File -FilePath "device_code_secret.txt" -Encoding utf8

Write-Host "`n============================================================"
Write-Host "ACTION REQUIRED: AUTHORIZE MFA (ATTEMPT 2)"
Write-Host "============================================================"
Write-Host "1. Go to: $verificationUri"
Write-Host "2. Enter code: $userCode"
Write-Host "============================================================`n"

"URL: $verificationUri`nCode: $userCode" | Out-File -FilePath "auth_code_v2.txt" -Encoding utf8

# 2. Poll for Token
$tokenUrl = "https://login.microsoftonline.com/$tenantId/oauth2/v2.0/token"
$tokenBody = @{
    grant_type  = "urn:ietf:params:oauth:grant-type:device_code"
    client_id   = $clientId
    device_code = $deviceCode
}

$startTime = Get-Date
$expiryTime = $startTime.AddSeconds($expiresIn)

Write-Host "Polling for token..."

while ((Get-Date) -lt $expiryTime) {
    try {
        # Try to get token
        $tokenResp = Invoke-RestMethod -Method Post -Uri $tokenUrl -Body $tokenBody -ErrorAction Stop
        
        Write-Host "`nSUCCESS! Refresh Token Acquired."
        $tokenResp.refresh_token | Out-File -FilePath "refresh_token.txt" -Encoding utf8
        $tokenResp.access_token | Out-File -FilePath "access_token_debug.txt" -Encoding utf8
        exit 0
    }
    catch {
        # Check if it is just "pending"
        $msg = $_.Exception.Message
        if ($msg -match "authorization_pending") {
            # Expected wait
            Write-Host -NoNewline "."
        }
        elseif ($msg -match "slow_down") {
            Write-Host -NoNewline "s"
            $interval += 5
        }
        else {
            # Try to read body if possible, otherwise just print message
            $details = $_.ErrorDetails.Message
            if (-not $details) { $details = $msg }
            
            # If it's 400 Bad Request, it's usually pending.
            # We will assume pending unless we see "expired"
            if ($details -match "expired") {
                Write-Host "Expired."
                exit 1
            }
            # Keep waiting
            Write-Host -NoNewline "."
        }
    }
    Start-Sleep -Seconds $interval
}
Write-Host "Timed out."
exit 1
