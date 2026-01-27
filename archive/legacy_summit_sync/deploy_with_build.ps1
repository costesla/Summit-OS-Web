# Deploy Azure Function with Remote Build
$ErrorActionPreference = "Stop"

$functionAppName = "summitsyncfuncus23436"
$resourceGroup = "rg-summitos-us2"

Write-Host "Preparing deployment for $functionAppName..." -ForegroundColor Cyan

# Create deployment package
Write-Host "Zipping files..."
$zipPath = "$env:TEMP\summit_sync_deploy.zip"
if (Test-Path $zipPath) { Remove-Item $zipPath }

# Zip the current directory
Compress-Archive -Path * -DestinationPath $zipPath -Force

Write-Host "Deploying to Azure with remote build..."

# Use deployment source config-zip which properly triggers Oryx build
az functionapp deployment source config-zip `
    --resource-group $resourceGroup `
    --name $functionAppName `
    --src $zipPath `
    --build-remote true `
    --timeout 600

if ($LASTEXITCODE -eq 0) {
    Write-Host "Deployment successful!" -ForegroundColor Green
    Write-Host "Syncing function triggers..."
    az functionapp function sync --name $functionAppName --resource-group $resourceGroup
}
else {
    Write-Host "Deployment failed with exit code $LASTEXITCODE" -ForegroundColor Red
}

# Cleanup
Remove-Item $zipPath
