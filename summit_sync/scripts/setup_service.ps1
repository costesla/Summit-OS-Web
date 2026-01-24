# setup_service.ps1
# This script register the Summit Sync local_watcher.py as a Windows Scheduled Task.

$ServiceName = "SummitSyncWatcher"
$PythonExe = (Get-Command python).Source
$ScriptPath = "c:\Users\PeterTeehan\OneDrive - COS Tesla LLC\COS Tesla - Website\Summit-OS-Web-master\summit_sync\local_watcher.py"
$WorkingDir = "c:\Users\PeterTeehan\OneDrive - COS Tesla LLC\COS Tesla - Website\Summit-OS-Web-master\summit_sync"
$LogFile = "$WorkingDir\watcher_service.log"

if (-not $PythonExe) {
    Write-Error "Python not found in PATH. Please install Python."
    exit
}

Write-Host "Registering $ServiceName..." -ForegroundColor Cyan

# Action: Run python with the script path
$Action = New-ScheduledTaskAction -Execute $PythonExe -Argument "$ScriptPath" -WorkingDirectory $WorkingDir

# Trigger: At startup
$Trigger = New-ScheduledTaskTrigger -AtStartup

# Settings: Restart on failure, allow start if on batteries, stay running permanently
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Hours 0)

# Register the Task
# We use 'S-1-5-18' (SYSTEM) to run hidden and 24/7 without a console session
Register-ScheduledTask -TaskName $ServiceName -Action $Action -Trigger $Trigger -Settings $Settings -Description "Background watcher for Summit Sync screenshots" -User "SYSTEM" -Force

Write-Host "Service $ServiceName registered successfully!" -ForegroundColor Green
Write-Host "Note: Since it's set to run as SYSTEM at startup, you may need to start it manually once or reboot."
Write-Host "To start now, run: Start-ScheduledTask -TaskName '$ServiceName'"
