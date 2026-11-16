# Shows the `dwmail` password to an administrator AT THE CONSOLE (or in their
# own RDP session), when someone must sign in to Windows as dwmail to set up
# OneDrive. Never run it through a remote tool whose output is logged or sent
# elsewhere (a chat, a CI log). Run as Administrator.
Add-Type -AssemblyName System.Security
$blob = [Convert]::FromBase64String((Get-Content 'C:\ProgramData\DW\dwmail.cred' -Raw).Trim())
[Text.Encoding]::UTF8.GetString([Security.Cryptography.ProtectedData]::Unprotect($blob, $null, 'LocalMachine'))
