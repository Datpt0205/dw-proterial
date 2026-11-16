# The DW host's own watchdog: the one observer that stands outside the VM, so it
# can see the VM, Strata, Tailscale and the disks when nothing inside the VM
# can. Run by the "DW-Host-Watchdog" task (SYSTEM, at startup and every 5 min;
# 07-watchdog.ps1 registers it).
#
# Each check is ok or failing. It repairs only what is safe to repair, and mails
# on a change of state (failing, then recovered), never on every run, so a long
# outage is one mail and one "recovered" mail. Without a mail setting it logs only.

$ErrorActionPreference = 'Continue'
$root      = 'C:\ProgramData\DW'
$log       = Join-Path $root 'watchdog.log'
$stateFile = Join-Path $root 'watchdog-state.json'
$mailFile  = Join-Path $root 'alert-mail.json'
$vmName    = 'dw-vm'
New-Item -ItemType Directory -Force $root | Out-Null
if ((Test-Path $log) -and (Get-Item $log).Length -gt 1MB) { Move-Item $log "$log.1" -Force }
function Log([string]$m) { "$(Get-Date -Format o) $m" | Add-Content -Path $log -Encoding utf8 }

$state = @{}
if (Test-Path $stateFile) {
    try { (Get-Content $stateFile -Raw | ConvertFrom-Json).PSObject.Properties | ForEach-Object { $state[$_.Name] = $_.Value } } catch { }
}

# A mail that cannot go now (at boot the network is not up yet: measured, the
# "OK again" of the restart drill was lost) waits in the state and is retried
# on every round until it goes.
function Send-Alert([string]$subject, [string]$body) {
    if (-not (Test-Path $mailFile)) { Log "no mail setting; not sent: $subject"; return }
    if (-not (Send-Now $subject $body)) {
        $q = @($state['mail.pending']) | Where-Object { $_ }
        $state['mail.pending'] = @($q) + @([pscustomobject]@{ subject = $subject; body = "$body`n`n(queued $(Get-Date -Format o))" })
    }
}
function Send-Now([string]$subject, [string]$body) {
    try {
        Add-Type -AssemblyName System.Security
        $cfg  = Get-Content $mailFile -Raw | ConvertFrom-Json
        $pass = [Text.Encoding]::UTF8.GetString([Security.Cryptography.ProtectedData]::Unprotect(
                    [Convert]::FromBase64String($cfg.password_dpapi), $null,
                    [Security.Cryptography.DataProtectionScope]::LocalMachine))
        $smtp = New-Object Net.Mail.SmtpClient($cfg.smtp_host, [int]$cfg.smtp_port)
        $smtp.EnableSsl = $true
        $smtp.Credentials = New-Object Net.NetworkCredential($cfg.user, $pass)
        $msg = New-Object Net.Mail.MailMessage($cfg.from, $cfg.to, "[DW $env:COMPUTERNAME] $subject", $body)
        $smtp.Send($msg)
        $msg.Dispose(); $smtp.Dispose()
        Log "mail sent: $subject"
        return $true
    } catch { Log "mail failed: $subject :: $($_.Exception.Message)"; return $false }
}

# Retry what earlier rounds could not send, oldest first; keep what still fails.
if ((Test-Path $mailFile) -and $state['mail.pending']) {
    $left = @()
    foreach ($m in @($state['mail.pending'])) {
        if (-not $m) { continue }
        if (-not (Send-Now $m.subject $m.body)) { $left += $m }
    }
    $state['mail.pending'] = $left
}

# The first minutes after boot: Hyper-V is still starting the VM and Strata waits
# on purpose, so those two are not judged yet (measured: a check at boot saw the
# VM "Off" and called Start-VM over Hyper-V's own start).
$hostUpMin = ((Get-Date) - (Get-CimInstance Win32_OperatingSystem).LastBootUpTime).TotalMinutes
$booting = $hostUpMin -lt 5

# One result per check: ok, or a sentence saying what is wrong.
# A check needing N failures in a row before it counts keeps a slow boot or a
# brief blip from becoming an alert or a restart.
function Report([string]$name, [bool]$ok, [string]$problem, [int]$after = 1) {
    $prev  = [string]$state["$name.status"]
    $count = [int]$state["$name.count"]
    if ($ok) {
        if ($prev -eq 'failing') { Send-Alert "OK again: $name" "$name is working again. $(Get-Date -Format o)" ; Log "recovered: $name" }
        $state["$name.status"] = 'ok'; $state["$name.count"] = 0
        return $false
    }
    $count++; $state["$name.count"] = $count
    Log "check failed ($count): $name :: $problem"
    if ($count -ge $after -and $prev -ne 'failing') {
        $state["$name.status"] = 'failing'
        Send-Alert "PROBLEM: $name" "$problem`n`nHost: $env:COMPUTERNAME`nTime: $(Get-Date -Format o)`nLog: $log"
    }
    return ($count -ge $after)
}

# --- 1. The VM is running ---------------------------------------------------------
$vm = Get-VM -Name $vmName -ErrorAction SilentlyContinue
if ($booting) {
    Log "host up $([math]::Round($hostUpMin, 1)) min: VM and Strata not judged yet"
} elseif (-not $vm) {
    [void](Report 'vm' $false "VM $vmName does not exist on this host.")
} elseif ($vm.State -ne 'Running') {
    if (Report 'vm' $false "VM $vmName was $($vm.State); the watchdog started it.") { }
    Start-VM -Name $vmName -ErrorAction SilentlyContinue
} else {
    [void](Report 'vm' $true '')
    # --- 2. ...and answering (Hyper-V heartbeat), after its first 10 minutes ------
    if ($vm.Uptime.TotalMinutes -gt 10) {
        $hb = (Get-VMIntegrationService -VMName $vmName -Name 'Heartbeat').PrimaryStatusDescription
        if (Report 'vm-heartbeat' ($hb -eq 'OK') "VM $vmName is running but its heartbeat is '$hb' for 15 minutes; the watchdog restarted it." 3) {
            if ([int]$state['vm-heartbeat.count'] -eq 3) { Restart-VM -Name $vmName -Force; Log 'VM restarted (no heartbeat)' }
        }
    }
}

# --- 3. Strata answers (its own task relaunches it; this only tells a person) ------
$strataTask = Get-ScheduledTask -TaskName 'DW-Strata' -ErrorAction SilentlyContinue
$strataOk = $false
try { $strataOk = ((Invoke-WebRequest -UseBasicParsing -TimeoutSec 15 -Uri 'http://127.0.0.1:8080/health').StatusCode -eq 200) } catch { }
if ($booting) {
    # judged from the next round on
} elseif ($strataOk -or ($strataTask -and $strataTask.State -eq 'Running' -and -not $state['strata.served'])) {
    # Not failing while the very first launch is still downloading the model.
    if ($strataOk) { $state['strata.served'] = $true }
    [void](Report 'strata' $true '')
} else {
    [void](Report 'strata' $false 'Strata (the model) has not answered /health for 15 minutes. Its DW-Strata task keeps trying to start it; see C:\Strata\dw-logs.' 3)
}

# --- 4. Tailscale is connected (the only way in for remote support) ---------------
$ts = 'C:\Program Files\Tailscale\tailscale.exe'
$tsState = ''
try { $tsState = (& $ts status --json | ConvertFrom-Json).BackendState } catch { }
if ($tsState -ne 'Running') {
    if (Report 'tailscale' $false "Tailscale is '$tsState'; the watchdog restarted its service. Remote support is cut off until it reconnects." 2) {
        Restart-Service Tailscale -ErrorAction SilentlyContinue
    }
} else { [void](Report 'tailscale' $true '') }

# --- 5. Disks keep 15 % free --------------------------------------------------------
foreach ($d in 'C', 'V', 'B') {
    $v = Get-Volume -DriveLetter $d -ErrorAction SilentlyContinue
    if (-not $v) { continue }
    $free = [math]::Round(100 * $v.SizeRemaining / $v.Size, 1)
    [void](Report "disk-$d" ($free -ge 15) "Drive ${d}: has $free % free ($([math]::Round($v.SizeRemaining/1GB)) GB).")
}

# --- 5b. The host keeps memory to spare ------------------------------------------------
# Strata keeps the model's experts in RAM and the VM holds a fixed 16 GB, so the
# host runs close to full by design. Below 2 GB for 15 minutes, Windows starts
# trimming Strata's memory (slow answers) or a restart of the VM may not find
# its 16 GB.
$mem = Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory
$availMB = [int]$mem.AvailableMBytes
[void](Report 'host-memory' ($availMB -ge 2048) "The host has only $availMB MB of memory available. Strata may slow down, and the VM may not start again after a stop." 3)
# Commit charge: what Windows has promised against RAM + page file. At the limit
# every new allocation fails, in any process (Strata alone commits ~59 GB).
$commitPct = [math]::Round(100 * $mem.CommittedBytes / $mem.CommitLimit, 1)
[void](Report 'host-commit' ($commitPct -lt 92) "Windows has committed $commitPct % of its memory limit ($([math]::Round($mem.CommittedBytes/1GB)) of $([math]::Round($mem.CommitLimit/1GB)) GB). At 100 % allocations fail in every process." 2)

# --- 5c. Backups are fresh and their restore test passes ------------------------------
# The VM's dw-backup.sh writes B:\DW-Backup\status; it never mails, this does.
# Until backups are installed (no status folder) there is nothing to judge.
$bs = 'B:\DW-Backup\status'
if (Test-Path $bs) {
    function Read-Status([string]$name) {
        $f = Join-Path $bs $name
        if (Test-Path $f) { try { return Get-Content $f -Raw | ConvertFrom-Json } catch { } }
        return $null
    }
    function Hours-Since($s) { if ($s -and $s.time) { return ((Get-Date) - [datetime]$s.time).TotalHours } return [double]::PositiveInfinity }
    $ok = Read-Status 'last-ok.json'; $err = Read-Status 'last-error.json'
    $wal = Read-Status 'last-wal.json'; $ver = Read-Status 'last-verify.json'
    $why = if ($err -and (Hours-Since $err) -lt (Hours-Since $ok)) { " The last run failed: $($err.mode): $($err.error)" } else { '' }
    $h = Hours-Since $ok
    [void](Report 'backup' ($h -lt 26) "No successful nightly backup for $([math]::Round($h)) hours.$why")
    $h = Hours-Since $wal
    [void](Report 'backup-wal' ($h -lt 3) "The WAL archive has not been copied to B: for $([math]::Round($h)) hours; a lost VM would lose more than 15 minutes of work.$why")
    $h = Hours-Since $ver
    [void](Report 'backup-verify' (($h -lt 35 * 24) -and $ver -and $ver.ok) "The monthly restore test has not passed for $([math]::Round($h / 24)) days.$why")
}

# --- 6. A restart Windows has been waiting for over 3 days --------------------------
$pending = Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired'
if ($pending) {
    if (-not $state['reboot.since']) { $state['reboot.since'] = (Get-Date).ToString('o') }
    $days = ((Get-Date) - [datetime]$state['reboot.since']).TotalDays
    [void](Report 'windows-update-restart' ($days -lt 3) "Windows has waited $([math]::Round($days,1)) days to restart after updates. Restart it in the agreed window; DW stops cleanly and comes back.")
} else {
    $state.Remove('reboot.since'); [void](Report 'windows-update-restart' $true '')
}

# --- 7. One mail a day from 08:00: the dead man's switch ------------------------------
# Alerts only say what broke. If this mail does not come, the watchdog, the mail
# or the whole host is down, which no alert from here could ever say.
$today = (Get-Date).ToString('yyyy-MM-dd')
if ((Get-Date).Hour -ge 8 -and $state['daily.sent'] -ne $today) {
    $failing = @($state.Keys | Where-Object { $_ -like '*.status' -and $state[$_] -eq 'failing' } | ForEach-Object { $_ -replace '\.status$', '' })
    $free = (Get-Volume | Where-Object DriveLetter -in 'C', 'V', 'B' |
             ForEach-Object { "$($_.DriveLetter): $([math]::Round($_.SizeRemaining/1GB)) GB free" }) -join ', '
    $vmUp = try { [math]::Round((Get-VM -Name $vmName).Uptime.TotalHours, 1) } catch { '?' }
    $status = if ($failing.Count) { "FAILING: $($failing -join ', ')" } else { 'all checks ok' }
    Send-Alert "daily: $status" "Daily report from the DW host.`n`nChecks: $status`nVM uptime: $vmUp h`nDisks: $free`nStrata serving: $([bool]$state['strata.served'])`n`nIf this mail stops coming, the host or its watchdog is down."
    $state['daily.sent'] = $today
}

$state | ConvertTo-Json -Depth 5 | Set-Content -Path $stateFile -Encoding utf8
