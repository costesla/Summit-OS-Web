$appName = "summitsyncfuncus23436"
$resourceGroup = "rg-summitos-us2"
$zipName = "deploy.zip"

Write-Host "Preparing deployment for $appName..."

# Remove old zip if exists
if (Test-Path $zipName) { Remove-Item $zipName }

# Create Zip (excluding venv, __pycache__, .git, etc.)
# Using 7z or standard Compress-Archive. Compress-Archive is safer standard.
# We need to explicitly include files to avoid zipping the parent folder or unnecessary large folders.
$files = Get-ChildItem -Path . -Exclude ".venv", "venv", "*__pycache__*", "*.zip", ".git", ".vscode", "scripts", "local_watcher.py"

Write-Host "Zipping files..."
Compress-Archive -Path $files -DestinationPath $zipName -Force

# Deploy
Write-Host "Deploying to Azure..."
az functionapp deployment source config-zip --resource-group $resourceGroup --name $appName --src $zipName

Write-Host "Deployment command sent."
