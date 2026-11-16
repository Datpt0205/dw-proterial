# The DW virtual machine on the host: Ubuntu 24.04 (cloud image) on Hyper-V,
# Generation 2 with Secure Boot, started with the host and shut down cleanly
# with it. Run as Administrator, after 03 (V:) and the DW-External vSwitch.
# Idempotent: an existing VM is left alone.
#
# Inputs, next to this script:
#   noble.vhdx          the Ubuntu 24.04 cloud image converted to VHDX
#                       (qemu-img convert -O vhdx -o subformat=dynamic, from
#                       ubuntu-24.04-server-cloudimg-amd64.img, SHA256 checked
#                       against cloud-images.ubuntu.com's SHA256SUMS)
#   authorized_keys     the public key(s) allowed to SSH in as `dw`
#
# Sizing (64 GB host): Strata keeps the model's experts in host RAM (34 GB plus
# ~10 GB for Windows, docs/MODELS.md), so the VM gets 16 GB, fixed.

param(
    [string]$Name     = 'dw-vm',
    [int]$Cpu         = 12,
    [int64]$MemoryGB  = 16,
    [int64]$DiskGB    = 400,
    [string]$Switch   = 'DW-External'
)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$dir  = "V:\Hyper-V\$Name"

if (Get-VM -Name $Name -ErrorAction SilentlyContinue) { Write-Host "VM $Name exists; nothing to do."; Get-VM $Name; exit 0 }

New-Item -ItemType Directory -Force $dir | Out-Null
Set-VMHost -VirtualMachinePath 'V:\Hyper-V' -VirtualHardDiskPath 'V:\Hyper-V'

# Defender: do not scan the VM's disks on every block (Microsoft's Hyper-V exclusions).
Add-MpPreference -ExclusionPath 'V:\Hyper-V' -ExclusionExtension '.vhdx', '.avhdx' `
    -ExclusionProcess "$env:SystemRoot\System32\vmms.exe", "$env:SystemRoot\System32\vmwp.exe", "$env:SystemRoot\System32\vmcompute.exe"

# --- OS disk -----------------------------------------------------------------------
$osDisk = Join-Path $dir "$Name.vhdx"
Copy-Item (Join-Path $here 'noble.vhdx') $osDisk
Resize-VHD -Path $osDisk -SizeBytes ($DiskGB * 1GB)

# --- cloud-init seed: a small FAT disk labelled CIDATA (NoCloud) ------------------
$keys = (Get-Content (Join-Path $here 'authorized_keys') | Where-Object { $_ -match '^ssh-' }) |
    ForEach-Object { "      - $_" }
$userData = @"
#cloud-config
hostname: $Name
timezone: Asia/Ho_Chi_Minh
users:
  - name: dw
    groups: [sudo]
    shell: /bin/bash
    sudo: "ALL=(ALL) NOPASSWD:ALL"
    lock_passwd: true
    ssh_authorized_keys:
$($keys -join "`n")
ssh_pwauth: false
disable_root: true
package_update: true
package_upgrade: true
packages: [chrony, ca-certificates, curl, jq]
write_files:
  - path: /etc/apt/apt.conf.d/52dw-no-auto-reboot
    content: |
      Unattended-Upgrade::Automatic-Reboot "false";
  - path: /etc/systemd/journald.conf.d/dw.conf
    content: |
      [Journal]
      SystemMaxUse=1G
"@
$metaData = "instance-id: $Name-1`nlocal-hostname: $Name`n"

$seed = Join-Path $dir 'cidata.vhdx'
New-VHD -Path $seed -SizeBytes 64MB -Fixed | Out-Null
$disk = Mount-VHD -Path $seed -Passthru | Get-Disk
Initialize-Disk -Number $disk.Number -PartitionStyle MBR
$part = New-Partition -DiskNumber $disk.Number -UseMaximumSize -AssignDriveLetter
Format-Volume -Partition $part -FileSystem FAT32 -NewFileSystemLabel 'CIDATA' -Confirm:$false | Out-Null
$root = "$($part.DriveLetter):\"
# cloud-init reads LF files; write without a BOM
[IO.File]::WriteAllText((Join-Path $root 'user-data'), ($userData -replace "`r`n", "`n"))
[IO.File]::WriteAllText((Join-Path $root 'meta-data'), $metaData)
Dismount-VHD -Path $seed

# --- the VM ------------------------------------------------------------------------
New-VM -Name $Name -Generation 2 -MemoryStartupBytes ($MemoryGB * 1GB) -VHDPath $osDisk `
    -SwitchName $Switch -Path 'V:\Hyper-V' | Out-Null
Set-VM -Name $Name -ProcessorCount $Cpu -StaticMemory `
    -AutomaticStartAction Start -AutomaticStartDelay 0 `
    -AutomaticStopAction ShutDown -CheckpointType Disabled
Set-VMFirmware -VMName $Name -EnableSecureBoot On -SecureBootTemplate 'MicrosoftUEFICertificateAuthority'
Add-VMHardDiskDrive -VMName $Name -Path $seed
Enable-VMIntegrationService -VMName $Name -Name 'Guest Service Interface', 'Heartbeat', 'Key-Value Pair Exchange', 'Shutdown', 'Time Synchronization'
Start-VM -Name $Name

Get-VM -Name $Name | Format-List Name, State, ProcessorCount, MemoryStartup, AutomaticStartAction, AutomaticStopAction, CheckpointType
Get-VMNetworkAdapter -VMName $Name | Format-List MacAddress, SwitchName
