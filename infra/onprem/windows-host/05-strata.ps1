# Strata (Qwen3.8-Flash-Next Q2_0 with its picture reader) on the DW host,
# started at boot and restarted when it stops answering. Run as Administrator.
# Idempotent. Decided by Đạt 2026-11-16: Strata on Windows, Q2 with vision.
#
# Pinned: Strata v0.2.14 (Terminal 0.1.60.1), MIT. The installer is the
# release's install.ps1, checked by SHA256 below; it checks the Terminal's
# SHA256 and the release's signed feed itself. Data lives in C:\Strata (not a
# user profile, so the boot task finds it); models in V:\Strata.
#
# The API key is made here, kept in the machine environment as
# DW_STRATA_API_KEY and never printed. The DW VM's .env gets it as
# DW_ONPREM_MODEL_API_KEY by a copy that does not echo it.

$ErrorActionPreference = 'Stop'
$here       = Split-Path -Parent $MyInvocation.MyCommand.Path
$installer  = Join-Path $here 'strata-install-0.2.14.ps1'
$installSha = 'DADBBD3F3BB4741102705CE2B67FE018C66F9833E7EF38A243DCF5E9D185F623'
$watchdog   = 'C:\Strata\dw\strata-watchdog.ps1'

# --- 1. The Terminal, pinned ---------------------------------------------------
[Environment]::SetEnvironmentVariable('STRATA_DATA_DIR', 'C:\Strata', 'Machine')
$env:STRATA_DATA_DIR = 'C:\Strata'
if (-not (Test-Path 'C:\Strata\terminal\current\bin\strata.cmd')) {
    if (-not (Test-Path $installer)) {
        curl.exe -fsSL -o $installer 'https://github.com/Niko1221/Strata/releases/download/v0.2.14/install.ps1'
    }
    if ((Get-FileHash $installer -Algorithm SHA256).Hash -ne $installSha) { throw 'Strata installer hash mismatch' }
    $env:STRATA_FEED    = 'https://github.com/Niko1221/Strata/releases/download/v0.2.14'
    $env:STRATA_NO_PATH = '1'
    & powershell -ExecutionPolicy Bypass -File $installer
}

# --- 2. API key, made once, never shown ----------------------------------------
if (-not [Environment]::GetEnvironmentVariable('DW_STRATA_API_KEY', 'Machine')) {
    $bytes = New-Object byte[] 36
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $key = [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
    [Environment]::SetEnvironmentVariable('DW_STRATA_API_KEY', $key, 'Machine')
    Remove-Variable key
    Write-Host 'DW_STRATA_API_KEY created (machine environment).'
}

# --- 3. Defender: do not scan 66 GB of model files on every read ---------------
New-Item -ItemType Directory -Force 'V:\Strata', 'C:\Strata\dw' | Out-Null
Add-MpPreference -ExclusionPath 'V:\Strata', 'C:\Strata'

# --- 4. Firewall: the API on 8080 from the local network only (key required) ----
#     Narrowed to the DW VM's address once it has a fixed one.
if (-not (Get-NetFirewallRule -Name 'dw-strata-api' -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -Name 'dw-strata-api' -DisplayName 'DW Strata API' -Direction Inbound `
        -Protocol TCP -LocalPort 8080 -RemoteAddress LocalSubnet -Action Allow -Profile Any | Out-Null
}

# --- 5. The boot and watchdog task -----------------------------------------------
Copy-Item (Join-Path $here 'strata-watchdog.ps1') $watchdog -Force
$action    = New-ScheduledTaskAction -Execute 'powershell.exe' `
                -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$watchdog`""
$atBoot    = New-ScheduledTaskTrigger -AtStartup
# The VM's 16 GB is taken when the VM starts; Strata then fills most of the rest
# with the model's experts. Strata waits 2 minutes so the VM always starts first.
$atBoot.Delay = 'PT2M'
$every5    = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 5)
$principal = New-ScheduledTaskPrincipal -UserId "$env:COMPUTERNAME\Administrator" -LogonType S4U -RunLevel Highest
$settings  = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable `
                -ExecutionTimeLimit (New-TimeSpan -Seconds 0) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName 'DW-Strata' -Action $action -Trigger $atBoot, $every5 `
    -Principal $principal -Settings $settings -Force | Out-Null
Write-Host 'Task DW-Strata registered (at startup and every 5 minutes).'

Get-ScheduledTask -TaskName 'DW-Strata' | Format-List TaskName, State
