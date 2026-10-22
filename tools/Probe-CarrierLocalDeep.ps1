# Carrier SmartHome v0.5.1 -- native proprietary LAN reconnaissance, no Matter.
# Does not scan without a fresh Omada Client ZIP and confirmed active MAC lease.
[CmdletBinding()]
param(
    [string]$ArchivePath = '',
    [string]$MacSuffix = '',
    [switch]$FullTCP,
    [switch]$PlanOnly,
    [ValidateRange(5,120)][int]$MaxAgeMinutes = 30,
    [ValidateRange(1,64)][int]$Concurrency = 32,
    [ValidateRange(0.2,2.0)][double]$TcpTimeout = 0.45,
    [Nullable[int]]$ControllerUtcOffset = $null
)
$ErrorActionPreference = 'Stop'
if (-not $ArchivePath) {
    $downloads = Join-Path $env:USERPROFILE 'Downloads'
    $found = @(Get-ChildItem -LiteralPath $downloads -Filter 'Client_*.zip' -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTimeUtc -Descending)
    if ($found.Count -eq 0) {
        throw 'No Omada Client_*.zip in Downloads. Export CURRENT CONNECTED CLIENTS from Omada, save ZIP to Downloads, then run again.'
    }
    $fresh = @($found | Where-Object { $_.LastWriteTimeUtc -ge [DateTime]::UtcNow.AddMinutes(-$MaxAgeMinutes) })
    if ($fresh.Count -eq 0) {
        $latest = $found[0]
        Write-Host ('Newest local export: ' + $latest.Name + ' (' + $latest.LastWriteTime.ToString('yyyy-MM-dd HH:mm') + ')') -ForegroundColor Yellow
        throw 'All available Omada exports are old. Open Omada > Clients, export CURRENT connected clients again, and save a NEW Client_*.zip to Downloads. Old exports cannot confirm a current thermostat IP.'
    }
    $ArchivePath = $fresh[0].FullName
}
if (-not $MacSuffix) {
    $MacSuffix = Read-Host 'Final 4 hexadecimal characters of the thermostat Wi-Fi MAC from Omada or label'
}
if ($MacSuffix -notmatch '^[0-9a-fA-F]{4}$') { throw 'A 4-character hexadecimal MAC suffix is required. No traffic sent.' }
if (-not (Test-Path -LiteralPath $ArchivePath -PathType Leaf)) { throw 'Omada ZIP is missing. No traffic sent.' }
$py = Get-Command py.exe, python.exe, python3.exe -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $py) { throw 'Install Python 3.11+ before using the local research tools.' }
$target = Join-Path $PSScriptRoot 'Probe-CarrierLocalDeep.py'
if (-not (Test-Path -LiteralPath $target)) { throw 'Carrier LAN tool is missing from this checkout.' }
$reportDir = Join-Path $env:LOCALAPPDATA 'CarrierSmartHome-Research'
New-Item -Path $reportDir -ItemType Directory -Force | Out-Null
$report = Join-Path $reportDir ('carrier-local-0.5.1-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.json')
$arguments = @($target, '--omada', $ArchivePath, '--suffix', $MacSuffix, '--max-age-minutes', "$MaxAgeMinutes", '--concurrency', "$Concurrency", '--tcp-timeout', $TcpTimeout.ToString([Globalization.CultureInfo]::InvariantCulture))
if ($PlanOnly) { $arguments += '--plan' } else { $arguments += @('--output', $report) }
if ($FullTCP) { $arguments += '--full-tcp' }
if ($null -ne $ControllerUtcOffset) { $arguments += @('--controller-utc-offset', "$ControllerUtcOffset") }
Write-Host "`n=== CARRIER LOCAL PROTOCOL RESEARCH ===" -ForegroundColor Cyan
Write-Host 'Omada ZIP:' (Split-Path -Leaf $ArchivePath)
Write-Host 'Mode:' $(if ($PlanOnly) { 'Plan only' } elseif ($FullTCP) { 'Full TCP 1-65535 + protocol discovery' } else { 'Top 1024 + common IoT TCP + protocol discovery' })
& $py.Source @arguments
if ($LASTEXITCODE -ne 0) {
    throw "SAFE STOP (exit $LASTEXITCODE). Omada verification did not pass. The 08:14 export is old; download a NEW Client_*.zip while the thermostat is CONNECTED in Omada. Check the archive filename printed above. No historical IP is ever scanned."
}
