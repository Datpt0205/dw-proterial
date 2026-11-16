# DW host baseline on Windows Server 2025: power and Windows Update behaviour.
# Idempotent: safe to run again. Run as Administrator (over SSH or a console).
# Holds nothing customer-specific; the repository is public.
#
# Why each setting: .claude/plans/ops-hardening.md (plant host, 2026-11-16).

$ErrorActionPreference = 'Stop'

# --- Power: a server never sleeps or hibernates -----------------------------
powercfg /setactive SCHEME_MIN | Out-Null           # High performance
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
powercfg /hibernate off

# --- Windows Update: download, but install and restart only when a person says
# AUOptions 3 = download automatically, notify to install. With a signed-in
# session (OneDrive needs one) Windows does not restart on its own.
$au = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU'
New-Item -Path $au -Force | Out-Null
Set-ItemProperty -Path $au -Name NoAutoUpdate -Type DWord -Value 0
Set-ItemProperty -Path $au -Name AUOptions -Type DWord -Value 3
Set-ItemProperty -Path $au -Name NoAutoRebootWithLoggedOnUsers -Type DWord -Value 1

# Drivers come from us, never from Windows Update: a replaced NIC or GPU driver
# on a long-running host is an outage nobody scheduled (the NIC here runs on
# the I226-LM driver chosen by hand).
$wu = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate'
Set-ItemProperty -Path $wu -Name ExcludeWUDriversInQualityUpdate -Type DWord -Value 1

# --- Report -------------------------------------------------------------------
Write-Host '== power'; powercfg /getactivescheme
Write-Host '== windows update policy'
Get-ItemProperty $au | Select-Object NoAutoUpdate, AUOptions, NoAutoRebootWithLoggedOnUsers | Format-List
Get-ItemProperty $wu | Select-Object ExcludeWUDriversInQualityUpdate | Format-List
