# Read current Carrier native-cloud state; optionally verify known previous values.
# Uses existing isolated Python venv. Sends no thermostat commands. No Matter.
[CmdletBinding()]
param(
    [double]$ExpectedHeat,
    [double]$ExpectedCool,
    [ValidateSet('off','heat','cool','auto','fanonly')][string]$ExpectedMode,
    [ValidateSet('auto','off','low','med','high')][string]$ExpectedFan,
    [ValidateSet('enabled','disabled')][string]$ExpectedSchedule
)
$ErrorActionPreference = 'Stop'
$venv = Join-Path $env:LOCALAPPDATA 'CarrierSmartHome-Research\cloud-test-venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venv -PathType Leaf)) {
    throw 'Isolated Carrier Python environment missing. Run tools\Test-Cloud.ps1 first.'
}
$argsList = @((Join-Path $PSScriptRoot 'Check-CarrierState.py'))
if ($PSBoundParameters.ContainsKey('ExpectedHeat'))     {$argsList += @('--heat-setpoint', [string]::Format([cultureinfo]::InvariantCulture,'{0}', $ExpectedHeat))}
if ($PSBoundParameters.ContainsKey('ExpectedCool'))     {$argsList += @('--cool-setpoint', [string]::Format([cultureinfo]::InvariantCulture,'{0}', $ExpectedCool))}
if ($PSBoundParameters.ContainsKey('ExpectedMode'))     {$argsList += @('--mode', $ExpectedMode)}
if ($PSBoundParameters.ContainsKey('ExpectedFan'))      {$argsList += @('--fan-mode', $ExpectedFan)}
if ($PSBoundParameters.ContainsKey('ExpectedSchedule')) {$argsList += @('--schedule-enabled', $ExpectedSchedule)}
Write-Host '=== CARRIER READ-ONLY NATIVE CLOUD STATE ===' -ForegroundColor Cyan
& $venv @argsList
if ($LASTEXITCODE -ne 0) { throw "Cloud state check did not pass ($LASTEXITCODE); no thermostat commands were sent." }
