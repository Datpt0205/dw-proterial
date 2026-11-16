# B:\DW-Backup shared to the DW VM over SMB (encrypted), for the VM's nightly
# backup and its WAL archive. Run as Administrator. Idempotent.
#
# One local account, `dwbackup`, may write there and do nothing else. Its
# password is made here, kept in C:\ProgramData\DW\backup-smb.cred (readable by
# Administrators and SYSTEM only) and never printed; the VM gets it by a pipe.
# The host watchdog reads B:\DW-Backup\status to tell whether backups are fresh.

$ErrorActionPreference = 'Stop'
$dir   = 'B:\DW-Backup'
$share = 'DW-Backup'
$user  = 'dwbackup'
$cred  = 'C:\ProgramData\DW\backup-smb.cred'

New-Item -ItemType Directory -Force $dir, 'C:\ProgramData\DW' | Out-Null

# --- the account -----------------------------------------------------------------
if (-not (Get-LocalUser -Name $user -ErrorAction SilentlyContinue)) {
    $bytes = New-Object byte[] 30
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $plain = [Convert]::ToBase64String($bytes).Replace('+', 'A').Replace('/', 'b').TrimEnd('=')
    $secure = ConvertTo-SecureString $plain -AsPlainText -Force
    New-LocalUser -Name $user -Password $secure -PasswordNeverExpires -UserMayNotChangePassword `
        -Description 'DW VM backup writer (SMB only)' | Out-Null
    Set-Content -Path $cred -Value $plain -Encoding ascii -NoNewline
    icacls.exe $cred /inheritance:r /grant '*S-1-5-32-544:F' /grant '*S-1-5-18:F' | Out-Null
    Remove-Variable plain
}

# --- folder rights: Administrators and SYSTEM full, dwbackup modify ------------------
icacls.exe $dir /inheritance:r /grant '*S-1-5-32-544:(OI)(CI)F' /grant '*S-1-5-18:(OI)(CI)F' `
    /grant "${user}:(OI)(CI)M" | Out-Null

# --- the share, encrypted, for dwbackup only ----------------------------------------
if (-not (Get-SmbShare -Name $share -ErrorAction SilentlyContinue)) {
    New-SmbShare -Name $share -Path $dir -ChangeAccess $user -EncryptData $true `
        -Description 'DW VM backups' | Out-Null
}
Set-SmbShare -Name $share -EncryptData $true -Force

# --- firewall: SMB from the local network only ---------------------------------------
if (-not (Get-NetFirewallRule -Name 'dw-backup-smb' -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -Name 'dw-backup-smb' -DisplayName 'DW backup share (SMB)' -Direction Inbound `
        -Protocol TCP -LocalPort 445 -RemoteAddress LocalSubnet -Action Allow -Profile Any | Out-Null
}

Get-SmbShare -Name $share | Format-List Name, Path, EncryptData
Get-SmbShareAccess -Name $share | Format-Table AccountName, AccessRight -AutoSize
