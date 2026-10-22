#!/usr/bin/env python3
"""Read-only TCP discovery for a *currently connected* verified Omada thermostat.

Never scans a historical IP. Identity is established from the active Omada
client table and a known label MAC suffix before contacting a host. This tests
whether selected TCP listeners accept connections; no HTTP, Matter or commands.
"""
from __future__ import annotations

import argparse
import asyncio
import ipaddress
from pathlib import Path
import sys

from omada_identity import identify, read_archive

ALLOWED_VLAN = ipaddress.ip_network('172.20.0.0/16')
PORTS = (80, 443, 8080, 8443, 1883, 8883)


def connected_target(record: dict) -> str:
    """Return approved current IP or refuse stale/reassigned Omada exports."""
    if record.get('status') != 'CONNECTED':
        raise ValueError('Thermostat is not connected in the supplied Omada export. No probing allowed.')
    host = record.get('current_ip')
    try:
        ip = ipaddress.ip_address(host)
    except (ValueError, TypeError):
        raise ValueError('Omada export did not contain a valid current IP.') from None
    if ip.version != 4 or ip not in ALLOWED_VLAN or ip in (ALLOWED_VLAN.network_address, ALLOWED_VLAN.broadcast_address):
        raise ValueError('Current IP is outside the authorized Carrier IoT network.')
    if record.get('same_ip_other_macs'):
        raise ValueError('IP identity is ambiguous in this Omada export.')
    return str(ip)


async def check_tcp(ip: str, port: int, timeout: float = 1.5) -> bool:
    """TCP connect only. Does not send a protocol payload."""
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(ip, port), timeout=timeout)
        writer.close()
        await writer.wait_closed()
        return True
    except (ConnectionError, OSError, asyncio.TimeoutError):
        return False


async def probe(ip: str) -> dict[int, bool]:
    outcomes = await asyncio.gather(*(check_tcp(ip, p) for p in PORTS))
    return dict(zip(PORTS, outcomes))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('omada_export', type=Path)
    parser.add_argument('--suffix', default='', help='Optional last four hex digits of thermostat MAC; use only to resolve multiple matches')
    parser.add_argument('--plan', action='store_true', help='Verify identity, but do not send any packets')
    args = parser.parse_args()
    try:
        target = connected_target(identify(read_archive(args.omada_export), suffix=args.suffix))
    except (ValueError, OSError) as exc:
        print(f'SAFE STOP: {exc}', file=sys.stderr)
        return 2
    print('Carrier thermostat identified in current Omada online client list.')
    print('Target: (redacted) — connectable ports will be reported, no IP exported.')
    if args.plan:
        print('PLAN ONLY: no network requests sent.')
        return 0
    results = asyncio.run(probe(target))
    print('TCP connect results:')
    for port in PORTS:
        print(f'  {port}: {"OPEN" if results[port] else "closed/filtered"}')
    print('No HTTP, MQTT, Matter, thermostat command, or cloud requests were sent.')
    print('No open TCP ports does not rule out a proprietary local protocol.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
