#!/usr/bin/env python3
"""Zero-argument, read-only Carrier SmartHome discovery for Linux and Windows.

Discovers the active private LAN (never scans public space), listens for mDNS,
uses a bounded /24 TCP connect scan, and records possible local devices. Does
not claim a responsive IP is a Carrier thermostat. Carrier API URL candidates
come from APK evidence, not user input or hostname guessing. No credentials.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any

# Import existing, independently tested parsing/port/multicast primitives.
from probe_local import discover_mdns, neighbors, scan_hosts, is_rfc1918


def private_route_network(ip: str, prefix: int) -> ipaddress.IPv4Network:
    address = ipaddress.ip_address(ip)
    if not isinstance(address, ipaddress.IPv4Address) or not is_rfc1918(address):
        raise ValueError('Selected address is not a private IPv4 address')
    if not 0 < prefix <= 32:
        raise ValueError('Invalid interface prefix length')
    # Bound scan at /24 even if the connected subnet is wider.
    return ipaddress.ip_network(f'{ip}/{max(prefix, 24)}', strict=False)


def _powershell_json(script: str) -> Any:
    executable = shutil.which('powershell.exe') or shutil.which('pwsh.exe')
    if not executable:
        raise RuntimeError('PowerShell unavailable')
    result = subprocess.run([executable, '-NoProfile', '-NonInteractive', '-Command', script],
                            capture_output=True, text=True, timeout=20, check=True)
    return json.loads(result.stdout)


def windows_routes() -> list[dict]:
    script = r'''
$ErrorActionPreference='Stop'
$routes=@(Get-NetRoute -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' |
 Sort-Object RouteMetric,InterfaceMetric)
$result=@()
foreach($r in $routes){
 $ips=@(Get-NetIPAddress -AddressFamily IPv4 -InterfaceIndex $r.InterfaceIndex -ErrorAction SilentlyContinue)
 foreach($ip in $ips){
   $result+=@{ip=$ip.IPAddress;prefix=[int]$ip.PrefixLength;gateway=$r.NextHop;
             metric=[int]($r.RouteMetric+$r.InterfaceMetric);index=$r.InterfaceIndex}
 }
}
ConvertTo-Json -InputObject @($result) -Depth 5 -Compress
'''
    value = _powershell_json(script)
    return value if isinstance(value, list) else [value]


def linux_routes() -> list[dict]:
    def call(*args):
        proc = subprocess.run(args, capture_output=True, text=True, timeout=10, check=True)
        return json.loads(proc.stdout)
    routes = call('ip', '-j', '-4', 'route', 'show', 'default')
    addresses = call('ip', '-j', '-4', 'address', 'show')
    by_dev = {r.get('ifname'): r for r in addresses}
    found = []
    for route in routes:
        for local in by_dev.get(route.get('dev'), {}).get('addr_info', []):
            if local.get('family') == 'inet':
                found.append({'ip': local.get('local'), 'prefix': local.get('prefixlen'),
                              'gateway': route.get('gateway'), 'metric': int(route.get('metric', 0)),
                              'interface': route.get('dev')})
    return found


def select_network(routes: list[dict]) -> tuple[ipaddress.IPv4Network, dict]:
    valid = []
    for item in routes:
        try:
            network = private_route_network(item['ip'], int(item['prefix']))
            gateway = ipaddress.ip_address(item.get('gateway') or '0.0.0.0')
            if not (isinstance(gateway, ipaddress.IPv4Address) and is_rfc1918(gateway)):
                continue
            valid.append((int(item.get('metric', 9999)), network, item))
        except (ValueError, TypeError, KeyError):
            continue
    if not valid:
        raise RuntimeError('No private IPv4 default-route LAN found; run while connected to home Wi-Fi/LAN')
    valid.sort(key=lambda item: (item[0], str(item[1])))
    return valid[0][1], valid[0][2]


def auto_network() -> tuple[ipaddress.IPv4Network, dict]:
    routes = windows_routes() if os.name == 'nt' else linux_routes()
    return select_network(routes)


def candidate_hostnames(hosts: list[dict]) -> list[dict]:
    # Do not label generic 'carrier' or 'thermostat' strings as a verified model.
    result = []
    for host in hosts:
        mac = (host.get('mac') or '').lower()
        if mac:
            result.append({'ip': host['ip'], 'mac': mac, 'evidence': 'local_neighbor_cache',
                           'thermostat_confirmed': False})
    return result


def report(network: ipaddress.IPv4Network, interface: dict, do_tcp=True,
           mdns_seconds=3, timeout=0.25) -> dict:
    if network.prefixlen < 24 or not all(is_rfc1918(a) for a in (network.network_address, network.broadcast_address)):
        raise ValueError('Scanning must be bounded to a private /24 or smaller')
    known = neighbors()
    records, warnings = discover_mdns(mdns_seconds) if mdns_seconds else ([], [])
    # Some devices ignore ping; TCP connection attempts still discover listeners.
    target_addresses = [str(addr) for addr in network.hosts() if str(addr) != interface['ip']]
    listeners = scan_hosts(target_addresses, timeout) if do_tcp else []
    return {
        'timestamp_utc': datetime.now(timezone.utc).isoformat(),
        'scope': str(network), 'local_ip': interface['ip'],
        'scan_type': 'neighbor cache, mDNS, bounded TCP connects',
        'candidate_devices': candidate_hostnames(known),
        'mdns_records': records, 'tcp_open': listeners, 'warnings': warnings,
        'limitations': [
            'No IP is declared to be the Carrier thermostat without identity correlation.',
            'An absent TCP listener does not imply absence of Matter (IPv6/UDP).',
            'A thermostat may reside on a different VLAN or isolated Wi-Fi network.',
        ],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--no-tcp', action='store_true', help='Skip /24 TCP connection checks')
    parser.add_argument('--mdns-seconds', type=float, default=3)
    parser.add_argument('--timeout', type=float, default=0.25)
    parser.add_argument('--output', type=Path, help='Optional private JSON output file')
    args = parser.parse_args(argv)
    if not 0.05 <= args.timeout <= 3 or not 0 <= args.mdns_seconds <= 15:
        parser.error('Invalid timeout duration')
    try:
        network, interface = auto_network()
    except (RuntimeError, OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError) as exc:
        print(f'FAIL: Automatic subnet detection: {type(exc).__name__}: {exc}', file=sys.stderr)
        return 2
    result = report(network, interface, not args.no_tcp, args.mdns_seconds, args.timeout)
    text = json.dumps(result, indent=2) + '\n'
    print(text, end='')
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if args.output.is_symlink():
            parser.error('Refusing symlink output')
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(text)
        if os.name == 'posix':
            os.chmod(args.output, 0o600)
    return 0


if __name__ == '__main__':
    sys.exit(main())
