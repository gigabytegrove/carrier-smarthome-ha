# Target a currently ONLINE Carrier thermostat identified by Omada hardware MAC.
# Never scans a historical (offline) lease or the entire VLAN.
[CmdletBinding()]
param([string]$ArchivePath, [switch]$PlanOnly)
$ErrorActionPreference = 'Stop'
if (-not $ArchivePath) {
    $ArchivePath = Get-ChildItem -Path (Join-Path $env:USERPROFILE 'Downloads') -Filter 'Client_*.zip' -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1 -ExpandProperty FullName
}
if (-not $ArchivePath) { throw 'Omada client export not found in Downloads.' }
$py = Get-Command py.exe, python.exe, python3.exe -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $py) { throw 'Python 3.11+ is required.' }
$argsForPython = @((Join-Path $PSScriptRoot 'Probe-VerifiedCarrierLAN.py'), $ArchivePath)
if ($PlanOnly) { $argsForPython += '--plan' }
& $py.Source @argsForPython
if ($LASTEXITCODE -ne 0) { throw "Carrier verified LAN probe stopped (exit $LASTEXITCODE)." }
