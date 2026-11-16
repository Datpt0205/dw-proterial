# Where the host watchdog mails its alerts. Run it yourself, interactively, as
# Administrator on the host (an `ssh dw-host` session from your own terminal is
# fine): it asks for the SMTP password and stores it encrypted for this machine
# (DPAPI, LocalMachine), so the password never passes through a chat or a file
# in clear. Then it sends one test mail.
#
# Gmail: the password is an App Password (Google Account > Security > 2-Step
# Verification > App passwords), not the account password.

param(
    [Parameter(Mandatory)] [string]$To,
    [string]$From     = $To,
    [string]$User     = $To,
    [string]$SmtpHost = 'smtp.gmail.com',
    [int]$SmtpPort    = 587
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Security
$secure = Read-Host -AsSecureString "SMTP password (App Password) for $User"
$plain  = [Runtime.InteropServices.Marshal]::PtrToStringBSTR([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
$blob   = [Security.Cryptography.ProtectedData]::Protect([Text.Encoding]::UTF8.GetBytes($plain), $null,
            [Security.Cryptography.DataProtectionScope]::LocalMachine)
Remove-Variable plain

New-Item -ItemType Directory -Force 'C:\ProgramData\DW' | Out-Null
$file = 'C:\ProgramData\DW\alert-mail.json'
[ordered]@{
    to = $To; from = $From; user = $User; smtp_host = $SmtpHost; smtp_port = $SmtpPort
    password_dpapi = [Convert]::ToBase64String($blob)
} | ConvertTo-Json | Set-Content -Path $file -Encoding utf8
# Only Administrators and SYSTEM read it (DPAPI LocalMachine lets any local process decrypt).
icacls.exe $file /inheritance:r /grant '*S-1-5-32-544:F' /grant '*S-1-5-18:F' | Out-Null

$cfg  = Get-Content $file -Raw | ConvertFrom-Json
$pass = [Text.Encoding]::UTF8.GetString([Security.Cryptography.ProtectedData]::Unprotect(
            [Convert]::FromBase64String($cfg.password_dpapi), $null, [Security.Cryptography.DataProtectionScope]::LocalMachine))
$smtp = New-Object Net.Mail.SmtpClient($SmtpHost, $SmtpPort)
$smtp.EnableSsl = $true
$smtp.Credentials = New-Object Net.NetworkCredential($User, $pass)
$smtp.Send($From, $To, "[DW $env:COMPUTERNAME] test", "The DW host watchdog can mail you. $(Get-Date -Format o)")
Write-Host "Saved $file and sent a test mail to $To."
