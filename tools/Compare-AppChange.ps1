# Guided read-only comparison of official Carrier app changes and two cloud queries.
# PowerShell 5.1 or later; reuse isolated Python cloud test environment.
[CmdletBinding()]
param([ValidateRange(1,12)][int]$Samples = 6,
      [ValidateRange(15,300)][int]$IntervalSeconds = 20)
$ErrorActionPreference = 'Stop'
$venv = Join-Path $env:LOCALAPPDATA 'CarrierSmartHome-Research\cloud-test-venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venv -PathType Leaf)) {
    throw 'Carrier Python environment not found. Run tools\Test-Cloud.ps1 first.'
}
Write-Host "`n=== OFFICIAL CARRIER APP <-> NATIVE CLOUD CHANGE COMPARISON ===" -ForegroundColor Cyan
Write-Host 'Read-only script; any changes and restoration happen ONLY in your official phone app.'
& $venv (Join-Path $PSScriptRoot 'Compare-AppChange.py') --samples $Samples --interval $IntervalSeconds
if ($LASTEXITCODE -ne 0) { throw "Carrier app/cloud comparison stopped (exit code $LASTEXITCODE). If you changed a setting, restore it in your app." }
