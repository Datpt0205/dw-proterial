# A private link between the host and the DW VM, apart from the LAN: an
# Internal vSwitch with fixed addresses (host 10.250.0.1, VM 10.250.0.2).
# DW reaches Strata and the backup share over it, so the LAN's addresses can
# change (IT moves the host to the 83.x network) without touching either, and
# the model's port and the backup share answer the VM alone, not the LAN.
# Run as Administrator. Idempotent. The VM side is vm/14-internal-link.sh.

$ErrorActionPreference = 'Stop'
$switch = 'DW-Internal'
$hostIp = '10.250.0.1'
$vmIp   = '10.250.0.2'
$vmName = 'dw-vm'

if (-not (Get-VMSwitch -Name $switch -ErrorAction SilentlyContinue)) {
    New-VMSwitch -Name $switch -SwitchType Internal -Notes 'DW host <-> VM only' | Out-Null
}
$ifAlias = "vEthernet ($switch)"
if (-not (Get-NetIPAddress -InterfaceAlias $ifAlias -IPAddress $hostIp -ErrorAction SilentlyContinue)) {
    New-NetIPAddress -InterfaceAlias $ifAlias -IPAddress $hostIp -PrefixLength 30 | Out-Null
}
# A private network profile, so no "public network" rule set applies to it.
Set-NetConnectionProfile -InterfaceAlias $ifAlias -NetworkCategory Private -ErrorAction SilentlyContinue

# Second adapter on the VM (hot-add works on Generation 2), fixed MAC so the VM
# names it the same way every boot.
if (-not (Get-VMNetworkAdapter -VMName $vmName | Where-Object SwitchName -eq $switch)) {
    Add-VMNetworkAdapter -VMName $vmName -SwitchName $switch -Name 'dw-internal' -StaticMacAddress '00155D0A0002'
}

# The model's port and the backup share: from the VM's internal address only.
# (Replaces the LocalSubnet rules 05 and 08 made.)
foreach ($r in @(@{ n = 'dw-strata-api'; p = 8080; d = 'DW Strata API' }, @{ n = 'dw-backup-smb'; p = 445; d = 'DW backup share (SMB)' })) {
    Remove-NetFirewallRule -Name $r.n -ErrorAction SilentlyContinue
    New-NetFirewallRule -Name $r.n -DisplayName $r.d -Direction Inbound -Protocol TCP -LocalPort $r.p `
        -RemoteAddress $vmIp -Action Allow -Profile Any | Out-Null
}

Get-NetIPAddress -InterfaceAlias $ifAlias -AddressFamily IPv4 | Format-Table InterfaceAlias, IPAddress, PrefixLength -AutoSize
Get-VMNetworkAdapter -VMName $vmName | Format-Table Name, SwitchName, MacAddress -AutoSize
Get-NetFirewallRule -Name 'dw-strata-api', 'dw-backup-smb' | Get-NetFirewallAddressFilter | Format-Table InstanceID, RemoteAddress -AutoSize
