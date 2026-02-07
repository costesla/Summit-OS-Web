$appName = "summitos-api"
$resourceGroup = "rg-summitos-prod"
$zipName = "deploy.zip"

Write-Host "Preparing deployment for $appName (Monorepo Backend)..."

# Remove old zip if exists
if (Test-Path $zipName) { Remove-Item $zipName }

# Create Zip using Python script (preserves structure correctly)
Write-Host "Zipping files from /backend using python script..."
python create_backend_zip.py
$zipName = "backend_deploy.zip"

# Deploy
Write-Host "Deploying to Azure..."
az functionapp deployment source config-zip --resource-group $resourceGroup --name $appName --src $zipName

Write-Host "Deployment command sent."
