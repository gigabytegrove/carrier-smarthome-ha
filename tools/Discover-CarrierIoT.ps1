# Read-only IPv4 discovery for the owner's Carrier SmartHome IoT VLAN.
# Defaults to 172.20.0.0/16, deliberately excluding the unrelated 192.168 LAN.
# Windows PowerShell 5.1 / PowerShell 7+. No admin rights or Python required.
[CmdletBinding()]
param(
    [ValidatePattern('^172\.20\.(?:\d{1,3}\.)\d{1,3}/(?:1[6-9]|2\d|3[0-2])$')]
    [string]$Subnet = '172.20.0.0/16',
    [string]$Output,
    [ValidateRange(100,2500)][int]$PingTimeoutMs = 350,
    [ValidateRange(100,2500)][int]$TcpTimeoutMs = 350,
    [ValidateRange(8,256)][int]$Concurrency = 128,
    [switch]$Deep,
    [switch]$NoTcp,
    [switch]$PlanOnly
)
$ErrorActionPreference = 'Stop'

function ConvertTo-Number([string]$Address) {
    $ip = [System.Net.IPAddress]::None
    if (-not [System.Net.IPAddress]::TryParse($Address, [ref]$ip) -or
        $ip.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork) {
        throw "Invalid IPv4 address: $Address"
    }
    $parts = $ip.GetAddressBytes()
    return ([uint64]$parts[0] * 16777216 + [uint64]$parts[1] * 65536 +
            [uint64]$parts[2] * 256 + [uint64]$parts[3])
}
function ConvertTo-Address([uint64]$Number) {
    return ('{0}.{1}.{2}.{3}' -f
        [int][Math]::Floor($Number / 16777216),
        ([int][Math]::Floor($Number / 65536) % 256),
        ([int][Math]::Floor($Number / 256) % 256),
        ([int]($Number % 256)))
}
function Resolve-Scope([string]$CIDR) {
    $segments = $CIDR.Split('/')
    if ($segments.Length -ne 2) { throw 'CIDR must include a prefix.' }
    $prefix = [int]$segments[1]
    if ($prefix -lt 16 -or $prefix -gt 32) { throw 'IoT scans must use /16-/32.' }
    $address = ConvertTo-Number $segments[0]
    $allowedStart = ConvertTo-Number '172.20.0.0'
    $allowedEnd = ConvertTo-Number '172.20.255.255'
    $blockSize = [uint64][Math]::Pow(2, 32 - $prefix)
    $start = [uint64]([Math]::Floor($address / $blockSize) * $blockSize)
    $end = $start + $blockSize - 1
    if ($start -lt $allowedStart -or $end -gt $allowedEnd) {
        throw 'Refusing to scan outside the user-confirmed 172.20.0.0/16 network.'
    }
    $hostStart = if ($prefix -le 30) { $start + 1 } else { $start }
    $hostEnd = if ($prefix -le 30) { $end - 1 } else { $end }
    return [pscustomobject]@{
        CIDR = ('{0}/{1}' -f (ConvertTo-Address $start), $prefix)
        Start = $hostStart
        End = $hostEnd
        Hosts = [int]($hostEnd - $hostStart + 1)
        Prefix = $prefix
    }
}
function Invoke-PingBatch([string[]]$IPs, [int]$Timeout) {
    $running = New-Object 'System.Collections.Generic.List[object]'
    foreach ($ip in $IPs) {
        $client = [System.Net.NetworkInformation.Ping]::new()
        try {
            $task = $client.SendPingAsync($ip, $Timeout)
            $running.Add([pscustomobject]@{IP=$ip;Client=$client;Task=$task})
        } catch { $client.Dispose() }
    }
    $success = New-Object 'System.Collections.Generic.List[string]'
    foreach ($job in $running) {
        try {
            if ($job.Task.Wait($Timeout + 200) -and
                $job.Task.Result.Status -eq [System.Net.NetworkInformation.IPStatus]::Success) {
                $success.Add($job.IP)
            }
        } catch { } finally { $job.Client.Dispose() }
    }
    return @($success.ToArray())
}
function Invoke-TcpBatch($Checks, [int]$Timeout) {
    $running = New-Object 'System.Collections.Generic.List[object]'
    foreach ($check in $Checks) {
        $client = [System.Net.Sockets.TcpClient]::new()
        try {
            $task = $client.ConnectAsync([string]$check.IP, [int]$check.Port)
            $running.Add([pscustomobject]@{IP=$check.IP;Port=$check.Port;Client=$client;Task=$task})
        } catch { $client.Dispose() }
    }
    $open = New-Object 'System.Collections.Generic.List[object]'
    foreach ($job in $running) {
        try {
            if ($job.Task.Wait($Timeout + 200) -and $job.Client.Connected) {
                $open.Add([pscustomobject]@{ip=$job.IP;port=$job.Port})
            }
        } catch { } finally { $job.Client.Dispose() }
    }
    return @($open.ToArray())
}

$scope = Resolve-Scope $Subnet
$ports = @(80,443,8080,8443,1883,8883)
Write-Host "`n=== CARRIER SMARTHOME - TARGETED IoT VLAN DISCOVERY ===" -ForegroundColor Cyan
Write-Host "Target: $($scope.CIDR) | Usable IPv4 addresses: $($scope.Hosts)"
Write-Host 'Other networks (including 192.168.x.x) are excluded.'
Write-Host 'ICMP and TCP connect checks only: no HTTP, MQTT, cloud login, or thermostat commands.'
if ($Deep) { Write-Warning 'Deep mode additionally checks TCP 80/443 on all addresses not already tested.' }

# Report the best-matching entry from the route table. Find-NetRoute returns
# interface-oriented objects on some Windows builds and can leave NextHop and
# DestinationPrefix empty; Get-NetRoute supplies the actual route properties.
# This is a *route-table observation*, not proof that VLAN firewall rules allow traffic.
$routeInfo = $null
try {
    $targetAddress = [uint64]$scope.Start
    $routeMatches = New-Object 'System.Collections.Generic.List[object]'
    foreach ($item in @(Get-NetRoute -AddressFamily IPv4 -ErrorAction Stop)) {
        $routeParts = ([string]$item.DestinationPrefix).Split('/')
        if ($routeParts.Count -ne 2) { continue }
        $bits = 0
        if (-not [int]::TryParse($routeParts[1], [ref]$bits) -or $bits -lt 0 -or $bits -gt 32) { continue }
        try { $routeStart = ConvertTo-Number $routeParts[0] } catch { continue }
        $block = [uint64][Math]::Pow(2, 32 - $bits)
        if ([Math]::Floor($targetAddress / $block) -ne [Math]::Floor($routeStart / $block)) { continue }
        $routeMatches.Add([pscustomobject]@{
            entry = $item
            bits = $bits
            metric = [int]$item.RouteMetric
        })
    }
    $best = $routeMatches | Sort-Object -Property @(
        @{Expression={$_.bits};Descending=$true},
        @{Expression={$_.metric};Descending=$false}
    ) | Select-Object -First 1
    if ($best) {
        $routeInfo = [pscustomobject]@{
            interface_alias = [string]$best.entry.InterfaceAlias
            interface_index = [int]$best.entry.InterfaceIndex
            next_hop = [string]$best.entry.NextHop
            destination_prefix = [string]$best.entry.DestinationPrefix
            route_metric = [int]$best.entry.RouteMetric
        }
        Write-Host ('Best matching Windows route: {0}, via {1}, interface {2}' -f
            $routeInfo.destination_prefix, $routeInfo.next_hop, $routeInfo.interface_alias)
        if ($best.bits -eq 0) {
            Write-Warning 'Only the default IPv4 route matches this IoT address; the VLAN is not explicitly routed on Windows.'
        }
    } else {
        Write-Warning 'No matching Windows IPv4 route was returned; ICMP results must be evaluated separately.'
    }
} catch { Write-Warning ('Unable to inspect Windows route table: ' + $_.Exception.Message) }

$metadata = [ordered]@{
    generated_utc = [DateTime]::UtcNow.ToString('o')
    target = $scope.CIDR
    usable_addresses = $scope.Hosts
    route = $routeInfo
    scan_mode = $(if ($Deep) {'deep'} else {'staged'})
    addresses_pinged = 0
    tcp_checks_attempted = 0
    tcp_silent_host_coverage = $(if ($NoTcp) {'disabled'} elseif ($Deep) {'80,443'} else {'not_scanned'})
    icmp_responsive = @()
    candidate_addresses = @()
    neighbor_records = @()
    tcp_open = @()
    per_24_summary = @()
    thermostat_ip_confirmed = $false
    proprietary_local_api_confirmed = $false
    limitations = @(
        'Most devices will not accept incoming connections; no TCP reply does not mean the thermostat is absent.',
        'Matter depends on IPv6 and UDP/mDNS, which IPv4 scanning cannot assess across isolated VLANs.',
        'Routed remote hosts will generally not have a local ARP/MAC entry.',
        'No hostname, MAC or TCP port alone is proof of thermostat identity.'
    )
}
if ($PlanOnly) {
    $metadata['note'] = 'Plan only: no packets sent.'
    $metadata | ConvertTo-Json -Depth 8
    return
}

$responded = New-Object 'System.Collections.Generic.HashSet[string]'
Write-Host "`nSweeping $($scope.Hosts) addresses (at most $Concurrency concurrent ICMP requests)..."
$started = [DateTime]::UtcNow
for ([uint64]$offset = 0; $offset -lt [uint64]$scope.Hosts; $offset += [uint64]$Concurrency) {
    $batch = New-Object 'System.Collections.Generic.List[string]'
    $endOffset = [Math]::Min([uint64]$scope.Hosts, $offset + [uint64]$Concurrency)
    for ([uint64]$position = $offset; $position -lt $endOffset; $position++) {
        $batch.Add((ConvertTo-Address ([uint64]$scope.Start + $position)))
    }
    foreach ($ip in @(Invoke-PingBatch $batch.ToArray() $PingTimeoutMs)) {
        [void]$responded.Add([string]$ip)
    }
    if (([uint64]$offset -eq 0) -or ([uint64]$offset % 4096 -eq 0)) {
        Write-Host ('ICMP progress: {0}/{1}; responsive: {2}' -f $endOffset, $scope.Hosts, $responded.Count)
    }
}
$metadata.addresses_pinged = $scope.Hosts
$metadata.icmp_responsive = @($responded | Sort-Object)

$neighbors = @()
try {
    $neighbors = @(Get-NetNeighbor -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object {
            $_.IPAddress -match '^172\.20\.' -and
            $_.State -notin @('Incomplete', 'Unreachable', 'Permanent') -and
            $_.LinkLayerAddress -and $_.LinkLayerAddress -notmatch '^(00[-:]){5}00$' -and
            (ConvertTo-Number $_.IPAddress) -ge $scope.Start -and
            (ConvertTo-Number $_.IPAddress) -le $scope.End
        } | Select-Object IPAddress,LinkLayerAddress,State,InterfaceAlias)
} catch { Write-Warning 'Could not read Windows neighbor cache.' }
foreach ($neighbor in $neighbors) { [void]$responded.Add([string]$neighbor.IPAddress) }
$metadata.neighbor_records = @($neighbors)
$metadata.candidate_addresses = @($responded | Sort-Object)

$open = New-Object 'System.Collections.Generic.List[object]'
$hostlist = @($responded | Sort-Object)
if (-not $NoTcp -and $hostlist.Count -gt 0) {
    Write-Host "`nChecking $($ports.Count) TCP ports on $($hostlist.Count) candidate hosts..."
    $buffer = New-Object 'System.Collections.Generic.List[object]'
    foreach ($ip in $hostlist) {
        foreach ($port in $ports) {
            $buffer.Add([pscustomobject]@{IP=$ip;Port=$port})
            if ($buffer.Count -ge $Concurrency) {
                foreach ($record in @(Invoke-TcpBatch $buffer.ToArray() $TcpTimeoutMs)) { $open.Add($record) }
                $metadata.tcp_checks_attempted += $buffer.Count
                $buffer.Clear()
            }
        }
    }
    if ($buffer.Count) {
        foreach ($record in @(Invoke-TcpBatch $buffer.ToArray() $TcpTimeoutMs)) { $open.Add($record) }
        $metadata.tcp_checks_attempted += $buffer.Count
    }
}

if ($Deep -and -not $NoTcp) {
    Write-Host "`nDeep check: TCP 80/443 on nonresponding addresses (additional traffic/time)..."
    $buffer = New-Object 'System.Collections.Generic.List[object]'
    for ([uint64]$value=$scope.Start; $value -le $scope.End; $value++) {
        $ip = ConvertTo-Address $value
        if ($responded.Contains($ip)) { continue }
        foreach ($port in @(80,443)) {
            $buffer.Add([pscustomobject]@{IP=$ip;Port=$port})
            if ($buffer.Count -ge $Concurrency) {
                foreach ($record in @(Invoke-TcpBatch $buffer.ToArray() $TcpTimeoutMs)) { $open.Add($record) }
                $metadata.tcp_checks_attempted += $buffer.Count
                $buffer.Clear()
            }
        }
    }
    if ($buffer.Count) {
        foreach ($record in @(Invoke-TcpBatch $buffer.ToArray() $TcpTimeoutMs)) { $open.Add($record) }
        $metadata.tcp_checks_attempted += $buffer.Count
    }
}
$metadata.tcp_open = @($open.ToArray() | Sort-Object ip,port -Unique)
$grouped = @{}
foreach ($ip in $responded) {
    $slice = [string]([System.Net.IPAddress]::Parse($ip).GetAddressBytes()[2])
    if (-not $grouped.ContainsKey($slice)) { $grouped[$slice] = [pscustomobject]@{subnet="172.20.$slice.0/24";responsive=0;open_ports=0} }
    $grouped[$slice].responsive++
}
foreach ($record in $metadata.tcp_open) {
    $slice = [string]([System.Net.IPAddress]::Parse($record.ip).GetAddressBytes()[2])
    if (-not $grouped.ContainsKey($slice)) { $grouped[$slice] = [pscustomobject]@{subnet="172.20.$slice.0/24";responsive=0;open_ports=0} }
    $grouped[$slice].open_ports++
}
$metadata.per_24_summary = @($grouped.Values | Sort-Object subnet)
$metadata['elapsed_seconds'] = [Math]::Round(([DateTime]::UtcNow - $started).TotalSeconds, 1)

Write-Host "`n=== IoT VLAN RESULTS ===" -ForegroundColor Green
Write-Host ('ICMP/neighbor candidates: {0}; TCP listeners: {1}; elapsed: {2} seconds' -f
    $responded.Count, $metadata.tcp_open.Count, $metadata.elapsed_seconds)
if ($metadata.per_24_summary.Count) { $metadata.per_24_summary | Format-Table -AutoSize | Out-Host }
if (-not $responded.Count -and -not $metadata.tcp_open.Count) {
    Write-Warning 'No hosts replied. Could be inter-VLAN filtering, disabled ICMP/inbound TCP, or no route; this does not prove absence of the thermostat.'
}
if ($Output) {
    $path = [IO.Path]::GetFullPath($Output)
    if ([IO.File]::Exists($path) -and ([IO.File]::GetAttributes($path) -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Refusing to overwrite a reparse-point destination.'
    }
    $directory = [IO.Path]::GetDirectoryName($path)
    if (-not [IO.Directory]::Exists($directory)) { [void][IO.Directory]::CreateDirectory($directory) }
    [IO.File]::WriteAllText($path, (($metadata | ConvertTo-Json -Depth 10) + [Environment]::NewLine), [Text.UTF8Encoding]::new($false))
    Write-Host "Private scan report: $path"
} else {
    $metadata | ConvertTo-Json -Depth 10
}
Write-Host 'Identity remains unconfirmed. No configuration or setpoint commands were sent.'
