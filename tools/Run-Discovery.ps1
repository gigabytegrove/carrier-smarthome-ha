# Automatic first-pass Carrier SmartHome research on Windows 10/11.
# No IP, domain, token, username, or password required. Read-only.
[CmdletBinding()]
param(
    [switch]$SkipLocal,
    [switch]$SkipPublicCloud,
    [switch]$NoTcp,
    [switch]$Quick,
    [string[]]$AdditionalSubnets = @(),
    [int]$MaxNetworks = 8
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$destination = Join-Path $env:LOCALAPPDATA ('CarrierSmartHome-Research\' + $stamp)
New-Item -ItemType Directory -Path $destination -Force | Out-Null
Write-Host "`n=== CARRIER SMARTHOME AUTOMATIC DISCOVERY ===" -ForegroundColor Cyan
Write-Host "Device model: TSTATCCEWF-01 | Research directory: $destination"
Write-Host 'No Carrier account credentials, thermostat IP, or API URL required.'

$results = [ordered]@{
    generated_utc = [DateTime]::UtcNow.ToString('o')
    application = 'Carrier SmartHome com.carrier.home 1.2.42'
    model_target = 'TSTATCCEWF-01'
    local_discovery = 'not_run'
    cloud_discovery = 'not_run'
    endpoint_authenticated = $false
    thermostat_ip_confirmed = $false
}
if (-not $SkipLocal) {
    Write-Host "`n=== AUTOMATIC LOCAL LAN DISCOVERY ===" -ForegroundColor Cyan
    $script = Join-Path $PSScriptRoot 'Probe-CarrierSmartHome.ps1'
    try {
        $params = @{Output = (Join-Path $destination 'lan-private.json')}
        if ($NoTcp) {$params['NoPortProbe'] = $true}
        if ($Quick) {$params['Quick'] = $true}
        $params['AdditionalSubnets'] = $AdditionalSubnets
        $params['MaxNetworks'] = $MaxNetworks
        & $script @params
        $results.local_discovery = 'completed; not model-confirmed'
        $lan = Get-Content -LiteralPath $params['Output'] -Raw | ConvertFrom-Json
        $results.local_networks_scanned = [int]$lan.networks_scanned
        $results.local_network_cidrs = @($lan.network_results | ForEach-Object { $_.subnet })
    } catch {
        $results.local_discovery = 'failed'
        Write-Warning ('Local discovery could not complete: ' + $_.Exception.Message)
    }
}
Write-Host "`n=== OFFLINE CLOUD EVIDENCE ===" -ForegroundColor Cyan
$report = Join-Path $repo 'research\transport-evidence.json'
if (Test-Path -LiteralPath $report) {
    $info = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
    Write-Host 'Extracted native service addresses (NOT asserted for this model):'
    $info.native_dex_urls | ForEach-Object {Write-Host ('  ' + $_.url)}
    Write-Host ('GraphQL paths: ' + (($info.graphql_routes | ForEach-Object {$_.route}) -join ', '))
}
if (-not $SkipPublicCloud) {
    $py = Get-Command py.exe, python.exe, python3.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($py) {
        Write-Host "`n=== PUBLIC PORTAL CONFIGURATION DISCOVERY ===" -ForegroundColor Cyan
        $cloudFile = Join-Path $destination 'cloud-public.json'
        & $py.Source (Join-Path $PSScriptRoot 'discover_cloud.py') --max-assets 3 --timeout 4 --output $cloudFile
        if ($LASTEXITCODE -eq 0) {$results.cloud_discovery = 'public-only completed'}
        else {$results.cloud_discovery = 'public portal unavailable'}
    } else {
        $results.cloud_discovery = 'Python not found; native APK evidence still available'
        Write-Warning 'Python was not detected; public cloud JavaScript discovery was skipped.'
    }
}
($results | ConvertTo-Json -Depth 6) | Set-Content -Path (Join-Path $destination 'status.json') -Encoding UTF8
Write-Host "`n=== DISCOVERY FINISHED ===" -ForegroundColor Green
Write-Host "Evidence directory: $destination"
Write-Host 'Never upload raw HAR captures or unredacted token/session files.'
Write-Host 'No appliance setting was changed. Any detected neighbor remains unconfirmed until its identity is correlated.'
