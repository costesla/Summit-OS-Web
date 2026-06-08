$appName = "summitsyncfuncus23436"
$resourceGroup = "rg-summitos-us2"
$zipName = "summit_sync_deploy_pkg.zip"

Write-Host "Preparing deployment for $appName..."

# Remove old zip if exists
if (Test-Path $zipName) { Remove-Item $zipName }

# Create Zip using Python script (preserves structure and is extremely fast)
Write-Host "Zipping files using python script..."
..\.venv\Scripts\python.exe create_deploy_zip.py

# Deploy
Write-Host "Deploying to Azure..."
az functionapp deployment source config-zip --resource-group $resourceGroup --name $appName --src $zipName

Write-Host "Deployment command sent."
