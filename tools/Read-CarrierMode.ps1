# Bounded read-only comparison of native Carrier GraphQL list vs detail.
[CmdletBinding()]
param([ValidateRange(1,12)][int]$Samples=5,
      [ValidateRange(10,300)][int]$IntervalSeconds=15)
$ErrorActionPreference='Stop'
$python=Join-Path $env:LOCALAPPDATA 'CarrierSmartHome-Research\cloud-test-venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw 'Carrier isolated cloud Python environment missing. First run tools\Test-Cloud.ps1.'
}
& $python (Join-Path $PSScriptRoot 'Read-CarrierMode.py') --samples $Samples --interval $IntervalSeconds
if ($LASTEXITCODE -ne 0) { throw "Read-only Carrier cloud diagnostic exited with code $LASTEXITCODE" }
