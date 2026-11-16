# Remote Desktop as a second way in, over Tailscale only; and the board's radios
# off. Run as Administrator. Idempotent.
#
# RDP: with Network Level Authentication, and a firewall rule from Tailscale's
# address range (100.64.0.0/10) alone; Windows' own "Remote Desktop" rules stay
# off, so the plant's LAN cannot reach 3389. (Tailscale's client adds its own
# allow rule for its interface: tailnet devices reach every port, so who is in
# the tailnet, and its ACL, is the real control.)
#
# Radios: the MediaTek Wi-Fi and the Bluetooth adapter have no driver on Server
# and no use on a wired server; disabled, they are neither an error in Device
# Manager nor a way in.

$ErrorActionPreference = 'Stop'

$ts = 'HKLM:\System\CurrentControlSet\Control\Terminal Server'
Set-ItemProperty -Path $ts -Name fDenyTSConnections -Value 0
Set-ItemProperty -Path "$ts\WinStations\RDP-Tcp" -Name UserAuthentication -Value 1
Get-NetFirewallRule -DisplayGroup 'Remote Desktop' -ErrorAction SilentlyContinue | Disable-NetFirewallRule
Remove-NetFirewallRule -Name 'dw-rdp-tailscale' -ErrorAction SilentlyContinue
New-NetFirewallRule -Name 'dw-rdp-tailscale' -DisplayName 'DW RDP over Tailscale' -Direction Inbound `
    -Protocol TCP -LocalPort 3389 -RemoteAddress '100.64.0.0/10' -Action Allow -Profile Any | Out-Null

$radios = Get-PnpDevice -PresentOnly | Where-Object {
    $_.InstanceId -like 'PCI\VEN_14C3&DEV_7925*' -or       # MediaTek Wi-Fi 7
    $_.InstanceId -like 'USB\VID_0489&PID_E11E*' -or       # its Bluetooth
    $_.Class -eq 'Bluetooth'
}
foreach ($d in $radios) {
    if ($d.Status -ne 'Unknown' -or $d.ConfigManagerErrorCode -ne 22) {
        Disable-PnpDevice -InstanceId $d.InstanceId -Confirm:$false -ErrorAction SilentlyContinue
    }
}

"RDP: deny={0} NLA={1}" -f (Get-ItemProperty $ts).fDenyTSConnections, (Get-ItemProperty "$ts\WinStations\RDP-Tcp").UserAuthentication
Get-NetFirewallRule -Name 'dw-rdp-tailscale' | Get-NetFirewallAddressFilter | Format-Table InstanceID, RemoteAddress -AutoSize
Get-PnpDevice | Where-Object { $_.InstanceId -like 'PCI\VEN_14C3*' -or $_.InstanceId -like 'USB\VID_0489*' -or $_.Class -eq 'Bluetooth' } |
    Format-Table FriendlyName, Status, ConfigManagerErrorCode -AutoSize
