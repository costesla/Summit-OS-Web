$appName = "summitos-api"
$resourceGroup = "rg-summitos-prod"
$zipName = "backend_deploy.zip"

Write-Host "Preparing deployment for $appName (Monorepo Backend)..."

# Remove old zip if exists
if (Test-Path $zipName) { Remove-Item $zipName }

# Create Zip using Python script (preserves structure correctly)
Write-Host "Zipping files from /backend using python script..."
python create_backend_zip.py

# Clear WEBSITE_RUN_FROM_PACKAGE first to avoid read-only mount issues
Write-Host "Clearing WEBSITE_RUN_FROM_PACKAGE setting..."
az functionapp config appsettings delete --name $appName --resource-group $resourceGroup --setting-names WEBSITE_RUN_FROM_PACKAGE

# Deploy with remote build
Write-Host "Deploying to Azure with remote build..."
az functionapp deployment source config-zip --resource-group $resourceGroup --name $appName --src $zipName --build-remote true --timeout 600

if ($LASTEXITCODE -eq 0) {
    Write-Host "Deployment successful!" -ForegroundColor Green
} else {
    Write-Host "Deployment failed with exit code $LASTEXITCODE" -ForegroundColor Red
}

