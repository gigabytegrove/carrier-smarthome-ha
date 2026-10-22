# Read-only Windows PowerShell probe. No administrator rights required.
[CmdletBinding()]
param(
    [string]$Target,
    [string]$Output
)
$ErrorActionPreference = 'Stop'

function Assert-PrivateIPv4([string]$Address) {
    $parsed = [System.Net.IPAddress]::None
    if (-not [System.Net.IPAddress]::TryParse($Address, [ref]$parsed) -or
        $parsed.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork) {
        throw 'Target must be a valid private IPv4 address.'
    }
    $octets = $parsed.GetAddressBytes()
    if (-not ($octets[0] -eq 10 -or
        ($octets[0] -eq 172 -and $octets[1] -ge 16 -and $octets[1] -le 31) -or
        ($octets[0] -eq 192 -and $octets[1] -eq 168))) {
        throw 'Only RFC1918 private IPv4 targets are allowed.'
    }
    return $parsed.ToString()
}

$neighborList = @(
    Get-NetNeighbor -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.State -notin @('Incomplete', 'Unreachable') -and
            $_.LinkLayerAddress -and $_.LinkLayerAddress -notmatch '^(00-){5}00$' -and
            $_.IPAddress -match '^(10\.|192\.168\.|172\.)' } |
        Select-Object IPAddress, LinkLayerAddress, State, InterfaceAlias
)

$report = [ordered]@{
    timestamp_utc = ([DateTime]::UtcNow.ToString('o'))
    explanation = 'Neighbor list alone cannot identify a thermostat or prove an API exists.'
    neighbors = $neighborList
    target = $null
    reachable_tcp_ports = @()
}

if ($Target) {
    $address = Assert-PrivateIPv4 $Target
    $report.target = $address
    $ports = @(80, 443, 8080, 8443, 1883, 8883)
    $openPorts = @()
    foreach ($port in $ports) {
        $client = [System.Net.Sockets.TcpClient]::new()
        try {
            $task = $client.ConnectAsync($address, $port)
            if ($task.Wait(500) -and $client.Connected) {
                $openPorts += $port
            }
        } catch {
            # A refused port is an ordinary result, not a script failure.
        } finally {
            $client.Dispose()
        }
    }
    $report.reachable_tcp_ports = @($openPorts)
}

$json = $report | ConvertTo-Json -Depth 8
Write-Output $json
if ($Output) {
    $destination = [IO.Path]::GetFullPath($Output)
    if (Test-Path -LiteralPath $destination -PathType Container) {
        throw 'Output must be a file path.'
    }
    [IO.File]::WriteAllText($destination, $json + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
    Write-Host 'Saved private report. Do not publish raw IP/MAC details.'
}
