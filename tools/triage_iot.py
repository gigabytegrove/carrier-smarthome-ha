#!/usr/bin/env python3
"""Read-only analysis of the saved Carrier SmartHome IoT discovery report.

No network calls. No attempts to identify a model from a common open TCP port.
The report contains private addressing information and must stay on the user's PC.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import ipaddress
import json
import sys
from pathlib import Path

TARGET = ipaddress.ip_network('172.20.0.0/16')


def valid_host(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        address = ipaddress.ip_address(value.strip())
    except ValueError:
        return None
    if address.version != 4 or address not in TARGET:
        return None
    return str(address)


def normalized_hosts(values: object) -> set[str]:
    if not isinstance(values, list):
        return set()
    return {ip for value in values if (ip := valid_host(value)) is not None}


def analyze(report: dict) -> dict:
    if not isinstance(report, dict):
        raise ValueError('Scan report must be a JSON object.')
    try:
        scan_network = ipaddress.ip_network(report['target'], strict=False)
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError('Scan report is missing a valid target CIDR.') from exc
    if scan_network.version != 4 or not scan_network.subnet_of(TARGET):
        raise ValueError('Report target is outside the confirmed 172.20.0.0/16 IoT network.')

    pings = normalized_hosts(report.get('icmp_responsive'))
    candidates = normalized_hosts(report.get('candidate_addresses'))
    neighbors: dict[str, dict] = {}
    for row in report.get('neighbor_records') or []:
        if not isinstance(row, dict):
            continue
        ip = valid_host(row.get('IPAddress'))
        if ip and ipaddress.ip_address(ip) in scan_network:
            neighbors[ip] = {
                'mac': str(row.get('LinkLayerAddress') or ''),
                'interface': str(row.get('InterfaceAlias') or ''),
                'state': str(row.get('State') or ''),
            }
    ports: dict[str, set[int]] = defaultdict(set)
    for row in report.get('tcp_open') or []:
        if not isinstance(row, dict):
            continue
        ip = valid_host(row.get('ip'))
        try:
            port = int(row.get('port'))
        except (ValueError, TypeError):
            continue
        if ip and ipaddress.ip_address(ip) in scan_network and 1 <= port <= 65535:
            ports[ip].add(port)

    # Defensive union means callers still see TCP-only candidates from deep scans.
    all_hosts = set(candidates) | set(pings) | set(neighbors) | set(ports)
    all_hosts = {ip for ip in all_hosts if ipaddress.ip_address(ip) in scan_network}
    devices = []
    for ip in sorted(all_hosts, key=lambda x: int(ipaddress.ip_address(x))):
        portlist = sorted(ports.get(ip, set()))
        neighbor = neighbors.get(ip, {})
        devices.append({
            'ip': ip,
            'icmp': ip in pings,
            'neighbor': bool(neighbor),
            'mac': neighbor.get('mac', ''),
            'neighbor_state': neighbor.get('state', ''),
            'interface': neighbor.get('interface', ''),
            'ports': portlist,
        })
    # Open-port devices first for service inspection, but not device-identification ranking.
    devices.sort(key=lambda row: (-len(row['ports']), -int(row['icmp']), int(ipaddress.ip_address(row['ip']))))
    by_subnet = Counter(str(ipaddress.ip_network(ip + '/24', strict=False)) for ip in all_hosts)
    return {
        'target': str(scan_network),
        'addresses_pinged': report.get('addresses_pinged'),
        'candidate_count': len(all_hosts),
        'icmp_count': len(pings & all_hosts),
        'neighbor_count': len(set(neighbors) & all_hosts),
        'tcp_port_results': sum(len(row['ports']) for row in devices),
        'tcp_devices': sum(bool(row['ports']) for row in devices),
        'by_subnet': dict(sorted(by_subnet.items(), key=lambda row: int(ipaddress.ip_network(row[0]).network_address))),
        'route': report.get('route'),
        'devices': devices,
    }


def format_report(summary: dict) -> str:
    lines = [
        'CARRIER SMARTHOME | SAVED IoT SCAN REVIEW (NO NETWORK ACTIVITY)',
        f"Target: {summary['target']} | addresses tested: {summary['addresses_pinged']}",
        (f"Distinct candidates: {summary['candidate_count']} | ICMP replies: {summary['icmp_count']} | "
         f"neighbor records: {summary['neighbor_count']}"),
        (f"Open TCP port results: {summary['tcp_port_results']} on "
         f"{summary['tcp_devices']} distinct host(s)"),
        'By /24: ' + (', '.join(f'{k}={v}' for k, v in summary['by_subnet'].items()) or 'none'),
    ]
    route = summary.get('route')
    if isinstance(route, dict) and route.get('destination_prefix') and route.get('interface_alias'):
        lines.append(f"Recorded route: {route['destination_prefix']} via "
                     f"{route.get('next_hop') or 'unknown'} on {route['interface_alias']}")
    else:
        lines.append('Recorded route: incomplete/unverified (old scanner route-reporting defect).')
    lines.extend([
        '',
        'IP ADDRESS       ICMP  MAC / NEIGHBOR       OPEN TCP PORTS',
        '---------------- ----- -------------------- ------------------------',
    ])
    for row in summary['devices']:
        mac = row['mac'] if row['mac'] else '(not visible)'
        ports = ','.join(map(str, row['ports'])) if row['ports'] else '-'
        lines.append(f"{row['ip']:<16} {'yes' if row['icmp'] else 'no':<5} {mac[:20]:<20} {ports}")
    lines.extend([
        '',
        'INTERPRETATION:',
        '- These are network candidates, NOT confirmed Carrier thermostats.',
        '- A host can have multiple open ports; port totals are not distinct device totals.',
        '- No open TCP ports does not rule out an outbound-cloud or Matter-only thermostat.',
        '- Across VLANs, MAC addresses often are not visible. DHCP controller data is stronger evidence.',
        '- The original report is private. Do not commit raw IP/MAC scans to GitHub.',
    ])
    return '\n'.join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path, help='Existing iot-private.json generated on your PC')
    parser.add_argument('--output', type=Path, help='Optional local text summary file')
    args = parser.parse_args(argv)
    try:
        report = json.loads(args.report.read_text(encoding='utf-8-sig'))
        summary = analyze(report)
        rendered = format_report(summary)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered + '\n', encoding='utf-8')
        print(rendered)
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f'ERROR: Could not review report: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
