# NVIDIA driver for the host's GPU (RTX PRO 4000 Blackwell) on Windows Server
# 2025, for Strata running on Windows (Đạt, 2026-11-16: the GPU stays on the
# host, no DDA). Run as Administrator. Idempotent.
#
# Pinned: NVIDIA RTX Server Driver 597.30 (R595, 2026-10-22), found through
# NVIDIA's driver lookup for "RTX PRO 4000 Blackwell" + "Windows Server 2025".
# R595 was chosen over the newer R620 (621.14, its first release) because it
# has had four point releases. The SHA256 below is what was downloaded and
# installed on the plant host; NVIDIA's Authenticode signature was valid.
# A new version is a deliberate change here, never Windows Update (01 blocks
# drivers there).

$ErrorActionPreference = 'Stop'
$version = '597.30'
$file    = "$version-nvidia-rtx-winserv-2022-2025-64bit-international-dch-whql.exe"
$url     = "https://us.download.nvidia.com/Windows/Quadro_Certified/$version/$file"
$sha256  = '330A0EBB48CDB52397FFCFC926FE2E5CF42E019BFFFC17B1B2DAAAEFD8ABDB6D'
$dir     = 'C:\dw-setup\drivers'
$smi     = "$env:SystemRoot\System32\nvidia-smi.exe"

$current = if (Test-Path $smi) { (& $smi --query-gpu=driver_version --format=csv,noheader).Trim() } else { '' }
if ($current -ne $version) {
    New-Item -ItemType Directory -Force $dir | Out-Null
    $path = Join-Path $dir $file
    if (-not (Test-Path $path)) { curl.exe -fsSL --retry 3 -o $path $url }
    if ((Get-FileHash $path -Algorithm SHA256).Hash -ne $sha256) { throw "SHA256 mismatch for $file" }
    if ((Get-AuthenticodeSignature $path).Status -ne 'Valid') { throw "Bad signature on $file" }
    $p = Start-Process $path -ArgumentList '-s', '-noreboot', '-noeula', '-clean' -Wait -PassThru
    if ($p.ExitCode -ne 0) { throw "NVIDIA installer exited $($p.ExitCode)" }
}

# Compute on a WDDM GPU: Windows resets the driver when the GPU does not answer
# within TdrDelay (2 s by default), which kills a long model call and can take
# the server process with it. 60 s; takes effect after the next restart.
$gd = 'HKLM:\SYSTEM\CurrentControlSet\Control\GraphicsDrivers'
Set-ItemProperty -Path $gd -Name TdrDelay    -Type DWord -Value 60
Set-ItemProperty -Path $gd -Name TdrDdiDelay -Type DWord -Value 60

& $smi --query-gpu=name,driver_version,memory.total,driver_model.current,temperature.gpu --format=csv
Get-ItemProperty $gd | Select-Object TdrDelay, TdrDdiDelay | Format-List
