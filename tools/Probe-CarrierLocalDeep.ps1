# Carrier SmartHome 0.5.4: one engine, three explicit target-selection paths.
# All probes are network reconnaissance only; NEVER HVAC commands or Matter.
[CmdletBinding()]
param(
    [string]$DirectIP = '',
    [switch]$AcknowledgeIpRisk,
    [string]$ArchivePath = '',
    [switch]$LiveOmada,
    [string]$MacSuffix = '',
    [switch]$PlanOnly,
    [switch]$FullTCP,
    [ValidateRange(5,120)][int]$MaxAgeMinutes = 30,
    [ValidateRange(1,64)][int]$Concurrency = 12,
    [ValidateRange(0.2,2.0)][double]$TcpTimeout = 0.45,
    [Nullable[int]]$ControllerUtcOffset = $null
)
$ErrorActionPreference = 'Stop'
$target = Join-Path $PSScriptRoot 'Probe-CarrierLocalDeep.py'
if (-not (Test-Path -LiteralPath $target -PathType Leaf)) { throw 'Local probe engine not found in this repository.' }

# Choose exactly one form of identification. No automatic fallback to an old IP.
if ($DirectIP) {
    if ($LiveOmada -or $ArchivePath -or $MacSuffix -or $null -ne $ControllerUtcOffset) {
        throw 'DirectIP cannot be combined with Omada export or MAC selection.'
    }
    if (-not $AcknowledgeIpRisk) {
        throw 'Use -AcknowledgeIpRisk: this address was identified earlier, but DHCP may have reassigned it. No packets sent.'
    }
} elseif ($AcknowledgeIpRisk) {
    throw '-AcknowledgeIpRisk is only for -DirectIP mode.'
} elseif ($LiveOmada -and $ArchivePath) {
    throw 'Choose either live Omada UI or an export, not both.'
}

$py = Get-Command py.exe, python.exe, python3.exe -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $py) { throw 'Python 3.11 or newer is needed. The cloud research tools previously used Python on this computer.' }
$argList = @($target, '--concurrency', [string]$Concurrency,
            '--tcp-timeout', $TcpTimeout.ToString([Globalization.CultureInfo]::InvariantCulture))

if ($DirectIP) {
    $argList += @('--direct-ip', $DirectIP, '--accept-direct-risk', 'I-ACCEPT-IP-REASSIGNMENT-RISK')
    Write-Host "`n=== KNOWN-IP SINGLE-HOST DISCOVERY ===" -ForegroundColor Cyan
    Write-Host 'Identity assurance: last known owner IP only; current hardware identity NOT machine-verified.' -ForegroundColor Yellow
} elseif ($LiveOmada) {
    if (-not $MacSuffix) { $MacSuffix = Read-Host 'Thermostat Wi-Fi MAC final 4 hex digits (private)' }
    if ($MacSuffix -notmatch '^[0-9A-Fa-f]{4}$') { throw 'MAC suffix must be four hex digits.' }
    Write-Host 'Read the current CONNECTED client from Omada; avoid historical DHCP records.' -ForegroundColor Cyan
    $currentIP = (Read-Host 'Current thermostat IP in Omada Connected Clients').Trim()
    $currentMAC = (Read-Host 'Current thermostat full Wi-Fi MAC').Trim()
    $confirm = (Read-Host 'Type I-SEE-IT-CONNECTED if the live Omada client is currently online').Trim()
    $argList += @('--manual-ip', $currentIP, '--manual-mac', $currentMAC,
                   '--manual-confirm', $confirm, '--suffix', $MacSuffix)
    Remove-Variable currentIP,currentMAC,confirm -ErrorAction SilentlyContinue
    Write-Host 'Identity assurance: owner-reported live UI; not independently verified.' -ForegroundColor Yellow
} else {
    if (-not $ArchivePath) {
        $downloads = Join-Path $env:USERPROFILE 'Downloads'
        $exports = @(Get-ChildItem -LiteralPath $downloads -Filter 'Client_*.zip' -File -ErrorAction SilentlyContinue |
                     Sort-Object LastWriteTimeUtc -Descending)
        if ($exports.Count -eq 0) { throw 'No Omada ZIP found. Use -DirectIP with an explicitly known address instead.' }
        $ArchivePath = $exports[0].FullName
    }
    if (-not (Test-Path -LiteralPath $ArchivePath -PathType Leaf)) { throw 'Omada ZIP not found.' }
    if (-not $MacSuffix) { $MacSuffix = Read-Host 'Thermostat Wi-Fi MAC final 4 hex digits (private)' }
    if ($MacSuffix -notmatch '^[0-9A-Fa-f]{4}$') { throw 'MAC suffix must be four hex digits.' }
    $argList += @('--omada', $ArchivePath, '--suffix', $MacSuffix, '--max-age-minutes', [string]$MaxAgeMinutes)
    if ($null -ne $ControllerUtcOffset) { $argList += @('--controller-utc-offset', [string]$ControllerUtcOffset) }
    Write-Host 'Identity assurance: current Omada MAC/IP mapping; freshness checked by engine.' -ForegroundColor Cyan
}
if ($FullTCP) { $argList += '--full-tcp' }
if ($PlanOnly) {
    $argList += '--plan'
} else {
    $reportDir = Join-Path $env:LOCALAPPDATA 'CarrierSmartHome-Research'
    New-Item -ItemType Directory -Path $reportDir -Force | Out-Null
    $reportFile = Join-Path $reportDir ('carrier-local-v0.5.4-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.json')
    $argList += @('--output', $reportFile)
}
Write-Host 'Mode:' $(if ($PlanOnly) {'PLAN: no network'} elseif ($FullTCP) {'FULL TCP + UDP targeted research'} else {'QUICK TCP + UDP targeted research'})
& $py.Source @argList
$exitCode = $LASTEXITCODE
if ($exitCode -ne 0) { throw "Carrier discovery stopped (exit $exitCode). Review the specific cause printed above. No HVAC commands are ever sent." }
