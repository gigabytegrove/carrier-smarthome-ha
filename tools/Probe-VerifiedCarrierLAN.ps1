# Target a currently ONLINE Carrier thermostat identified by Omada hardware MAC.
# Never scans a historical (offline) lease or the entire VLAN.
[CmdletBinding()]
param(
    [string]$ArchivePath,
    [string]$Suffix = '',
    [ValidateRange(1,120)][int]$MaxAgeMinutes = 20,
    [switch]$PlanOnly,
    [switch]$HttpFingerprint
)
$ErrorActionPreference = 'Stop'
if (-not $ArchivePath) {
    $ArchivePath = Get-ChildItem -Path (Join-Path $env:USERPROFILE 'Downloads') -Filter 'Client_*.zip' -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1 -ExpandProperty FullName
}
if (-not $ArchivePath) { throw 'No Omada Client_*.zip found in Downloads. Export fresh connected clients to Downloads or supply -ArchivePath.' }
Write-Host 'Omada export selected:' (Split-Path -Leaf $ArchivePath)
Write-Host 'Export must contain a currently connected thermostat and be no older than' $MaxAgeMinutes 'minutes.'
$py = Get-Command py.exe, python.exe, python3.exe -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $py) { throw 'Python 3.11+ is required.' }
$argsForPython = @((Join-Path $PSScriptRoot 'Probe-VerifiedCarrierLAN.py'), $ArchivePath, '--suffix', $Suffix, '--max-age-minutes', [string]$MaxAgeMinutes)
if ($PlanOnly) { $argsForPython += '--plan' }
if ($HttpFingerprint) { $argsForPython += '--http-fingerprint' }
& $py.Source @argsForPython
if ($LASTEXITCODE -ne 0) { throw "Carrier LAN probe stopped safely (exit $LASTEXITCODE). Export an up-to-date Omada Client ZIP. If multiple thermostats appear, pass the MAC suffix privately using -Suffix. No old IP was probed." }
