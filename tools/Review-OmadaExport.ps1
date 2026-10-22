# Analyze an existing Omada Client_*.zip export and the saved IoT scan.
# Works offline; never contacts Omada, Carrier, or thermostat. PowerShell 5.1+.
[CmdletBinding()]
param([string]$ArchivePath, [string]$ScanPath, [string]$MacSuffix = '')
$ErrorActionPreference = 'Stop'
if (-not $ArchivePath) {
    $downloads = Join-Path $env:USERPROFILE 'Downloads'
    $candidates = @(Get-ChildItem -LiteralPath $downloads -Filter 'Client_*.zip' -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTimeUtc -Descending)
    if ($candidates.Count -eq 0) {
        throw "No Omada Client_*.zip found in Downloads. Save your export there or supply -ArchivePath."
    }
    $ArchivePath = $candidates[0].FullName
}
if (-not (Test-Path -LiteralPath $ArchivePath -PathType Leaf)) {
    throw "Omada export not found: $ArchivePath"
}
if (-not $ScanPath) {
    $base = Join-Path $env:LOCALAPPDATA 'CarrierSmartHome-Research'
    $saved = @(Get-ChildItem -LiteralPath $base -Recurse -Filter 'iot-private.json' -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1)
    if ($saved.Count -gt 0) { $ScanPath = $saved[0].FullName }
}
$py = Get-Command py.exe, python.exe, python3.exe -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $py) { throw 'Python is required. It was used by the earlier Carrier research tools.' }
$arguments = @((Join-Path $PSScriptRoot 'omada_identity.py'), $ArchivePath)
if ($MacSuffix) { $arguments += @('--suffix', $MacSuffix) }
if ($ScanPath) { $arguments += @('--scan', $ScanPath) }
Write-Host "`n=== CARRIER SMARTHOME OMADA EXPORT REVIEW ===" -ForegroundColor Cyan
Write-Host "Export: $ArchivePath"
if ($ScanPath) { Write-Host "Saved IoT scan: $ScanPath" }
& $py.Source @arguments
if ($LASTEXITCODE -ne 0) { throw "Omada review failed (exit $LASTEXITCODE)" }
