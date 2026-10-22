#!/usr/bin/env python3
"""Read-only TCP discovery for a *currently connected* verified Omada thermostat.

Never scans a historical IP. Identity is established from the active Omada
client table and a known label MAC suffix before contacting a host. This tests
whether selected TCP listeners accept connections; no HTTP, Matter or commands.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import re
import ssl
import zipfile
import asyncio
import ipaddress
from pathlib import Path
import sys

from omada_identity import identify, read_archive

ALLOWED_VLAN = ipaddress.ip_network('172.20.0.0/16')
PORTS = (80, 443, 8080, 8443, 1883, 8883)
EXPORT_TIME = re.compile(r'^OnlineClient_(\d{4}-\d{2}-\d{2}-\d{2}-\d{2})\.csv$', re.I)


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


def assert_export_fresh(path: Path, max_age_minutes: int = 20) -> None:
    """Require a current Omada ONLINE snapshot, not merely recent ZIP mtime."""
    if not 1 <= max_age_minutes <= 120:
        raise ValueError('Freshness interval must be 1-120 minutes.')
    try:
        with zipfile.ZipFile(path) as z:
            matches = [EXPORT_TIME.fullmatch(Path(n).name)
                       for n in z.namelist()]
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError('Invalid Omada client export.') from exc
    times = [datetime.strptime(m.group(1), '%Y-%m-%d-%H-%M')
             for m in matches if m is not None]
    if len(times) != 1:
        raise ValueError('Current Omada OnlineClient timestamp cannot be established.')
    # Omada CSV timestamp uses the controller-local civil clock. Only accept
    # plausible timestamps aligned with this workstation's local clock.
    age = (datetime.now() - times[0]).total_seconds() / 60
    if age < -5 or age > max_age_minutes:
        raise ValueError('Omada snapshot is too old or clock-skewed. Export current clients again.')


async def read_http_fingerprint(ip: str, port: int) -> str:
    """Optional single HTTP HEAD to one verified host; no credentials/body read."""
    context = None
    if port in (443, 8443):
        context = ssl.create_default_context()
        context.check_hostname = False  # Fingerprint is not an authenticated TLS connection.
        context.verify_mode = ssl.CERT_NONE
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port, ssl=context), timeout=2.0)
        try:
            writer.write(b'HEAD / HTTP/1.1\r\nHost: device.local\r\nConnection: close\r\n\r\n')
            await asyncio.wait_for(writer.drain(), 2.0)
            line = await asyncio.wait_for(reader.readline(), 2.0)
            line = line[:96].decode('ascii', errors='replace').strip()
            match = re.fullmatch(r'HTTP/\d(?:\.\d)? ([1-5][0-9]{2})(?: .*?)?', line)
            return 'HTTP ' + match.group(1) if match else 'no recognized HTTP status'
        finally:
            writer.close()
            await writer.wait_closed()
    except (ConnectionError, OSError, ssl.SSLError, asyncio.TimeoutError):
        return 'no HTTP response/TLS handshake failed'


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
    parser.add_argument('--max-age-minutes', type=int, default=20, help='Current Omada online export freshness limit')
    parser.add_argument('--http-fingerprint', action='store_true', help='Optional single HTTP HEAD on open web ports')
    args = parser.parse_args()
    try:
        assert_export_fresh(args.omada_export, args.max_age_minutes)
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
    if args.http_fingerprint:
        print('Optional HTTP HEAD fingerprints (no credentials, bodies or thermostat commands):')
        for port in (80, 443, 8080, 8443):
            if results.get(port):
                print(f'  {port}: {asyncio.run(read_http_fingerprint(target, port))}')
    else:
        print('No HTTP requests sent. Optional --http-fingerprint sends only HEAD / on verified open ports.')
    print('No MQTT publish/subscribe, Matter, HVAC command, or cloud requests were sent.')
    print('No open TCP ports does not rule out a proprietary local protocol.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
