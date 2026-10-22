#!/usr/bin/env python3
"""Identify Carrier SmartHome thermostat from an Omada Client_*.zip export.

Runs entirely offline. No Matter, cloud, network scanning, or control commands.
Never upload export archives, MAC addresses, serials, or IP inventories to GitHub.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime
import io
import ipaddress
from pathlib import Path
import re
import sys
import zipfile

MAX_CSV_BYTES = 32 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAC_RE = re.compile(r'^[0-9a-fA-F]{12}$')
NAME_RE = re.compile(r'\b(?:smart[ -]?thermostat|carrier[ -]?thermostat|tstatccewf)\b', re.I)
ZIP_MEMBERS = {
    'online': 'OnlineClient_',
    'offline': 'OfflineClient_',
    'history': 'PastConnection_',
}


def mac(value: object) -> str:
    raw = re.sub(r'[^a-fA-F0-9]', '', str(value or ''))
    return raw.upper() if MAC_RE.fullmatch(raw) and raw != '000000000000' else ''


def ipv4(value: object) -> str:
    try:
        a = ipaddress.ip_address(str(value or '').strip())
    except ValueError:
        return ''
    return str(a) if a.version == 4 else ''


def read_archive(path: Path) -> dict[str, list[dict[str, str]]]:
    if not path.is_file():
        raise ValueError('Omada archive not found.')
    result: dict[str, list[dict[str, str]]] = {}
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        if sum(i.file_size for i in infos) > MAX_TOTAL_BYTES:
            raise ValueError('Omada archive exceeds the 64 MiB decompressed safety limit.')
        for kind, prefix in ZIP_MEMBERS.items():
            candidates = [i for i in infos if Path(i.filename).name.startswith(prefix) and i.filename.lower().endswith('.csv')]
            if len(candidates) != 1:
                raise ValueError(f'Expected exactly one {prefix}*.csv in the Omada archive.')
            info = candidates[0]
            if info.file_size > MAX_CSV_BYTES or info.flag_bits & 0x1:
                raise ValueError(f'{kind} export too large or encrypted.')
            with archive.open(info) as binary, io.TextIOWrapper(binary, encoding='utf-8-sig', errors='replace', newline='') as text:
                reader = csv.DictReader(text)
                header = set(reader.fieldnames or [])
                needed = {'MAC ADDRESS', 'IP ADDRESS'}
                if not needed.issubset(header):
                    raise ValueError(f'{kind} export missing required Omada columns.')
                if kind == 'history' and 'USERNAME' not in header:
                    raise ValueError('History export missing USERNAME.')
                if kind != 'history' and 'NAME' not in header:
                    raise ValueError(f'{kind} export missing NAME.')
                # The history file is large but still bounded by MAX_CSV_BYTES.
                result[kind] = [{k: str(v or '').strip() for k, v in row.items() if isinstance(k, str)} for row in reader]
    return result


def historical_time(value: str) -> datetime | None:
    for fmt in ('%Y-%m-%d %I:%M:%S %p', '%Y-%m-%d %H:%M:%S'):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    return None


def identify(rows: dict[str, list[dict[str, str]]], exact_mac: str = '', suffix: str = '') -> dict:
    requested_mac = mac(exact_mac)
    suffix = suffix.upper().strip()
    if suffix and not re.fullmatch(r'[0-9A-F]{4}', suffix):
        raise ValueError('MAC suffix must be exactly four hexadecimal characters.')
    if exact_mac and not requested_mac:
        raise ValueError('Invalid MAC address. Expected 12 hexadecimal digits.')
    snapshots = rows['online'] + rows['offline']
    matched = []
    for row in snapshots:
        m = mac(row.get('MAC ADDRESS'))
        name = row.get('NAME') or row.get('SYSTEM NAME') or ''
        sysname = row.get('SYSTEM NAME') or ''
        if not m:
            continue
        if requested_mac:
            matches = m == requested_mac
        else:
            # Avoid generic lwip0/wlan0 clients and vendor-OUI guessing.
            matches = bool(NAME_RE.search(name + ' ' + sysname))
            name_suffix = re.search(r'-([A-Fa-f0-9]{4})$', name)
            if name_suffix and not m.endswith(name_suffix.group(1).upper()):
                matches = False
        if matches and (not suffix or m.endswith(suffix)):
            matched.append(row)
    distinct_macs = {mac(row.get('MAC ADDRESS')) for row in matched}
    if not distinct_macs:
        raise ValueError('No named thermostat match in the current/archived Omada client snapshots. No device identity will be guessed.')
    if len(distinct_macs) != 1:
        raise ValueError('Multiple thermostat MAC candidates. Use --mac locally to select the one printed on the label.')
    device_mac = next(iter(distinct_macs))
    online = [row for row in rows['online'] if mac(row.get('MAC ADDRESS')) == device_mac and row.get('STATUS', '').upper() == 'CONNECTED']
    offline = [row for row in rows['offline'] if mac(row.get('MAC ADDRESS')) == device_mac]
    events = [r for r in rows['history'] if mac(r.get('MAC ADDRESS')) == device_mac]
    events.sort(key=lambda r: historical_time(r.get('LAST ONLINE TIME', '')) or datetime.min, reverse=True)
    snapshot = (online or offline or matched)[0]
    history = []
    for event in events:
        ip = ipv4(event.get('IP ADDRESS'))
        if ip and ip not in history:
            history.append(ip)
    current_ip = ipv4(online[0].get('IP ADDRESS')) if online else ''
    last_ip = current_ip or ipv4(snapshot.get('IP ADDRESS')) or (history[0] if history else '')
    # Offline client record is not a DHCP lease confirming current ownership.
    ip_conflicts = sorted({mac(row.get('MAC ADDRESS')) for row in snapshots if ipv4(row.get('IP ADDRESS')) == last_ip and mac(row.get('MAC ADDRESS')) not in ('', device_mac)})
    return {
        'name': snapshot.get('NAME') or snapshot.get('SYSTEM NAME') or '(unnamed)',
        'mac': ':'.join(device_mac[i:i + 2] for i in range(0, 12, 2)),
        'status': 'CONNECTED' if online else 'NOT CONNECTED IN EXPORT',
        'current_ip': current_ip,
        'last_ip': last_ip,
        'vlan': snapshot.get('VLAN', ''),
        'ssid': snapshot.get('SSID', ''),
        'access_point': snapshot.get('AP/PORT', ''),
        'last_seen': events[0].get('LAST ONLINE TIME', '') if events else '',
        'history_ips': history,
        'history_sessions': len(events),
        'same_ip_other_macs': len(ip_conflicts),
        'source': 'Omada exported current/offline client lists and past connections',
    }


def render(result: dict, scan: dict | None = None) -> str:
    lines = [
        'CARRIER SMARTHOME | OMADA IDENTITY CORRELATION (OFFLINE)',
        f"Device: {result['name']}",
        f"Wi-Fi MAC: {result['mac']}",
        f"Omada status at export: {result['status']}",
        f"Current IP confirmed by ONLINE export: {result['current_ip'] or 'NO'}",
        f"Last recorded IP (NOT necessarily current): {result['last_ip'] or 'unknown'}",
        f"VLAN: {result['vlan'] or 'unknown'} | SSID: {result['ssid'] or 'unknown'}",
        f"Access point: {result['access_point'] or 'unknown'}",
        f"Last online recorded: {result['last_seen'] or 'unavailable'}",
        f"Distinct historical IP addresses: {len(result['history_ips'])}",
        f"History: {', '.join(result['history_ips']) or 'unavailable'}",
        f"Prior sessions for same hardware MAC: {result['history_sessions']}",
    ]
    if result['same_ip_other_macs']:
        lines.append('WARNING: Historical client exports contain OTHER MAC(s) associated with the same IP. IP reuse is proven.')
    if scan and result['last_ip']:
        pings = scan.get('icmp_responsive', []) or []
        ports = [int(p['port']) for p in (scan.get('tcp_open', []) or []) if isinstance(p, dict) and p.get('ip') == result['last_ip'] and str(p.get('port','')).isdigit()]
        lines += [
            'PREVIOUS SAVED SCAN (historical, NOT current):',
            f"  {result['last_ip']} answered ICMP: {'yes' if result['last_ip'] in pings else 'no'}",
            f"  Open TCP ports in tested set: {','.join(map(str, sorted(set(ports)))) or 'none'}",
        ]
    lines += [
        'No network requests were made. No Matter APIs were used.',
        'A disconnected device cannot be considered reachable until its current lease is confirmed.',
        'Keep the export, full MAC and output private; do not commit them to GitHub.',
    ]
    return '\n'.join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path, help='Omada Client_*.zip export')
    parser.add_argument('--mac', default='', help='Optional exact thermostat MAC when multiple match (not saved)')
    parser.add_argument('--suffix', default='', help='Optional final four MAC hex digits from thermostat label when multiple named thermostats exist')
    parser.add_argument('--scan', type=Path, help='Optional existing iot-private.json for comparison; never rescans')
    args = parser.parse_args(argv)
    try:
        rows = read_archive(args.archive)
        result = identify(rows, args.mac, args.suffix)
        scan = None
        if args.scan:
            import json
            scan = json.loads(args.scan.read_text(encoding='utf-8-sig'))
            if not isinstance(scan, dict):
                raise ValueError('Saved scan must be a JSON object.')
        print(render(result, scan))
        return 0
    except (ValueError, OSError, zipfile.BadZipFile, csv.Error) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
