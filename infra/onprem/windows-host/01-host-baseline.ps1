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

# --- Page file: a fixed 64 GB on C: --------------------------------------------
# Strata commits about 59 GB for the model and the VM holds 16 GB, so with the
# automatic 22 GB page file the commit charge stood at 83.2 of 85 GB (measured
# 2026-11-16): one more allocation anywhere and Windows refuses it, whoever
# asks. A fixed 64 GB lifts the limit to ~128 GB. It is a ceiling, not paging:
# pages were read back from it at 0/s with the model serving. Takes effect at
# the next restart.
$cs = Get-CimInstance Win32_ComputerSystem
if ($cs.AutomaticManagedPagefile) { Set-CimInstance -InputObject $cs -Property @{ AutomaticManagedPagefile = $false } }
$pf = Get-CimInstance Win32_PageFileSetting | Where-Object Name -eq 'C:\pagefile.sys'
if (-not $pf) { $pf = New-CimInstance -ClassName Win32_PageFileSetting -Property @{ Name = 'C:\pagefile.sys' } }
Set-CimInstance -InputObject $pf -Property @{ InitialSize = [uint32]65536; MaximumSize = [uint32]65536 }

# --- Report -------------------------------------------------------------------
Write-Host '== power'; powercfg /getactivescheme
Write-Host '== windows update policy'
Get-ItemProperty $au | Select-Object NoAutoUpdate, AUOptions, NoAutoRebootWithLoggedOnUsers | Format-List
Get-ItemProperty $wu | Select-Object ExcludeWUDriversInQualityUpdate | Format-List
Write-Host '== page file (MB)'
Get-CimInstance Win32_PageFileSetting | Format-Table Name, InitialSize, MaximumSize -AutoSize
