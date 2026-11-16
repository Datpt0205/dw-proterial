# Volumes for the DW host, after 02-boot-from-os-disk.ps1 and the BIOS step:
#   V:  ReFS on the rest of the OS disk (SSD), for the DW virtual machine
#   B:  NTFS on the data disk (HDD), for backups only
# Run as Administrator. Idempotent: an existing V: or B: is left alone.
#
# Disks are picked by model, never by number: numbers moved between reboots on
# the plant host (2026-11-16). Defaults are that host's disks.

param(
    [string]$OsDiskModel   = 'KIOXIA*',
    [string]$DataDiskModel = 'WDC WD40EZZX*'
)

$ErrorActionPreference = 'Stop'
$espGuid = '{c12a7328-f81f-11d2-ba4b-00a0c93ec93b}'

function One-Disk([string]$model) {
    $d = @(Get-Disk | Where-Object FriendlyName -like $model)
    if ($d.Count -ne 1) { throw "Expected one disk like '$model', found $($d.Count)." }
    $d[0]
}

$os   = One-Disk $OsDiskModel
$data = One-Disk $DataDiskModel

# Refuse to touch the data disk while anything boots from it.
$loaded = (Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\hivelist').'\REGISTRY\MACHINE\BCD00000000'
if ($data.IsBoot -or $data.IsSystem) { throw "Disk $($data.Number) is boot/system; run 02 and the BIOS step first." }
if (-not (Get-Partition -DiskNumber $os.Number | Where-Object GptType -eq $espGuid)) {
    throw "The OS disk has no EFI system partition; run 02 first."
}
Write-Host "BCD loaded from: $loaded"

# --- V: ReFS for the VM on the OS disk ---------------------------------------
if (-not (Get-Volume -DriveLetter V -ErrorAction SilentlyContinue)) {
    New-Partition -DiskNumber $os.Number -UseMaximumSize -DriveLetter V | Out-Null
    Format-Volume -DriveLetter V -FileSystem ReFS -NewFileSystemLabel 'DW-VM' -Confirm:$false | Out-Null
    Write-Host 'V: created (ReFS, DW-VM)'
}

# --- B: the backup disk -------------------------------------------------------
if (-not (Get-Volume -DriveLetter B -ErrorAction SilentlyContinue)) {
    # Holds only Setup's stray ESP and an empty volume on a fresh host.
    Clear-Disk -Number $data.Number -RemoveData -RemoveOEM -Confirm:$false
    if ((Get-Disk -Number $data.Number).PartitionStyle -eq 'RAW') {
        Initialize-Disk -Number $data.Number -PartitionStyle GPT
    }
    New-Partition -DiskNumber $data.Number -UseMaximumSize -DriveLetter B | Out-Null
    Format-Volume -DriveLetter B -FileSystem NTFS -AllocationUnitSize 65536 `
        -NewFileSystemLabel 'DW-BACKUP' -Confirm:$false | Out-Null
    Write-Host 'B: created (NTFS 64K, DW-BACKUP)'
}

# --- WinRE registered in the boot store now in use ------------------------------
# Moving the ESP left WinRE disabled and ReAgent.xml naming an entry of the old
# store, so `reagentc /enable` failed "The specified path was not found"
# (measured 2026-11-16). Clearing that id lets enable make a new entry.
if ((reagentc /info | Out-String) -notmatch 'Windows RE status:\s+Enabled') {
    $x = "$env:SystemRoot\System32\Recovery\ReAgent.xml"
    if (Test-Path $x) {
        Copy-Item $x "$x.bak-dw" -Force
        (Get-Content $x -Raw) -replace '<WinreBCD id="\{[0-9a-fA-F-]+\}"/>', '<WinreBCD id=""/>' |
            Set-Content $x -Encoding utf8
    }
    reagentc /enable | Out-Host
}

Write-Host '== volumes'
Get-Volume | Where-Object DriveLetter -in 'B','C','V' |
    Format-Table DriveLetter, FileSystemLabel, FileSystem, @{n='GB';e={[math]::Round($_.Size/1GB)}} -AutoSize
Write-Host '== ESPs'
Get-Partition | Where-Object GptType -eq $espGuid | Format-Table DiskNumber, PartitionNumber, @{n='MB';e={[math]::Round($_.Size/1MB)}} -AutoSize
reagentc /info | Select-String 'status|location|BCD'
