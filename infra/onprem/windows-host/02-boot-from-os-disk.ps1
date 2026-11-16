# Make the disk that holds Windows boot on its own: an EFI system partition on
# that disk, and the firmware pointed at it. Run as Administrator; reboot after.
#
# Why: with a second disk present, Windows Setup put the EFI system partition
# on the 4 TB HDD while Windows went to the SSD (measured on the plant host,
# 2026-11-16). A dead HDD would then leave the host unbootable, and the HDD
# could not be wiped to hold backups. Idempotent: does nothing once the OS disk
# carries an ESP.
#
# Not enough on its own on the ASUS board: its BIOS keeps a per-disk boot
# priority and still started the HDD's Windows Boot Manager after both changes
# below (the loaded BCD hive stayed on the HDD's ESP). A person sets Boot
# Option #1 to the SSD's "Windows Boot Manager" in the BIOS;
# `shutdown /r /fw /t 5` reboots straight into it. Then confirm, before the
# HDD's ESP is removed, that
#   (Get-ItemProperty HKLM:\SYSTEM\CurrentControlSet\Control\hivelist).'\REGISTRY\MACHINE\BCD00000000'
# names the SSD's ESP volume.

param(
    [int]$SystemSizeGB = 250   # C: is shrunk to this; the rest becomes the VM volume later
)

$ErrorActionPreference = 'Stop'
$espGuid = '{c12a7328-f81f-11d2-ba4b-00a0c93ec93b}'
$osDisk = (Get-Partition -DriveLetter C).DiskNumber

if (Get-Partition -DiskNumber $osDisk | Where-Object GptType -eq $espGuid) {
    Write-Host "Disk $osDisk already has an EFI system partition; nothing to do."
    exit 0
}

# 1. Shrink C: to make room (only if it is larger than asked).
$c = Get-Partition -DriveLetter C
$target = [int64]$SystemSizeGB * 1GB
if ($c.Size -gt $target + 1GB) {
    Resize-Partition -DriveLetter C -Size $target
    Write-Host ("C: shrunk to {0} GB" -f $SystemSizeGB)
}

# 2. An ESP on the OS disk, FAT32, with a temporary letter.
#    diskpart, because New-Partition will not format or letter an ESP.
$letter = 'S'
if (Test-Path "${letter}:\") { throw "Drive ${letter}: is in use; free it first." }
$script = @"
select disk $osDisk
create partition efi size=300
format quick fs=fat32 label="SYSTEM"
assign letter=$letter
"@
$tmp = Join-Path $env:TEMP 'dw-esp.txt'
Set-Content -Path $tmp -Value $script -Encoding ascii
diskpart /s $tmp | Out-Host
Remove-Item $tmp

# 3. Boot files onto it, then point Windows Boot Manager at it. bcdboot alone
#    left {bootmgr} on the HDD's ESP (measured 2026-11-16), so it is set too.
bcdboot C:\Windows /s "${letter}:" /f UEFI | Out-Host
bcdedit /set '{bootmgr}' device "partition=${letter}:" | Out-Host

# 4. Drop the temporary letter.
mountvol "${letter}:" /D

Write-Host '== boot manager now'
bcdedit /enum '{bootmgr}' | Select-String 'device|path|description'
Write-Host '== ESPs'
Get-Partition | Where-Object GptType -eq $espGuid |
    Format-Table DiskNumber, PartitionNumber, @{n='MB';e={[math]::Round($_.Size/1MB)}}, IsSystem -AutoSize
