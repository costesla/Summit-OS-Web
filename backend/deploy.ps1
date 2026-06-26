$appName       = "summitos-api"
$resourceGroup = "rg-summitos-prod"
$zipName       = "backend_deploy_clean.zip"

Write-Host "=== SummitOS Backend Deploy ===" -ForegroundColor Cyan
Write-Host "Target: $appName ($resourceGroup)"

# --- SECURITY GATE (pre-zip validation) ---
Write-Host "`n[1/4] Running pre-zip security validation..." -ForegroundColor Yellow
$validatorPath = Join-Path $PSScriptRoot "validate_before_zip.py"
if (-not (Test-Path $validatorPath)) {
    Write-Host "ERROR: validate_before_zip.py not found. Aborting." -ForegroundColor Red
    exit 1
}
python $validatorPath --dir $PSScriptRoot
if ($LASTEXITCODE -ne 0) {
    Write-Host "ABORT: Security validation failed. No zip created, nothing deployed." -ForegroundColor Red
    exit 1
}

# --- CREATE ZIP ---
Write-Host "`n[2/4] Creating deployment package..." -ForegroundColor Yellow
if (Test-Path $zipName) { Remove-Item $zipName }
python (Join-Path $PSScriptRoot "create_backend_zip.py")
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Zip creation failed." -ForegroundColor Red
    exit 1
}

# --- CLEAR WEBSITE_RUN_FROM_PACKAGE ---
Write-Host "`n[3/4] Clearing WEBSITE_RUN_FROM_PACKAGE setting..." -ForegroundColor Yellow
az functionapp config appsettings delete `
    --name $appName `
    --resource-group $resourceGroup `
    --setting-names WEBSITE_RUN_FROM_PACKAGE `
    --output none

# --- DEPLOY ---
Write-Host "`n[4/4] Deploying to Azure..." -ForegroundColor Yellow
az functionapp deployment source config-zip `
    --resource-group $resourceGroup `
    --name $appName `
    --src $zipName `
    --build-remote true `
    --timeout 600

if ($LASTEXITCODE -eq 0) {
    Write-Host "`nDeployment successful!" -ForegroundColor Green
    # Clean up local zip after successful deploy
    Remove-Item $zipName -ErrorAction SilentlyContinue
    Write-Host "Local zip removed."
} else {
    Write-Host "`nDeployment FAILED (exit code $LASTEXITCODE)" -ForegroundColor Red
    Write-Host "The zip has NOT been deleted - inspect $zipName before retrying."
    exit $LASTEXITCODE
}
