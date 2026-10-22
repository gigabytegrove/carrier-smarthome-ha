# Carrier SmartHome read-only multi-network discovery for Windows PowerShell 5.1+.
# Scans private, bounded network segments only. Never sends thermostat/API commands.
[CmdletBinding()]
param(
    [string]$Output,
    [string[]]$AdditionalSubnets = @(),
    [int]$PingTimeoutMs = 350,
    [int]$TcpTimeoutMs = 350,
    [int]$MaxNetworks = 8,
    [switch]$NoSweep,
    [switch]$NoPortProbe,
    [switch]$Quick
)
$ErrorActionPreference = 'Stop'
if ($PingTimeoutMs -lt 100 -or $PingTimeoutMs -gt 2500) { throw 'PingTimeoutMs must be 100-2500' }
if ($TcpTimeoutMs -lt 100 -or $TcpTimeoutMs -gt 2500) { throw 'TcpTimeoutMs must be 100-2500' }
if ($MaxNetworks -lt 1 -or $MaxNetworks -gt 16) { throw 'MaxNetworks must be 1-16' }

function Test-PrivateIPv4([string]$Address) {
    $ip = [System.Net.IPAddress]::None
    if (-not [System.Net.IPAddress]::TryParse($Address, [ref]$ip) -or
        $ip.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork) { return $false }
    $b = $ip.GetAddressBytes()
    return ($b[0] -eq 10 -or ($b[0] -eq 172 -and $b[1] -ge 16 -and $b[1] -le 31) -or
        ($b[0] -eq 192 -and $b[1] -eq 168))
}

function Get-BoundedNetwork([string]$Address, [int]$Prefix) {
    if (-not (Test-PrivateIPv4 $Address) -or $Prefix -lt 1 -or $Prefix -gt 32) {
        throw "Invalid private IPv4 network: $Address/$Prefix"
    }
    $bits = [Math]::Max(24, $Prefix)
    $b = [System.Net.IPAddress]::Parse($Address).GetAddressBytes()
    $block = [int][Math]::Pow(2, (32 - $bits))
    $first = [int]([Math]::Floor($b[3] / $block) * $block)
    $network = '{0}.{1}.{2}.{3}/{4}' -f $b[0], $b[1], $b[2], $first, $bits
    $last = $first + $block - 1
    $broadcast = '{0}.{1}.{2}.{3}' -f $b[0], $b[1], $b[2], $last
    if (-not (Test-PrivateIPv4 $broadcast)) { throw "Non-private network end: $network" }
    return [pscustomobject]@{CIDR=$network; A=$b[0]; B=$b[1]; C=$b[2]; First=$first; Last=$last; Prefix=$bits}
}

function Test-NetworkMember([string]$IPAddress, $Network) {
    if (-not (Test-PrivateIPv4 $IPAddress)) { return $false }
    $b = [System.Net.IPAddress]::Parse($IPAddress).GetAddressBytes()
    return ($b[0] -eq $Network.A -and $b[1] -eq $Network.B -and
        $b[2] -eq $Network.C -and $b[3] -ge $Network.First -and $b[3] -le $Network.Last)
}

function Parse-AuthorizedSubnet([string]$Subnet) {
    if ($Subnet -match '^((?:\d{1,3}\.){3}\d{1,3})/(\d{1,2})$') {
        $ip = $Matches[1]
        $n = [int]$Matches[2]
    } else { throw "Invalid CIDR '$Subnet'. Expected a private IPv4 /24-/32." }
    if ($n -lt 24 -or $n -gt 32) { throw "Only explicitly bounded /24-/32 CIDRs allowed: $Subnet" }
    return Get-BoundedNetwork $ip $n
}

$warnings = New-Object 'System.Collections.Generic.List[string]'
$scopes = [ordered]@{}
function Add-Scope($Network, [string]$Source, [string]$InterfaceIP) {
    if ($scopes.Contains($Network.CIDR)) {
        $current = $scopes[$Network.CIDR]
        if ($current.sources -notcontains $Source) { $current.sources += $Source }
        if ($InterfaceIP -and $current.local_ips -notcontains $InterfaceIP) { $current.local_ips += $InterfaceIP }
        return
    }
    $scopes[$Network.CIDR] = [pscustomobject]@{
        network = $Network
        sources = @($Source)
        local_ips = @($(if ($InterfaceIP) { $InterfaceIP }))
    }
}

# Discover ALL connected private IPv4 interfaces, not just the default route.
$connected = @(Get-NetIPInterface -AddressFamily IPv4 -ErrorAction Stop |
    Where-Object { $_.ConnectionState -eq 'Connected' } |
    Select-Object -ExpandProperty InterfaceIndex -Unique)
$localAddresses = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
    Where-Object { $connected -contains $_.InterfaceIndex -and (Test-PrivateIPv4 $_.IPAddress) })
foreach ($address in $localAddresses) {
    $n = Get-BoundedNetwork $address.IPAddress ([int]$address.PrefixLength)
    Add-Scope $n ('connected:' + $address.InterfaceAlias) $address.IPAddress
    if ([int]$address.PrefixLength -lt 24) {
        $warnings.Add("$($address.IPAddress)/$($address.PrefixLength) is wider than /24; scanned only $($n.CIDR). Other /24 slices require an explicit authorized subnet or a probe inside that network.")
    }
}

# Include explicit routed private networks (e.g., a route for the IoT VLAN).
# Default routes 0.0.0.0/0 cannot reveal which VLAN subnets lie beyond the router.
$routed = @(Get-NetRoute -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.NextHop -and $_.NextHop -ne '0.0.0.0' -and $_.DestinationPrefix -match '/\d+$' })
foreach ($route in $routed) {
    $parts = $route.DestinationPrefix -split '/'
    $prefix = [int]$parts[1]
    if ($prefix -lt 24 -or $prefix -gt 30 -or -not (Test-PrivateIPv4 $parts[0])) { continue }
    try {
        $n = Get-BoundedNetwork $parts[0] $prefix
        Add-Scope $n ('route:via-' + $route.NextHop) ''
    } catch {
        $warnings.Add("Ignored invalid routed prefix $($route.DestinationPrefix)")
    }
}
foreach ($subnet in $AdditionalSubnets) {
    $n = Parse-AuthorizedSubnet $subnet
    Add-Scope $n 'user-authorized' ''
}
if ($scopes.Count -eq 0) { throw 'No connected private IPv4 interfaces or authorized subnets were found.' }

$selectedScopes = @($scopes.Values | Select-Object -First $MaxNetworks)
if ($scopes.Count -gt $MaxNetworks) {
    $warnings.Add("Found $($scopes.Count) candidate private networks but only $MaxNetworks were scanned. Increase -MaxNetworks (maximum 16) to authorize additional networks.")
}

Write-Host "`nCARRIER SMARTHOME - MULTI-VLAN NETWORK DISCOVERY" -ForegroundColor Cyan
Write-Host "Found $($scopes.Count) private network scopes; scanning $($selectedScopes.Count)."
Write-Host 'Scope is the connected/reachable private LAN, not every VLAN configured on your router.'
Write-Host 'Probe methods: bounded ICMP, neighbor cache, TCP connects; no HTTP, MQTT, or thermostat commands.'

$ports = @(80, 443, 8080, 8443, 1883, 8883)
$networkResults = @()
foreach ($scope in $selectedScopes) {
    $network = $scope.network
    $cidr = $network.CIDR
    Write-Host "`n=== $cidr ($($scope.sources -join ', ')) ===" -ForegroundColor Cyan
    $targets = @()
    for ($octet = $network.First; $octet -le $network.Last; $octet++) {
        # Do not send ICMP to the network and broadcast addresses except /31 and /32.
        if ($network.Prefix -le 30 -and ($octet -eq $network.First -or $octet -eq $network.Last)) { continue }
        $candidate = '{0}.{1}.{2}.{3}' -f $network.A, $network.B, $network.C, $octet
        if ($scope.local_ips -contains $candidate) { continue }
        $targets += $candidate
    }
    $responded = New-Object 'System.Collections.Generic.List[string]'
    if (-not $NoSweep) {
        Write-Host "ICMP sweep: $($targets.Count) addresses (32 concurrent maximum)."
        for ($offset=0; $offset -lt $targets.Count; $offset+=32) {
            $work = @()
            foreach ($candidate in @($targets | Select-Object -Skip $offset -First 32)) {
                $pinger = [System.Net.NetworkInformation.Ping]::new()
                try {
                    $task = $pinger.SendPingAsync([string]$candidate, $PingTimeoutMs)
                    $work += [pscustomobject]@{IP=$candidate;Instance=$pinger;Task=$task}
                } catch { $pinger.Dispose() }
            }
            foreach ($item in $work) {
                try {
                    if ($item.Task.Wait($PingTimeoutMs + 150) -and
                        $item.Task.Result.Status -eq [System.Net.NetworkInformation.IPStatus]::Success) {
                        $responded.Add($item.IP)
                    }
                } catch { } finally { $item.Instance.Dispose() }
            }
        }
    }
    # Refresh after ping: local ARP/neighbor entries often appear only once probed.
    $neighbors = @(Get-NetNeighbor -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object {
            (Test-NetworkMember $_.IPAddress $network) -and
            $_.State -notin @('Incomplete', 'Unreachable', 'Permanent') -and
            $_.LinkLayerAddress -and $_.LinkLayerAddress -notmatch '^(00[-:]){5}00$'
        } | Sort-Object IPAddress -Unique |
        Select-Object IPAddress, LinkLayerAddress, State, InterfaceAlias)
    # Routed hosts never acquire local ARP entries. Include ping responders regardless of MAC.
    $hostSet = @{}
    foreach ($candidate in $responded) { $hostSet[$candidate] = $true }
    foreach ($n in $neighbors) { $hostSet[[string]$n.IPAddress] = $true }
    $scanIPs = if ($Quick) { @($hostSet.Keys | Sort-Object) } else { @($targets) }
    $listeners = New-Object 'System.Collections.Generic.List[object]'
    if (-not $NoPortProbe) {
        Write-Host "TCP probes: $($scanIPs.Count) IPs x $($ports.Count) ports (32 concurrent maximum)."
        $checks = @()
        foreach ($candidate in $scanIPs) {
            foreach ($port in $ports) {
                $checks += [pscustomobject]@{IP=$candidate;Port=$port}
            }
        }
        for ($offset=0; $offset -lt $checks.Count; $offset+=32) {
            $batch = @()
            foreach ($check in @($checks | Select-Object -Skip $offset -First 32)) {
                $client = [System.Net.Sockets.TcpClient]::new()
                try {
                    $task = $client.ConnectAsync([string]$check.IP, [int]$check.Port)
                    $batch += [pscustomobject]@{IP=$check.IP;Port=$check.Port;Client=$client;Task=$task}
                } catch { $client.Dispose() }
            }
            foreach ($item in $batch) {
                try {
                    if ($item.Task.Wait($TcpTimeoutMs + 150) -and $item.Client.Connected) {
                        $listeners.Add([pscustomobject]@{ip=$item.IP;port=$item.Port})
                        $hostSet[$item.IP] = $true
                    }
                } catch { } finally { $item.Client.Dispose() }
            }
        }
    }
    $result = [pscustomobject]@{
        subnet = $cidr
        sources = @($scope.sources)
        scanner_ips = @($scope.local_ips)
        icmp_responsive = @($responded | Sort-Object -Unique)
        neighbors = @($neighbors)
        common_tcp_listeners = @($listeners | Sort-Object ip, port)
        detected_addresses = @($hostSet.Keys | Sort-Object)
        model_confirmed = $false
        matter_discovery_performed = $false
        note = 'IP/MAC/port results are candidates only. Matter uses IPv6 and UDP; IPv4 TCP absence cannot rule it out.'
    }
    $networkResults += $result
    Write-Host ('Ping responsive: {0}; neighbor records: {1}; TCP listeners: {2}; discovered IPs: {3}' -f
        $responded.Count, $neighbors.Count, $listeners.Count, $hostSet.Count) -ForegroundColor Green
    if ($listeners.Count) { @($listeners | Select-Object -First 15) | Format-Table -AutoSize | Out-Host }
    if (-not $hostSet.Count) { Write-Warning "No devices responded in $cidr; the VLAN may be unreachable or isolated from this computer." }
}

foreach ($note in $warnings) { Write-Warning $note }
if ($scopes.Count -eq 1) {
    Write-Warning 'Only one private network is visible. If the thermostat is on an IoT VLAN routed only by the gateway, its subnet cannot be learned from this computer alone. Run on a host in that VLAN, or supply -AdditionalSubnets after checking your router.'
}
$report = [ordered]@{
    generated_utc = [DateTime]::UtcNow.ToString('o')
    scanner = 'Carrier SmartHome multi-VLAN read-only discovery v2'
    device_model_target = 'TSTATCCEWF-01'
    networks_found = $scopes.Count
    networks_scanned = $networkResults.Count
    network_results = @($networkResults)
    warnings = @($warnings.ToArray())
    thermostat_ip_confirmed = $false
    proprietary_lan_api_confirmed = $false
    limitations = @(
        'Subnets behind a router default route cannot be enumerated from a client routing table.',
        'Local mDNS generally does not cross VLANs unless relayed; Matter requires IPv6/UDP and commissioning.',
        'No cloud/thermostat settings were modified.'
    )
}
if ($Output) {
    $destination = [IO.Path]::GetFullPath($Output)
    if ([IO.File]::Exists($destination) -and ([IO.File]::GetAttributes($destination) -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Refusing to overwrite reparse-point destination.'
    }
    $parent = [IO.Path]::GetDirectoryName($destination)
    if (-not [IO.Directory]::Exists($parent)) { [void][IO.Directory]::CreateDirectory($parent) }
    [IO.File]::WriteAllText($destination, (($report | ConvertTo-Json -Depth 12) + [Environment]::NewLine), [Text.UTF8Encoding]::new($false))
    Write-Host "Saved private network report: $destination" -ForegroundColor Green
}
Write-Host 'No thermostat command issued. Report retains device IP/MAC details only on this computer.'
