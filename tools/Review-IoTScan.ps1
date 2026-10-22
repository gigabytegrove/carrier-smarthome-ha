# Review the most recent Carrier IoT scan in place; zero network requests.
# Windows PowerShell 5.1+; relies on Python already used by cloud discovery.
[CmdletBinding()]
param([string]$InputPath)
$ErrorActionPreference = 'Stop'
$base = Join-Path $env:LOCALAPPDATA 'CarrierSmartHome-Research'
if (-not $InputPath) {
    $latest = @(Get-ChildItem -LiteralPath $base -Recurse -Filter 'iot-private.json' -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1)
    if ($latest.Count -lt 1) { throw "No IoT scan found under $base. Run Run-Discovery.ps1 first." }
    $InputPath = $latest[0].FullName
}
if (-not (Test-Path -LiteralPath $InputPath -PathType Leaf)) { throw "Scan file not found: $InputPath" }
$py = Get-Command py.exe, python.exe, python3.exe -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $py) { throw 'Python is required to review saved scan reports.' }
Write-Host "`nSaved scan: $InputPath" -ForegroundColor Cyan
& $py.Source (Join-Path $PSScriptRoot 'triage_iot.py') $InputPath
if ($LASTEXITCODE -ne 0) { throw "Carrier IoT review failed with exit code $LASTEXITCODE" }
