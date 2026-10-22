# One-command read-only Carrier SmartHome cloud test for Windows.
# Uses only native Carrier cloud APIs. No network scanning, Matter, or changes to HVAC.
[CmdletBinding()]
param([switch]$SkipDependencyInstall)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Get-Command py.exe, python.exe, python3.exe -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $python) { throw 'Python 3.11+ required; install with winget install Python.Python.3.13' }
$folder = Join-Path $env:LOCALAPPDATA 'CarrierSmartHome-Research\cloud-test-venv'
$venvExe = Join-Path $folder 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvExe)) {
    Write-Host 'Creating isolated Carrier SmartHome Python environment...' -ForegroundColor Cyan
    if ($python.Name -eq 'py.exe') {
        & $python.Source -3 -m venv $folder
    } else {
        & $python.Source -m venv $folder
    }
    if ($LASTEXITCODE -ne 0) { throw 'Unable to initialize Python environment.' }
}
if (-not $SkipDependencyInstall) {
    & $venvExe -m pip --disable-pip-version-check install 'aiohttp>=3.9,<4'
    if ($LASTEXITCODE -ne 0) { throw 'Failed to install aiohttp in the isolated environment.' }
}
Write-Host "`n=== CARRIER SMARTHOME NATIVE CLOUD TEST (READ ONLY) ===" -ForegroundColor Cyan
& $venvExe (Join-Path $PSScriptRoot 'Smoke-TestSmartHomeCloud.py')
if ($LASTEXITCODE -ne 0) {
    throw "Carrier cloud test stopped (exit $LASTEXITCODE). See the status lines above. Do not share credentials."
}
Write-Host 'Carrier cloud read-only smoke test passed.' -ForegroundColor Green
