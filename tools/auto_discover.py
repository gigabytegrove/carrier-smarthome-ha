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
    """All connected private IPv4 interfaces; do not depend on default gateway."""
    script = r'''
$ErrorActionPreference='Stop'
$up=@(Get-NetIPInterface -AddressFamily IPv4 | Where-Object {$_.ConnectionState -eq 'Connected'} |
 Select-Object -ExpandProperty InterfaceIndex -Unique)
$rows=@(Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$up -contains $_.InterfaceIndex} |
 ForEach-Object {@{ip=$_.IPAddress;prefix=[int]$_.PrefixLength;
 interface=$_.InterfaceAlias;metric=0}})
ConvertTo-Json -InputObject @($rows) -Depth 4 -Compress
'''
    value = _powershell_json(script)
    return value if isinstance(value, list) else [value]


def windows_routed_cidrs() -> list[str]:
    script = r'''
$rows=@(Get-NetRoute -AddressFamily IPv4 -ErrorAction SilentlyContinue |
 Where-Object {$_.NextHop -and $_.NextHop -ne '0.0.0.0' -and
 $_.DestinationPrefix -match '/\d+$'} |
 Select-Object -ExpandProperty DestinationPrefix)
ConvertTo-Json -InputObject @($rows) -Compress
'''
    value = _powershell_json(script)
    return value if isinstance(value, list) else [value]


def linux_routes() -> list[dict]:
    result = subprocess.run(['ip', '-j', '-4', 'address', 'show', 'up'],
                            capture_output=True, text=True, timeout=10, check=True)
    addresses = json.loads(result.stdout)
    found = []
    for adapter in addresses:
        for address in adapter.get('addr_info', []):
            if address.get('family') == 'inet':
                found.append({'ip': address.get('local'), 'prefix': address.get('prefixlen'),
                              'interface': adapter.get('ifname'), 'metric': 0})
    return found


def linux_routed_cidrs() -> list[str]:
    result = subprocess.run(['ip', '-j', '-4', 'route', 'show'],
                            capture_output=True, text=True, timeout=10, check=True)
    routes = json.loads(result.stdout)
    return [item.get('dst') for item in routes if item.get('gateway') and item.get('dst')
            and item['dst'] != 'default']


def safe_cidr(value: str, explicit: bool = False) -> ipaddress.IPv4Network:
    try:
        network = ipaddress.ip_network(value, strict=False)
    except ValueError as exc:
        raise ValueError(f'Invalid CIDR {value}: {exc}') from exc
    if not isinstance(network, ipaddress.IPv4Network) or network.prefixlen < 24 or network.prefixlen > 32:
        raise ValueError('Ranges must be private IPv4 /24 or smaller')
    if not all(is_rfc1918(a) for a in (network.network_address, network.broadcast_address)):
        raise ValueError('Non-RFC1918 network is not allowed')
    return network


def discovery_scopes(interfaces: list[dict], routed: list[str], extra: list[str] | None = None,
                     max_networks: int = 8) -> tuple[list[dict], list[str]]:
    """Choose only attached, explicitly routed, or caller-authorized private subnets.

    Do not guess VLAN subnets from a router's default route.
    """
    if not 1 <= max_networks <= 16:
        raise ValueError('max_networks must be 1-16')
    found: dict[str, dict] = {}
    warnings: list[str] = []

    def add(network: ipaddress.IPv4Network, source: str, local_ip: str | None = None):
        key = str(network)
        row = found.setdefault(key, {'network': network, 'sources': [], 'local_ips': []})
        if source not in row['sources']:
            row['sources'].append(source)
        if local_ip and local_ip not in row['local_ips']:
            row['local_ips'].append(local_ip)

    for entry in interfaces:
        try:
            ip = entry['ip']
            network = private_route_network(ip, int(entry['prefix']))
        except (ValueError, TypeError, KeyError):
            continue
        add(network, 'connected:' + str(entry.get('interface') or 'interface'), ip)
        if int(entry['prefix']) < 24:
            warnings.append(f'{ip}/{entry["prefix"]} wider than /24; only {network} scanned. '
                            'Other slices require an explicit subnet or in-VLAN probe.')
    for value in routed:
        try:
            cidr = safe_cidr(value)
            if cidr.prefixlen > 30:
                continue
        except (ValueError, TypeError):
            continue
        add(cidr, 'specific_route')
    for value in extra or []:
        add(safe_cidr(value, explicit=True), 'user_authorized')
    scopes = list(found.values())
    if len(scopes) > max_networks:
        warnings.append(f'{len(scopes)} private subnets found; limited to {max_networks} by safety cap.')
    return scopes[:max_networks], warnings


def auto_networks(extra: list[str] | None = None, max_networks: int = 8) -> tuple[list[dict], list[str]]:
    if os.name == 'nt':
        interfaces, routes = windows_routes(), windows_routed_cidrs()
    else:
        interfaces, routes = linux_routes(), linux_routed_cidrs()
    scopes, warnings = discovery_scopes(interfaces, routes, extra, max_networks)
    if not scopes:
        raise RuntimeError('No visible connected private networks or authorized private subnets')
    return scopes, warnings


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
    known = [n for n in neighbors() if ipaddress.ip_address(n['ip']) in network]
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
    parser.add_argument('--no-tcp', action='store_true', help='Skip local TCP connection checks')
    parser.add_argument('--cidr', action='append', default=[],
                        help='Additional authorized private /24-or-smaller VLAN; repeat if needed')
    parser.add_argument('--max-networks', type=int, default=8, help='Safety cap (1-16, default 8)')
    parser.add_argument('--list-only', action='store_true', help='Report networks without probing hosts')
    parser.add_argument('--mdns-seconds', type=float, default=3)
    parser.add_argument('--timeout', type=float, default=0.25)
    parser.add_argument('--output', type=Path, help='Optional private JSON output file')
    args = parser.parse_args(argv)
    if not 0.05 <= args.timeout <= 3 or not 0 <= args.mdns_seconds <= 15:
        parser.error('Invalid timeout duration')
    try:
        scopes, warnings = auto_networks(args.cidr, args.max_networks)
    except (RuntimeError, OSError, subprocess.SubprocessError, ValueError,
            json.JSONDecodeError) as exc:
        print(f'FAIL: Network detection: {type(exc).__name__}: {exc}', file=sys.stderr)
        return 2
    if len(scopes) == 1:
        warnings.append('Only one network visible. The router default route cannot tell us '                        'the IoT VLAN subnet; run there or provide an authorized --cidr.')
    result: dict[str, Any] = {
        'timestamp_utc': datetime.now(timezone.utc).isoformat(),
        'model_target': 'TSTATCCEWF-01',
        'network_count': len(scopes),
        'networks': [],
        'mdns_records': [],
        'warnings': warnings,
        'thermostat_ip_confirmed': False,
        'local_api_verified': False,
    }
    if not args.list_only and args.mdns_seconds:
        records, errors = discover_mdns(args.mdns_seconds)
        result['mdns_records'] = records
        result['warnings'].extend(errors)
        result['warnings'].append('mDNS is scoped to the local multicast domain; '                                  'its records are not evidence about every VLAN.')
    for item in scopes:
        if args.list_only:
            part = {'scope': str(item['network']), 'sources': item['sources'],
                    'local_ips': item['local_ips'], 'discovered': False}
        else:
            part = report(item['network'], {'ip': item['local_ips'][0] if item['local_ips'] else ''},
                          not args.no_tcp, 0, args.timeout)
            part['sources'] = item['sources']
            part['local_ips'] = item['local_ips']
        result['networks'].append(part)
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
