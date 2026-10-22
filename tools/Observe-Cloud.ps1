# Bounded read-only native Carrier cloud trend test; no Matter or thermostat writes.
[CmdletBinding()]
param([ValidateRange(1,12)][int]$Samples = 3,
      [ValidateRange(20,3600)][int]$IntervalSeconds = 60)
$ErrorActionPreference = 'Stop'
$root = Join-Path $env:LOCALAPPDATA 'CarrierSmartHome-Research'
$venv = Join-Path $root 'cloud-test-venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venv)) {
    throw 'Cloud test Python environment missing. Run tools\Test-Cloud.ps1 first.'
}
& $venv (Join-Path $PSScriptRoot 'Observe-SmartHomeCloud.py') --samples $Samples --interval $IntervalSeconds
if ($LASTEXITCODE -ne 0) { throw "Carrier read-only observer failed (exit $LASTEXITCODE)." }
