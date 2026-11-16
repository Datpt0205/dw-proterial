# Keeps Strata serving on the DW host. Run by the "DW-Strata" scheduled task at
# startup and every 5 minutes (05-strata.ps1 registers it). If /health answers,
# it does nothing; otherwise it runs `strata launch` with the fixed choices
# below, which starts the server and returns (the same choices never restart a
# running model, so a slow health answer cannot cause a restart loop).
#
# The first run downloads the engine and the model (about 68.5 GB); the task's
# "ignore new instances" keeps the 5-minute trigger from starting a second one.

$ErrorActionPreference = 'Continue'
$env:STRATA_DATA_DIR   = 'C:\Strata'
$env:DW_STRATA_API_KEY = [Environment]::GetEnvironmentVariable('DW_STRATA_API_KEY', 'Machine')
$strata = 'C:\Strata\terminal\current\bin\strata.cmd'
$logDir = 'C:\Strata\dw-logs'
New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path $logDir 'watchdog.log'
function Log([string]$m) { "$(Get-Date -Format o) $m" | Add-Content -Path $log -Encoding utf8 }

# Keep the log small: one previous file, about 1 MB each.
if ((Test-Path $log) -and (Get-Item $log).Length -gt 1MB) { Move-Item $log "$log.1" -Force }

try {
    $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 15 -Uri 'http://127.0.0.1:8080/health'
    if ($r.StatusCode -eq 200) { exit 0 }
} catch { }

if (-not $env:DW_STRATA_API_KEY) { Log 'no DW_STRATA_API_KEY in the machine environment; not starting'; exit 1 }

Log 'health did not answer; launching'
& $strata launch --family qwen --model q2_0 --data-dir 'V:\Strata' `
    --context 64k --parallel 3 --vision on `
    --access lan --port 8080 --api-key-env DW_STRATA_API_KEY `
    --yes --no-tui *>> (Join-Path $logDir 'launch.log')
Log "launch exited $LASTEXITCODE"
