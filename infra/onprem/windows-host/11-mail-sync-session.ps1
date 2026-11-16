# The Windows session OneDrive runs in, for the mail drop (infra/onprem/README.md,
# "Mail without access to Microsoft 365"): OneDrive syncs the Team's DW-mail
# folder only inside a signed-in session, so the host keeps one.
#   - OneDrive installed for all users (Microsoft's signed installer);
#   - a standard local user `dwmail` (not an administrator), signed in at every
#     boot by Sysinternals Autologon (password kept as an LSA secret), and its
#     screen locked at once by a logon task;
#   - a disconnected Remote Desktop session is never ended, so leaving by
#     Disconnect keeps OneDrive running (never Sign out);
#   - Files On-Demand off, so every mail file is on disk for the VM to read.
# The password is random, never printed here; an administrator reads it at the
# console with `show-dwmail-password.ps1` when someone must sign in to OneDrive
# as the Team's owner (RDP over Tailscale as dwmail, then Disconnect).
# Run as Administrator. Idempotent. Installers in C:\dw-setup\installers,
# fetched and signature-checked first.

$ErrorActionPreference = 'Stop'
$inst = 'C:\dw-setup\installers'
$user = 'dwmail'
$cred = 'C:\ProgramData\DW\dwmail.cred'
Add-Type -AssemblyName System.Security

foreach ($f in "$inst\OneDriveSetup.exe", "$inst\AutoLogon\Autologon64.exe") {
    $s = Get-AuthenticodeSignature $f
    if ($s.Status -ne 'Valid' -or $s.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation') { throw "bad signature on $f" }
}

# --- OneDrive for all users -------------------------------------------------------
if (-not (Test-Path 'C:\Program Files\Microsoft OneDrive\OneDrive.exe')) {
    # WaitForExit, not -Wait: -Wait also waits on the OneDrive.Sync.Service the
    # installer leaves running, i.e. forever (measured 2026-11-16).
    $p = Start-Process "$inst\OneDriveSetup.exe" -ArgumentList '/allusers', '/silent' -PassThru
    $p.WaitForExit()
    if ($p.ExitCode -ne 0) { throw "OneDriveSetup exited $($p.ExitCode)" }
}
$od = 'HKLM:\SOFTWARE\Policies\Microsoft\OneDrive'
New-Item -Path $od -Force | Out-Null
Set-ItemProperty -Path $od -Name FilesOnDemandEnabled -Type DWord -Value 0

# --- the user and its password (made once, kept encrypted for this machine) --------
if (-not (Get-LocalUser -Name $user -ErrorAction SilentlyContinue)) {
    $bytes = New-Object byte[] 24
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $plain = 'Dw-' + [Convert]::ToBase64String($bytes).Replace('+', 'x').Replace('/', 'y').TrimEnd('=')
    New-LocalUser -Name $user -Password (ConvertTo-SecureString $plain -AsPlainText -Force) `
        -PasswordNeverExpires -UserMayNotChangePassword -Description 'DW mail drop: OneDrive session' | Out-Null
    $blob = [Security.Cryptography.ProtectedData]::Protect([Text.Encoding]::UTF8.GetBytes($plain), $null, 'LocalMachine')
    Set-Content -Path $cred -Value ([Convert]::ToBase64String($blob)) -Encoding ascii
    icacls.exe $cred /inheritance:r /grant '*S-1-5-32-544:F' /grant '*S-1-5-18:F' | Out-Null
    Remove-Variable plain
}
Add-LocalGroupMember -SID 'S-1-5-32-555' -Member $user -ErrorAction SilentlyContinue   # Remote Desktop Users

# --- sign it in at every boot ----------------------------------------------------------
$plain = [Text.Encoding]::UTF8.GetString([Security.Cryptography.ProtectedData]::Unprotect(
            [Convert]::FromBase64String((Get-Content $cred -Raw).Trim()), $null, 'LocalMachine'))
& "$inst\AutoLogon\Autologon64.exe" $user $env:COMPUTERNAME $plain /accepteula | Out-Null
Remove-Variable plain

# --- lock its screen as soon as it signs in ---------------------------------------------
$a = New-ScheduledTaskAction -Execute 'rundll32.exe' -Argument 'user32.dll,LockWorkStation'
$t = New-ScheduledTaskTrigger -AtLogOn -User "$env:COMPUTERNAME\$user"
$p = New-ScheduledTaskPrincipal -UserId "$env:COMPUTERNAME\$user" -LogonType Interactive
Register-ScheduledTask -TaskName 'DW-Lock-dwmail' -Action $a -Trigger $t -Principal $p -Force | Out-Null

# --- start OneDrive in that session ---------------------------------------------------------
# The per-machine installer registers its startup task only for the account that
# ran it (Administrator), so dwmail gets its own (measured 2026-11-16).
$a = New-ScheduledTaskAction -Execute 'C:\Program Files\Microsoft OneDrive\OneDrive.exe' -Argument '/background'
Register-ScheduledTask -TaskName 'DW-OneDrive-dwmail' -Action $a -Trigger $t -Principal $p -Force | Out-Null

# --- no "Sign out" in dwmail's own menus ----------------------------------------------------
# Signing dwmail out stops OneDrive until the next boot (autologon runs only at
# boot), so its Start menu and Ctrl+Alt+Del offer no Sign out: per-user policy
# NoLogoff in dwmail's hive, loaded if dwmail is not signed in. An administrator
# can still end the session; the watchdog then says so.
$sid = (Get-LocalUser -Name $user).SID.Value
$loadedHere = $false
if (-not (Test-Path "Registry::HKEY_USERS\$sid")) {
    $profile = (Get-CimInstance Win32_UserProfile | Where-Object SID -eq $sid).LocalPath
    if ($profile) { reg.exe load "HKU\$sid" "$profile\NTUSER.DAT" | Out-Null; $loadedHere = $true }
}
if (Test-Path "Registry::HKEY_USERS\$sid") {
    $pol = "Registry::HKEY_USERS\$sid\Software\Microsoft\Windows\CurrentVersion\Policies\Explorer"
    New-Item -Path $pol -Force | Out-Null
    Set-ItemProperty -Path $pol -Name NoLogoff -Type DWord -Value 1
    if ($loadedHere) { [GC]::Collect(); reg.exe unload "HKU\$sid" | Out-Null }
} else {
    Write-Warning "dwmail has no profile yet (never signed in): run this again after its first sign-in"
}

# --- a disconnected session is never ended (OneDrive keeps running) ----------------------
$ts = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows NT\Terminal Services'
New-Item -Path $ts -Force | Out-Null
Set-ItemProperty -Path $ts -Name MaxDisconnectionTime -Type DWord -Value 0
Set-ItemProperty -Path $ts -Name MaxIdleTime -Type DWord -Value 0
Set-ItemProperty -Path $ts -Name fResetBroken -Type DWord -Value 0

$w = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon'
"OneDrive: " + (Test-Path 'C:\Program Files\Microsoft OneDrive\OneDrive.exe') + ", Files On-Demand off"
"Autologon: user=$($w.DefaultUserName) enabled=$($w.AutoAdminLogon) (password as LSA secret, not in the registry: $(-not $w.DefaultPassword))"
"Lock task: " + (Get-ScheduledTask -TaskName 'DW-Lock-dwmail').State
