# Optional owner-side read-only Carrier schedule/reminder capability test.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$venv = Join-Path $env:LOCALAPPDATA 'CarrierSmartHome-Research\cloud-test-venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venv)) { throw 'Run tools\Test-Cloud.ps1 first to establish the isolated Python environment.' }
& $venv (Join-Path $PSScriptRoot 'Probe-SmartHomeFeatures.py')
if ($LASTEXITCODE -ne 0) { throw "Cloud feature probe stopped (exit $LASTEXITCODE)." }
