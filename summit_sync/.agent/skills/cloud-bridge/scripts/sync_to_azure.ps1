<#
.SYNOPSIS
    Cloud Bridge: Sync to Azure Blob Storage
    Uses 'az storage blob upload-batch' with retry logic and directory monitoring.

.DESCRIPTION
    This script uploads files from a local directory to an Azure Blob Storage container.
    It supports a one-time sync or a continuous watch mode.

.PARAMETER Source
    The local directory to upload from.

.PARAMETER Container
    The Azure Blob Storage container name (Default: Thor_Backups).

.PARAMETER Watch
    If specified, the script will monitor the directory and sync periodically.

.EXAMPLE
    .\sync_to_azure.ps1 -Source "C:\Photos" -Container "my-backups" -Watch
#>

param (
    [Parameter(Mandatory = $true)]
    [string]$Source,

    [string]$Container = "thor-backups",

    [string]$Pattern = "*",

    [switch]$Watch,
    
    [string]$ConnectionString = $env:AZUREWEBJOBSSTORAGE,

    [int]$MaxRetries = 5
)

function Start-BatchUpload {
    $attempt = 1
    $success = $false

    Write-Host "[$(Get-Date)] Starting upload from '$Source' to '$Container' with pattern '$Pattern'..." -ForegroundColor Cyan
    
    if (-not $ConnectionString) {
        Write-Error "Connection String is missing. Please provide -ConnectionString or set env:AZUREWEBJOBSSTORAGE"
        return
    }

    # Check if container exists, create if not
    Write-Host "Verifying container '$Container'..." -ForegroundColor Gray
    $containerExists = az storage container exists --name $Container --connection-string "$ConnectionString" --query exists --output tsv 2>$null
    if ($containerExists -ne "true") {
        Write-Host "Container '$Container' not found. Creating..." -ForegroundColor Yellow
        az storage container create --name $Container --connection-string "$ConnectionString" --output none
    }

    while ($attempt -le $MaxRetries) {
        try {
            # Execute az storage blob upload-batch
            $output = az storage blob upload-batch `
                --connection-string "$ConnectionString" `
                --destination $Container `
                --source "$Source" `
                --pattern "$Pattern" `
                --overwrite true `
                --output table 2>&1

            if ($LASTEXITCODE -eq 0) {
                Write-Host "[$(Get-Date)] Upload successful." -ForegroundColor Green
                Write-Host $output
                $success = $true
                break
            }
            else {
                throw $output
            }
        }
        catch {
            Write-Host "[$(Get-Date)] Error uploading (Attempt $attempt/$MaxRetries)." -ForegroundColor Red
            Write-Host "Output: $_"
            
            # Exponential backoff
            $sleepTime = [math]::Pow(2, $attempt)
            Write-Host "Retrying in $sleepTime seconds..." -ForegroundColor Yellow
            Start-Sleep -Seconds $sleepTime
            $attempt++
        }
    }

    if (-not $success) {
        Write-Host "[$(Get-Date)] CRITICAL: Upload failed after $MaxRetries attempts." -ForegroundColor Red
    }
}

# Main Execution Flow
if ($Watch) {
    Write-Host "Starting Watch Mode on '$Source'..." -ForegroundColor Magenta
    Write-Host "Press [CTRL+C] to stop."
    
    # Simple polling loop (every 30 seconds)
    while ($true) {
        Start-BatchUpload
        Start-Sleep -Seconds 30
    }
}
else {
    Start-BatchUpload
}
