# Test process-blob endpoint with sample blob URL
$key = "YOUR_FUNCTION_KEY_HERE"
$url = "https://summitsyncfuncus23436.azurewebsites.net/api/process-blob?code=$key"

# Get a sample blob URL from storage
$testBlob = az storage blob list --account-name summitstoreus23 -c function-releases --prefix "2026-01-16" --auth-mode login --query "[0].name" -o tsv

if ($testBlob) {
    $blobUrl = "https://summitstoreus23.blob.core.windows.net/function-releases/$testBlob"
    
    $body = @{blob_url = $blobUrl } | ConvertTo-Json
    
    Write-Host "Testing with blob: $testBlob"
    Invoke-RestMethod -Uri $url -Method Post -Body $body -ContentType "application/json"
}
else {
    Write-Host "No test blobs found"
}
