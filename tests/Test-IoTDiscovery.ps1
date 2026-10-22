# Windows PowerShell 5.1+/PowerShell 7+ offline plan validation.
# Run: powershell.exe -NoProfile -ExecutionPolicy Bypass -File tests\Test-IoTDiscovery.ps1
$ErrorActionPreference = 'Stop'
$script = Join-Path (Split-Path -Parent $PSScriptRoot) 'tools\Discover-CarrierIoT.ps1'
function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw "FAIL: $Message" }
}
$default = (& $script -PlanOnly | Out-String | ConvertFrom-Json)
Assert-True ($default.target -eq '172.20.0.0/16') 'default target must be IoT /16'
Assert-True ($default.usable_addresses -eq 65534) 'default host count must be 65534'
Assert-True ($default.note -match 'no packets') 'plan-only must not probe'
$small = (& $script -Subnet '172.20.32.0/24' -PlanOnly | Out-String | ConvertFrom-Json)
Assert-True ($small.target -eq '172.20.32.0/24') '/24 must remain bounded'
Assert-True ($small.usable_addresses -eq 254) '/24 must have 254 usable addresses'
foreach ($invalid in @('172.21.0.0/16', '192.168.0.0/16', '172.20.0.0/8', '172.20.999.0/24')) {
    $failed = $false
    try { & $script -Subnet $invalid -PlanOnly *>$null } catch { $failed = $true }
    Assert-True $failed "must reject $invalid"
}
Write-Host 'PASS: Targeted IoT scanner plan and safety checks (offline).' -ForegroundColor Green
