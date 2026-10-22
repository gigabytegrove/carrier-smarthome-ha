# Read-only Carrier cloud inventory; outputs only sanitized fields.
[CmdletBinding()]
param([switch]$NoSave)
$ErrorActionPreference = 'Stop'
$venv = Join-Path $env:LOCALAPPDATA 'CarrierSmartHome-Research\cloud-test-venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venv -PathType Leaf)) {
    throw 'Cloud test Python environment missing. Run tools\Test-Cloud.ps1 first.'
}
$cmd = @( (Join-Path $PSScriptRoot 'Get-CarrierValues.py') )
if (-not $NoSave) {
    $dir = Join-Path $env:LOCALAPPDATA 'CarrierSmartHome-Research'
    $file = Join-Path $dir ('cloud-values-safe-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.json')
    $cmd += @('--output', $file)
}
& $venv @cmd
if ($LASTEXITCODE -ne 0) { throw "Cloud field inventory returned exit code $LASTEXITCODE" }
