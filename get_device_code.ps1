$tenantId = "1cd94367-e5ad-4827-90a9-cc4c6124a340"
$clientId = "a7d212ac-dd2b-4910-a62a-b623a8ac250c"
$scope = "offline_access Bookings.ReadWrite.All User.Read"

# 1. Get Code
$url = "https://login.microsoftonline.com/$tenantId/oauth2/v2.0/devicecode"
$body = @{
    client_id = $clientId
    scope     = $scope
}
$resp = Invoke-RestMethod -Method Post -Uri $url -Body $body

$deviceCode = $resp.device_code
$userCode = $resp.user_code
$verificationUri = $resp.verification_uri
$interval = $resp.interval
$expiresIn = $resp.expires_in

Write-Host "`n============================================================"
Write-Host "ACTION REQUIRED: AUTHORIZE MFA"
Write-Host "============================================================"
Write-Host "1. Go to: $verificationUri"
Write-Host "2. Enter code: $userCode"
Write-Host "============================================================`n"

# Write to file for agent to read
"URL: $verificationUri`nCode: $userCode" | Out-File -FilePath "auth_code.txt" -Encoding utf8

# 2. Poll for Token
$tokenUrl = "https://login.microsoftonline.com/$tenantId/oauth2/v2.0/token"
$tokenBody = @{
    grant_type  = "urn:ietf:params:oauth:grant-type:device_code"
    client_id   = $clientId
    device_code = $deviceCode
}

$startTime = Get-Date

Write-Host "Waiting for sign-in... (Expires in $expiresIn seconds)"

while ($true) {
    if ((Get-Date) -gt $startTime.AddSeconds($expiresIn)) {
        Write-Host "Timed out."
        exit 1
    }
    
    try {
        $tokenResp = Invoke-RestMethod -Method Post -Uri $tokenUrl -Body $tokenBody -ErrorAction Stop
        Write-Host "`nSUCCESS! Refresh Token Acquired."
        $tokenResp.refresh_token | Out-File -FilePath "refresh_token.txt" -Encoding utf8
        exit 0
    }
    catch {
        $err = $_.Exception.Response
        if ($err) {
            $reader = New-Object System.IO.StreamReader($err.GetResponseStream())
            $errBody = $reader.ReadToEnd() | ConvertFrom-Json
            if ($errBody.error -eq "authorization_pending") {
                # Wait loops
            }
            elseif ($errBody.error -eq "slow_down") {
                $interval += 5
            }
            else {
                Write-Host "Error: $($errBody.error)"
                exit 1
            }
        }
    }
    Start-Sleep -Seconds $interval
}
