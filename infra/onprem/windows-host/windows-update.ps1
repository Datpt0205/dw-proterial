# Installs every pending Windows software update (drivers stay excluded by
# 01's policy) and reports whether a restart is needed. It never restarts: a
# person does that in the agreed window, and DW stops and starts cleanly
# (drilled 2026-11-16). For the monthly window, or a fresh host.
#
# The Windows Update API refuses to download in a remote (SSH) session, so run
# it through the one-shot task it registers for itself:
#   powershell -File windows-update.ps1 -ViaTask
# Output: C:\ProgramData\DW\windows-update.log

param([switch]$ViaTask)
$ErrorActionPreference = 'Stop'
$log = 'C:\ProgramData\DW\windows-update.log'
New-Item -ItemType Directory -Force (Split-Path $log) | Out-Null

if ($ViaTask) {
    $self = $MyInvocation.MyCommand.Path
    $a = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$self`""
    $p = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
    Register-ScheduledTask -TaskName 'DW-Windows-Update' -Action $a -Principal $p -Force | Out-Null
    Start-ScheduledTask -TaskName 'DW-Windows-Update'
    Write-Host "Started; follow $log"
    exit 0
}

function Log([string]$m) { "$(Get-Date -Format o) $m" | Add-Content -Path $log -Encoding utf8 }
try {
    Log 'searching'
    $session  = New-Object -ComObject Microsoft.Update.Session
    $searcher = $session.CreateUpdateSearcher()
    $found    = $searcher.Search("IsInstalled=0 and Type='Software' and IsHidden=0").Updates
    Log "found $($found.Count)"
    if ($found.Count -eq 0) { Log 'DONE nothing to install'; exit 0 }
    $list = New-Object -ComObject Microsoft.Update.UpdateColl
    foreach ($u in $found) {
        if (-not $u.EulaAccepted) { $u.AcceptEula() }
        [void]$list.Add($u); Log "  - $($u.Title)"
    }
    $dl = $session.CreateUpdateDownloader(); $dl.Updates = $list
    Log "download result $($dl.Download().ResultCode)"
    $inst = $session.CreateUpdateInstaller(); $inst.Updates = $list
    $r = $inst.Install()
    Log "install result $($r.ResultCode) (2 = succeeded), reboot required: $($r.RebootRequired)"
    Log "DONE"
} catch {
    Log "FAILED $($_.Exception.Message)"
    exit 1
}
