$appName       = "summitsyncfuncus23436"
$resourceGroup = "rg-summitos-us2"
$zipName       = "summit_sync_deploy_pkg.zip"

Write-Host "=== SummitSync Deploy ===" -ForegroundColor Cyan
Write-Host "Target: $appName ($resourceGroup)"

# --- SECURITY GATE ---
Write-Host "`n[1/3] Running pre-zip security validation..." -ForegroundColor Yellow
$validator = Join-Path $PSScriptRoot "..\backend\validate_before_zip.py"
$validator = [System.IO.Path]::GetFullPath($validator)
if (-not (Test-Path $validator)) {
    Write-Host "ERROR: validate_before_zip.py not found at $validator. Aborting." -ForegroundColor Red
    exit 1
}
python $validator --dir $PSScriptRoot
if ($LASTEXITCODE -ne 0) {
    Write-Host "ABORT: Security validation failed. No zip created, nothing deployed." -ForegroundColor Red
    exit 1
}

# --- CREATE ZIP ---
Write-Host "`n[2/3] Creating deployment package..." -ForegroundColor Yellow
if (Test-Path $zipName) { Remove-Item $zipName }
python (Join-Path $PSScriptRoot "create_deploy_zip.py")
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Zip creation failed." -ForegroundColor Red
    exit 1
}

# --- DEPLOY ---
Write-Host "`n[3/3] Deploying to Azure..." -ForegroundColor Yellow
az functionapp deployment source config-zip `
    --resource-group $resourceGroup `
    --name $appName `
    --src $zipName

if ($LASTEXITCODE -eq 0) {
    Write-Host "`nDeployment successful!" -ForegroundColor Green
    Remove-Item $zipName -ErrorAction SilentlyContinue
    Write-Host "Local zip removed."
} else {
    Write-Host "`nDeployment FAILED (exit code $LASTEXITCODE)" -ForegroundColor Red
    exit $LASTEXITCODE
}
