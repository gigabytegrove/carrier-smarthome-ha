# Read-only, memory-only account/device identity and connection cross-check.
[CmdletBinding()]
param([string]$ExpectedMac)
$ErrorActionPreference = 'Stop'
$venv = Join-Path $env:LOCALAPPDATA 'CarrierSmartHome-Research\cloud-test-venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venv -PathType Leaf)) {
    throw 'Cloud test environment missing. Run tools\Test-Cloud.ps1 first.'
}
$arguments = @( (Join-Path $PSScriptRoot 'Verify-CarrierConnectivity.py') )
if ($ExpectedMac) { $arguments += @('--expected-mac', $ExpectedMac) }
& $venv @arguments
if ($LASTEXITCODE -ne 0) { throw "Carrier connectivity check failed with exit code $LASTEXITCODE" }
