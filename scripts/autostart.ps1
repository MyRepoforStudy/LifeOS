<#
.SYNOPSIS
    Start LifeOS automatically when you sign in to Windows (Task Scheduler, current user).

        powershell -ExecutionPolicy Bypass -File .\scripts\autostart.ps1            # enable
        powershell -ExecutionPolicy Bypass -File .\scripts\autostart.ps1 -Disable   # remove the task

    The task runs scripts\prod.ps1 hidden: PostgreSQL, the daily backup and the API.
#>
param([switch]$Disable)

$ErrorActionPreference = 'Stop'
$TaskName = 'LifeOS'

if ($Disable) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host 'Autostart removed.'
    }
    else {
        Write-Host 'Autostart was not enabled.'
    }
    return
}

$script = Join-Path $PSScriptRoot 'prod.ps1'
$action = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0) -StartWhenAvailable
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Description 'Starts LifeOS (PostgreSQL, daily backup, API) at sign-in.' -Force | Out-Null
Write-Host "Autostart enabled: task '$TaskName' runs $script at sign-in."
