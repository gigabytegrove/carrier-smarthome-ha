# Windows 10/11 read-only LAN discovery; detects connected private subnet automatically.
# Uses ICMP echo to populate the ARP table. Does not send Carrier commands or modify devices.
[CmdletBinding()]
param(
    [string]$Output,
    [int]$PingTimeoutMs = 400,
    [int]$TcpTimeoutMs = 400,
    [switch]$NoSweep,
    [switch]$NoPortProbe
)
$ErrorActionPreference = 'Stop'
if ($PingTimeoutMs -lt 100 -or $PingTimeoutMs -gt 2500) { throw 'PingTimeoutMs must be 100–2500' }
if ($TcpTimeoutMs -lt 100 -or $TcpTimeoutMs -gt 2500) { throw 'TcpTimeoutMs must be 100–2500' }

function Test-PrivateIPv4([string]$Address) {
    $ip = [System.Net.IPAddress]::None
    if (-not [System.Net.IPAddress]::TryParse($Address, [ref]$ip) -or
        $ip.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork) { return $false }
    $b = $ip.GetAddressBytes()
    return ($b[0] -eq 10 -or ($b[0] -eq 172 -and $b[1] -ge 16 -and $b[1] -le 31) -or
        ($b[0] -eq 192 -and $b[1] -eq 168))
}

$routes = @(Get-NetRoute -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' -ErrorAction Stop |
    Sort-Object RouteMetric, InterfaceMetric)
$selected = $null
foreach ($route in $routes) {
    if (-not (Test-PrivateIPv4 $route.NextHop)) { continue }
    $addr = @(Get-NetIPAddress -AddressFamily IPv4 -InterfaceIndex $route.InterfaceIndex -ErrorAction SilentlyContinue |
        Where-Object { Test-PrivateIPv4 $_.IPAddress } | Select-Object -First 1)
    if ($addr.Count) {
        $selected = $addr[0]
        break
    }
}
if (-not $selected) {
    throw 'No connected private IPv4 default route found. Connect to the same LAN as the thermostat.'
}

$bytes = [System.Net.IPAddress]::Parse($selected.IPAddress).GetAddressBytes()
$prefix = [int]$selected.PrefixLength
# Do not traverse wider than a /24, even if LAN is /16; honor smaller subnets.
$bits = [Math]::Min(32, [Math]::Max(24, $prefix))
$block = [int][Math]::Pow(2, 32 - $bits)
$start = [int]([Math]::Floor($bytes[3] / $block) * $block)
$end = $start + $block - 1
$network = '{0}.{1}.{2}.{3}/{4}' -f $bytes[0], $bytes[1], $bytes[2], $start, $bits
$interface = $selected.InterfaceIndex

Write-Host "`nCARRIER SMARTHOME - AUTOMATIC LOCAL DISCOVERY" -ForegroundColor Cyan
Write-Host "Selected network: $network | Local interface: $($selected.IPAddress)"
if (-not $NoSweep) {
    Write-Host 'Populating local neighbor cache (read-only ICMP discovery)...'
    $targets = @($start..$end | Where-Object { $_ -ne $start -and $_ -ne $end } |
        ForEach-Object { '{0}.{1}.{2}.{3}' -f $bytes[0], $bytes[1], $bytes[2], $_ } |
        Where-Object { $_ -ne $selected.IPAddress })
    # Throttled batches: avoid 250 concurrent ping instances and never probe outside local /24.
    for ($offset = 0; $offset -lt $targets.Count; $offset += 32) {
        $pings = @()
        foreach ($address in @($targets | Select-Object -Skip $offset -First 32)) {
            $worker = [System.Net.NetworkInformation.Ping]::new()
            try { $pings += [pscustomobject]@{ Instance = $worker; Task = $worker.SendPingAsync($address, $PingTimeoutMs) } }
            catch { $worker.Dispose() }
        }
        foreach ($item in $pings) {
            try { [void]$item.Task.Wait($PingTimeoutMs + 300) } catch { }
            $item.Instance.Dispose()
        }
    }
}

$neighbors = @(Get-NetNeighbor -InterfaceIndex $interface -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object {
        (Test-PrivateIPv4 $_.IPAddress) -and
        $_.State -notin @('Incomplete', 'Unreachable', 'Permanent') -and
        $_.LinkLayerAddress -and
        $_.LinkLayerAddress -notmatch '^(00[-:]){5}00$'
    } | Sort-Object IPAddress -Unique |
    Select-Object IPAddress, LinkLayerAddress, State, InterfaceAlias)

$openPorts = @()
if (-not $NoPortProbe -and $neighbors.Count) {
    Write-Host 'Checking common local TCP listeners (connection-only; no HTTP or MQTT commands)...'
    $checks = @()
    foreach ($n in $neighbors) {
        foreach ($port in @(80, 443, 8080, 8443, 1883, 8883)) {
            $client = [System.Net.Sockets.TcpClient]::new()
            try {
                $task = $client.ConnectAsync([string]$n.IPAddress, [int]$port)
                $checks += [pscustomobject]@{ IP = $n.IPAddress; Port = $port; Client = $client; Task = $task }
            } catch { $client.Dispose() }
        }
    }
    foreach ($check in $checks) {
        try {
            if ($check.Task.Wait($TcpTimeoutMs + 150) -and $check.Client.Connected) {
                $openPorts += [pscustomobject]@{ ip = $check.IP; port = $check.Port }
            }
        } catch { }
        finally { $check.Client.Dispose() }
    }
}

$report = [ordered]@{
    generated_utc = [DateTime]::UtcNow.ToString('o')
    selected_subnet = $network
    local_interface_ip = $selected.IPAddress
    description = 'IPs are LAN devices, not confirmed Carrier thermostat identities. The thermostat may not reply to ICMP or expose conventional TCP ports.'
    neighbors = @($neighbors)
    common_tcp_listeners = @($openPorts)
    thermostat_ip_confirmed = $null
}

Write-Host "`nDetected $($neighbors.Count) LAN neighbor entries:" -ForegroundColor Green
$neighbors | Format-Table -AutoSize | Out-Host
if ($openPorts.Count) {
    Write-Host 'Reachable TCP listeners (not necessarily thermostat APIs):'
    $openPorts | Format-Table -AutoSize | Out-Host
} else { Write-Host 'No conventional TCP listeners detected; Matter may still work over IPv6/UDP.' }
Write-Host 'No thermostat setting was changed. Correlate its Wi-Fi MAC or DHCP hostname if available.'
$json = $report | ConvertTo-Json -Depth 8
if ($Output) {
    $destination = [IO.Path]::GetFullPath($Output)
    if ([IO.File]::Exists($destination) -and ([IO.File]::GetAttributes($destination) -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Refusing to overwrite reparse-point destination.'
    }
    $parent = [IO.Path]::GetDirectoryName($destination)
    if (-not [IO.Directory]::Exists($parent)) { [void][IO.Directory]::CreateDirectory($parent) }
    [IO.File]::WriteAllText($destination, $json + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
    Write-Host "Saved locally: $destination (do not commit raw IP/MAC data)"
}
