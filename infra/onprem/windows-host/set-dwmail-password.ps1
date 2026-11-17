# Sets a new password for `dwmail` everywhere it is kept at once: the Windows
# account, Autologon's LSA secret (or the next boot would not sign it in), and
# the DPAPI copy show-dwmail-password.ps1 reads. The password comes on standard
# input, or is asked for. Run as Administrator.
param([switch]$FromStdin)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Security, System.DirectoryServices.AccountManagement

$plain = if ($FromStdin) { [Console]::In.ReadToEnd().Trim() } else {
    $s = Read-Host -AsSecureString 'New password for dwmail'
    [Runtime.InteropServices.Marshal]::PtrToStringBSTR([Runtime.InteropServices.Marshal]::SecureStringToBSTR($s))
}
if (-not $plain) { throw 'empty password' }

Set-LocalUser -Name dwmail -Password (ConvertTo-SecureString $plain -AsPlainText -Force)
& 'C:\dw-setup\installers\AutoLogon\Autologon64.exe' dwmail $env:COMPUTERNAME $plain /accepteula | Out-Null
$blob = [Security.Cryptography.ProtectedData]::Protect([Text.Encoding]::UTF8.GetBytes($plain), $null, 'LocalMachine')
Set-Content -Path 'C:\ProgramData\DW\dwmail.cred' -Value ([Convert]::ToBase64String($blob)) -Encoding ascii

$ctx = New-Object System.DirectoryServices.AccountManagement.PrincipalContext('Machine')
"Windows accepts the new password: " + $ctx.ValidateCredentials('dwmail', $plain)
$w = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon'
"Autologon: user=$($w.DefaultUserName) enabled=$($w.AutoAdminLogon)"
Remove-Variable plain
