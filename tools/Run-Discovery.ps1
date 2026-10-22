# Automatic first-pass Carrier SmartHome research on Windows 10/11.
# No IP, domain, token, username, or password required. Read-only.
[CmdletBinding()]
param(
    [switch]$SkipLocal,
    [switch]$SkipPublicCloud,
    [switch]$NoTcp,
    [switch]$Quick,
    [string[]]$AdditionalSubnets = @(),
    [int]$MaxNetworks = 8,
    [string]$IoTSubnet = '172.20.0.0/16',
    [switch]$IncludeOtherNetworks,
    [switch]$DeepIoT,
    [switch]$PlanOnly,
    [switch]$ReviewOnly
)
$ErrorActionPreference = 'Stop'
if ($ReviewOnly) {
    # Reuse existing scan; do not repeat cloud discovery or the 65,534-host sweep.
    & (Join-Path $PSScriptRoot 'Review-IoTScan.ps1')
    return
}
$repo = Split-Path -Parent $PSScriptRoot
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$destination = Join-Path $env:LOCALAPPDATA ('CarrierSmartHome-Research\' + $stamp)
New-Item -ItemType Directory -Path $destination -Force | Out-Null
Write-Host "`n=== CARRIER SMARTHOME AUTOMATIC DISCOVERY ===" -ForegroundColor Cyan
Write-Host "Device model: TSTATCCEWF-01 | Research directory: $destination"
Write-Host 'IoT target: 172.20.0.0/16 unless -IoTSubnet is supplied; 192.168 is excluded by default.'
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
Write-Host "`n=== OFFLINE CLOUD EVIDENCE ===" -ForegroundColor Cyan
$report = Join-Path $repo 'research\transport-evidence.json'
if (Test-Path -LiteralPath $report) {
    $info = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
    Write-Host 'Extracted native service addresses (NOT asserted for this model):'
    $info.native_dex_urls | ForEach-Object {Write-Host ('  ' + $_.url)}
    Write-Host ('GraphQL paths: ' + (($info.graphql_routes | ForEach-Object {$_.route}) -join ', '))
}
if (-not $SkipPublicCloud -and -not $PlanOnly) {
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

if (-not $SkipLocal) {
    Write-Host "`n=== TARGETED CARRIER IoT VLAN DISCOVERY ===" -ForegroundColor Cyan
    $script = Join-Path $PSScriptRoot 'Discover-CarrierIoT.ps1'
    try {
        $params = @{ Subnet = $IoTSubnet; Output = (Join-Path $destination 'iot-private.json') }
        if ($NoTcp) { $params['NoTcp'] = $true }
        if ($DeepIoT) { $params['Deep'] = $true }
        if ($PlanOnly) { $params['PlanOnly'] = $true }
        # Quick only affects the optional general-LAN sweep; the IoT /16 ICMP sweep
        # must remain complete rather than silently sampling 1/256 of the network.
        & $script @params
        if ($PlanOnly) {
            $results.local_discovery = 'plan-only; no network probes'
        } else {
            $results.local_discovery = 'IoT network probed; thermostat not identified'
            $iot = Get-Content -LiteralPath $params['Output'] -Raw | ConvertFrom-Json
            $results.local_networks_scanned = 1
            $results.local_network_cidrs = @($iot.target)
            $results.iot_hosts_pinged = [int]$iot.addresses_pinged
            $results.iot_candidates = @($iot.candidate_addresses).Count
            $results.iot_tcp_listeners = @($iot.tcp_open).Count
        }
    } catch {
        $results.local_discovery = 'failed'
        Write-Warning ('IoT discovery failed: ' + $_.Exception.Message)
    }
    if ($IncludeOtherNetworks) {
        Write-Host "`n=== OPTIONAL OTHER PRIVATE LAN DISCOVERY ===" -ForegroundColor Cyan
        $general = Join-Path $PSScriptRoot 'Probe-CarrierSmartHome.ps1'
        try {
            $generalParams = @{Output = (Join-Path $destination 'other-lans-private.json')}
            if ($NoTcp) {$generalParams['NoPortProbe'] = $true}
            if ($Quick) {$generalParams['Quick'] = $true}
            $generalParams['AdditionalSubnets'] = $AdditionalSubnets
            $generalParams['MaxNetworks'] = $MaxNetworks
            if (-not $PlanOnly) { & $general @generalParams }
        } catch { Write-Warning ('Optional general LAN discovery failed: ' + $_.Exception.Message) }
    }
}
($results | ConvertTo-Json -Depth 6) | Set-Content -Path (Join-Path $destination 'status.json') -Encoding UTF8
Write-Host "`n=== DISCOVERY FINISHED ===" -ForegroundColor Green
Write-Host "Evidence directory: $destination"
Write-Host 'Never upload raw HAR captures or unredacted token/session files.'
Write-Host 'No appliance setting was changed. Any detected neighbor remains unconfirmed until its identity is correlated.'
