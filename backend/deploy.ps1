$appName = "summitos-api"
$resourceGroup = "rg-summitos-prod"
$zipName = "deploy.zip"

Write-Host "Preparing deployment for $appName (Monorepo Backend)..."

# Remove old zip if exists
if (Test-Path $zipName) { Remove-Item $zipName }

# Create Zip (Target /backend specifically)
$files = Get-ChildItem -Path backend/* -Exclude ".venv", "venv", "*__pycache__*", "*.zip", ".git", ".vscode", "scripts", "*.bak", ".python_packages", "config"

Write-Host "Zipping files from /backend..."
Compress-Archive -Path $files -DestinationPath $zipName -Force

# Deploy
Write-Host "Deploying to Azure..."
az functionapp deployment source config-zip --resource-group $resourceGroup --name $appName --src $zipName

Write-Host "Deployment command sent."
