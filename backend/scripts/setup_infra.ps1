# Setup Infrastructure for Summit Sync (US 2 Region)
$resourceGroup = "rg-summitos-us2"
$location = "eastus2"
$suffix = Get-Random -Minimum 1000 -Maximum 9999
$storageName = "summitstoreus2$suffix"
$sqlServerName = "summitsqlus2$suffix"
$dbName = "SummitMediaDB"
$functionAppName = "summitsyncfuncus2$suffix"
$storageSku = "Standard_LRS"
$sqlAdminUser = "summitadmin"
$sqlAdminPass = -join ((33..126) | Get-Random -Count 20 | % {[char]$_}) # Simple generation, ensure requirements met

Write-Host "--- Summit Sync Infrastructure Setup (US 2) ---"
Write-Host "Region: $location"
Write-Host "Resource Group: $resourceGroup"
Write-Host "Admin User: $sqlAdminUser"
Write-Host "Admin Pass: $sqlAdminPass"

# 1. Create Resource Group
Write-Host "Creating Resource Group..."
az group create --name $resourceGroup --location $location

# 2. Create Storage Account
Write-Host "Creating Storage Account: $storageName..."
az storage account create --name $storageName --resource-group $resourceGroup --location $location --sku $storageSku

# 3. Create SQL Server
Write-Host "Creating SQL Server: $sqlServerName..."
az sql server create --name $sqlServerName --resource-group $resourceGroup --location $location --admin-user $sqlAdminUser --admin-password $sqlAdminPass

# 4. Create SQL Database
Write-Host "Creating SQL Database: $dbName..."
az sql db create --resource-group $resourceGroup --server $sqlServerName --name $dbName --service-objective Basic

# 5. Allow Azure Services to access SQL (Firewall rule)
Write-Host "Configuring SQL Firewall (Allow Azure Services)..."
az sql server firewall-rule create --resource-group $resourceGroup --server $sqlServerName --name "AllowAzureServices" --start-ip-address 0.0.0.0 --end-ip-address 0.0.0.0

# 6. Create Function App (Consumption Plan, Linux or Windows? Python requires Linux usually for Consumption is better, but Windows works too. Defaulting to Linux for Python)
# Note: Function App names must be globally unique
Write-Host "Creating Function App: $functionAppName..."
az functionapp create --resource-group $resourceGroup --consumption-plan-location $location --runtime python --runtime-version 3.10 --functions-version 4 --name $functionAppName --storage-account $storageName --os-type Linux

# 7. Output Configuration
$storageConnectionString = az storage account show-connection-string --name $storageName --resource-group $resourceGroup --query connectionString --output tsv
$sqlConnectionString = "Driver={ODBC Driver 18 for SQL Server};Server=tcp:$sqlServerName.database.windows.net,1433;Database=$dbName;Uid=$sqlAdminUser;Pwd=$sqlAdminPass;Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"

Write-Host "`n--- CONFIGURATION STRINGS ---"
Write-Host "Storage Connection String:"
Write-Host $storageConnectionString
Write-Host "`nSQL Connection String:"
Write-Host $sqlConnectionString
Write-Host "`n-----------------------------"
Write-Host "Save these credentials securely!"
