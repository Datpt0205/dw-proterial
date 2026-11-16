# Registers the host watchdog (host-watchdog.ps1): SYSTEM, at startup and every
# 5 minutes. Run as Administrator. Idempotent. Mail is set separately with
# set-alert-mail.ps1; until then the watchdog repairs and logs only.

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$dest = 'C:\ProgramData\DW\host-watchdog.ps1'
New-Item -ItemType Directory -Force 'C:\ProgramData\DW' | Out-Null
Copy-Item (Join-Path $here 'host-watchdog.ps1') $dest -Force

$action    = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$dest`""
$atBoot    = New-ScheduledTaskTrigger -AtStartup
$every5    = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 5)
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$settings  = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable `
                -ExecutionTimeLimit (New-TimeSpan -Minutes 4) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName 'DW-Host-Watchdog' -Action $action -Trigger $atBoot, $every5 `
    -Principal $principal -Settings $settings -Force | Out-Null

Start-ScheduledTask -TaskName 'DW-Host-Watchdog'
Start-Sleep -Seconds 20
Get-ScheduledTaskInfo -TaskName 'DW-Host-Watchdog' | Format-List LastRunTime, LastTaskResult
Get-Content 'C:\ProgramData\DW\watchdog.log' -Tail 10 -ErrorAction SilentlyContinue
Get-Content 'C:\ProgramData\DW\watchdog-state.json' -ErrorAction SilentlyContinue
