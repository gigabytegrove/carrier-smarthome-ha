#!/usr/bin/env python3
"""Carrier SmartHome v0.5.0: authorized, target-only proprietary LAN reconnaissance.

Accepts either a recently exported Omada snapshot with verified device identity,
or an explicitly acknowledged single known IP (identity NOT independently verified).
Never scans a subnet. No Matter,
HVAC commands, credential exchange, firmware change, DNS interception, or
MQTT publish/subscribe. Results intentionally omit private IP/MAC/SSID/name.
"""
from __future__ import annotations

import argparse
import asyncio
import ipaddress
import json
from datetime import datetime, timezone
from pathlib import Path
import re
import secrets
import socket
import ssl
import struct
import sys
import time
import zipfile
from typing import Any

from omada_identity import identify, read_archive, mac

AUTHORIZED = ipaddress.ip_network('172.20.0.0/16')
ONLINE_NAME = re.compile(r'^OnlineClient_(\d{4}-\d{2}-\d{2}-\d{2}-\d{2})\.csv$', re.I)
# Scopes: first 1024 reserved ports + embedded/web/MQTT/CoAP/IoT probes.
EXTRA_TCP = (
    1080, 1443, 1883, 1884, 1885, 2000, 2001, 2375, 2376, 3000, 3001,
    3333, 4000, 4001, 4040, 4443, 4567, 5000, 5001, 5002, 5050, 5353,
    5555, 5683, 5684, 6000, 6001, 6666, 6667, 6668, 7000, 7001, 7443,
    7777, 8000, 8001, 8008, 8009, 8010, 8080, 8081, 8082, 8088, 8090,
    8100, 8181, 8222, 8333, 8443, 8484, 8530, 8554, 8883, 8884, 8888,
    9000, 9001, 9002, 9090, 9443, 9999, 10000, 10001, 10443, 12345,
    18080, 19000, 20000, 22318, 32768, 49152, 49153, 49154, 49155,
    49156, 49157, 49158, 49159, 49160, 50000, 54321, 55555, 60000,
)
WEB_PORTS = {80, 81, 443, 8000, 8008, 8080, 8081, 8088, 8443, 8888, 9000, 9090, 9443, 18080}
TLS_PORTS = {443, 8443, 8883, 8884, 9443, 10443}
MQTT_PORTS = {1883, 1884, 8883, 8884}
MAX_PORTS = 65535


def export_age(path: Path, now: datetime | None = None, *, clock_offset_hours: int | None = None) -> dict[str, Any]:
    """Check both archive filesystem mtime AND embedded Omada OnlineClient name.

    The Omada controller may use local time while Windows uses a different
    timezone. The caller can supply explicit offset from UTC (e.g. -4); no
    automatic override if neither local nor UTC interpretation is recent.
    """
    if not path.is_file() or not zipfile.is_zipfile(path):
        raise ValueError('Select a valid Omada Client_*.zip file.')
    now = now or datetime.now(timezone.utc)
    try:
        with zipfile.ZipFile(path) as z:
            names = [Path(x.filename).name for x in z.infolist()]
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError('Unable to inspect Omada ZIP.') from exc
    stamps = [m.group(1) for name in names if (m := ONLINE_NAME.fullmatch(name))]
    if len(stamps) != 1:
        raise ValueError('Omada ZIP must contain exactly one timestamped OnlineClient CSV.')
    stamp = datetime.strptime(stamps[0], '%Y-%m-%d-%H-%M')
    local = datetime.now().astimezone().tzinfo
    if clock_offset_hours is None:
        candidates = [('workstation-local', stamp.replace(tzinfo=local)),
                      ('UTC', stamp.replace(tzinfo=timezone.utc))]
    else:
        from datetime import timedelta
        candidates = [('explicit-controller-offset', stamp.replace(
            tzinfo=timezone(timedelta(hours=clock_offset_hours))))]
    ages = [(label, (now - moment).total_seconds() / 60) for label, moment in candidates]
    label, age = min(ages, key=lambda item: abs(item[1]))
    file_age = (now.timestamp() - path.stat().st_mtime) / 60
    return {'controller_clock': label, 'stamp_age_minutes': round(age, 2),
            'file_age_minutes': round(file_age, 2)}


def verify_fresh_export(path: Path, minutes: int, now: datetime | None = None,
                        clock_offset_hours: int | None = None) -> dict[str, Any]:
    if not 5 <= minutes <= 120:
        raise ValueError('Allowed export age is 5 to 120 minutes.')
    evidence = export_age(path, now=now, clock_offset_hours=clock_offset_hours)
    if not -5 <= evidence['stamp_age_minutes'] <= minutes:
        raise ValueError('Omada embedded online-client timestamp is stale or has an unverified clock offset. Export again.')
    if not -5 <= evidence['file_age_minutes'] <= minutes:
        raise ValueError('Omada ZIP filesystem timestamp is stale. Export again.')
    return evidence


def verify_identity(rows: dict[str, list[dict[str, str]]], suffix: str) -> tuple[str, dict[str, Any]]:
    """One connected MAC, unique current IP, authorized VLAN, no active IP clash."""
    if not re.fullmatch(r'[a-fA-F0-9]{4}', suffix):
        raise ValueError('Enter exactly the final 4 hexadecimal digits of thermostat MAC.')
    record = identify(rows, suffix=suffix)
    if record['status'] != 'CONNECTED' or not record.get('current_ip'):
        raise ValueError('The identified thermostat is not CONNECTED in this Omada snapshot.')
    ip = ipaddress.ip_address(record['current_ip'])
    if ip.version != 4 or ip not in AUTHORIZED or ip == AUTHORIZED.network_address or ip == AUTHORIZED.broadcast_address:
        raise ValueError('Verified thermostat IPv4 is outside the approved IoT VLAN.')
    # Prior OFFLINE clients may have reused the same IP historically; only
    # simultaneous ONLINE assignments would be an actual current conflict.
    concurrent = {mac(row.get('MAC ADDRESS')) for row in rows['online']
                  if row.get('IP ADDRESS', '').strip() == str(ip)
                  and row.get('STATUS', '').upper() == 'CONNECTED'}
    if len(concurrent) != 1 or mac(record['mac']) not in concurrent:
        raise ValueError('Current IP has conflicting or unverified active MAC assignment.')
    return str(ip), {'online_verified': True, 'vlan_verified': True,
                     'active_ip_unique': True, 'identity_method': 'Omada current MAC match'}


def verify_live_ui_selection(ip_text: str, mac_text: str, suffix: str,
                             confirmation: str) -> tuple[str, dict[str, Any]]:
    """Owner reads current IP+MAC from Omada UI; not a machine proof."""
    if confirmation != 'I-SEE-IT-CONNECTED':
        raise ValueError('Must confirm the selected thermostat is connected in live Omada UI.')
    actual_mac = mac(mac_text)
    if not actual_mac or not re.fullmatch(r'[A-Fa-f0-9]{4}', suffix) or not actual_mac.endswith(suffix.upper()):
        raise ValueError('Current full Wi-Fi MAC does not match expected last four characters.')
    # Address validation is identical to direct-IP, but UI owner attestation is
    # distinct from consent to scan a potentially reassigned historical lease.
    ip, _ = verify_direct_target(ip_text, 'I-ACCEPT-IP-REASSIGNMENT-RISK')
    return ip, {'online_verified': False, 'active_ip_unique': False,
                'vlan_verified': True, 'independently_verified': False,
                'identity_method': 'owner-attested current Omada UI MAC/IP association'}


def verify_direct_target(ip_text: str, confirmation: str) -> tuple[str, dict[str, Any]]:
    """Explicit owner-authorized last-known address, not proof of current MAC.

    The user has already identified a device and may inspect a specific IP
    without continuously re-exporting Omada records. Be truthful: an IP can
    change owners across DHCP leases. Neither connectivity nor ARP on a routed
    VLAN authenticates its hardware identity.
    """
    if confirmation != 'I-ACCEPT-IP-REASSIGNMENT-RISK':
        raise ValueError('Direct-IP scan requires acknowledgement that DHCP may have reassigned the host.')
    try:
        ip = ipaddress.ip_address(ip_text)
    except ValueError:
        raise ValueError('Direct target must be a numeric IPv4 address.') from None
    if (ip.version != 4 or ip not in AUTHORIZED or
            ip in (AUTHORIZED.network_address, AUTHORIZED.broadcast_address)):
        raise ValueError('Direct target must be one host inside the authorized 172.20.0.0/16 IoT network.')
    return str(ip), {
        'online_verified': False, 'active_ip_unique': False,
        'vlan_verified': True, 'independently_verified': False,
        'identity_method': 'owner-authorized last-known IP; DHCP ownership not reverified',
    }


def scan_ports(full: bool) -> list[int]:
    return list(range(1, MAX_PORTS + 1)) if full else sorted(set(range(1, 1025)).union(EXTRA_TCP))


async def check_tcp(ip: str, port: int, timeout: float) -> str:
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(ip, port), timeout=timeout)
        writer.close()
        try:
            await asyncio.wait_for(writer.wait_closed(), .65)
        except (OSError, asyncio.TimeoutError):
            pass
        return 'open'
    except ConnectionRefusedError:
        return 'closed'
    except (asyncio.TimeoutError, TimeoutError):
        return 'filtered_or_no_reply'
    except OSError:
        return 'other_error'


async def tcp_sweep(ip: str, ports: list[int], concurrency: int, timeout: float,
                    show_progress: bool = True) -> dict[str, Any]:
    sem = asyncio.Semaphore(concurrency)
    opened: list[int] = []
    counters = {'closed': 0, 'filtered_or_no_reply': 0, 'other_error': 0}
    done = 0
    start = time.monotonic()

    async def check(port: int):
        nonlocal done
        async with sem:
            status = await check_tcp(ip, port, timeout)
        if status == 'open':
            opened.append(port)
            if show_progress:
                print(f'  TCP OPEN: {port}', flush=True)
        else:
            counters[status] += 1
        done += 1
        if show_progress and (done % 4096 == 0 or done == len(ports)):
            print(f'  TCP progress: {done}/{len(ports)} ports; {len(opened)} open', flush=True)

    # Bounded task queue; don't spawn 65K active coroutines simultaneously.
    for start_at in range(0, len(ports), concurrency * 8):
        batch = ports[start_at:start_at + concurrency * 8]
        await asyncio.gather(*(check(p) for p in batch))
    return {'count': len(ports), 'open_ports': sorted(opened), 'statuses': counters,
            'elapsed_seconds': round(time.monotonic() - start, 1)}


async def tls_check(ip: str, port: int) -> dict[str, Any]:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE  # Discovery only, never submit credentials.
    ctx.set_alpn_protocols(['http/1.1', 'h2', 'mqtt'])
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(
            ip, port, ssl=ctx, server_hostname=None), timeout=3)
        transport = writer.transport
        ssl_object = transport.get_extra_info('ssl_object')
        value = {'handshake': True, 'tls_version': ssl_object.version(),
                 'alpn': ssl_object.selected_alpn_protocol() or 'none'}
        # Cert fingerprint is potentially a device identifier; do not export it.
        writer.close()
        await asyncio.wait_for(writer.wait_closed(), 1)
        return value
    except (OSError, asyncio.TimeoutError, ssl.SSLError, ConnectionError):
        return {'handshake': False}


async def http_head(ip: str, port: int, tls: bool) -> dict[str, Any]:
    ctx = None
    if tls:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(
            ip, port, ssl=ctx), timeout=2.5)
        try:
            # The Host value is generic and does not reveal device IP or MAC.
            writer.write(b'HEAD / HTTP/1.1\r\nHost: device.local\r\nConnection: close\r\n\r\n')
            await asyncio.wait_for(writer.drain(), 1)
            line = await asyncio.wait_for(reader.readline(), 2)
            m = re.match(rb'^HTTP/\d(?:\.\d)?\s+([1-5]\d\d)\b', line[:128])
            return {'http_status': int(m.group(1))} if m else {'http_status': None}
        finally:
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), 1)
            except (OSError, asyncio.TimeoutError):
                pass
    except (OSError, asyncio.TimeoutError, ssl.SSLError):
        return {'http_status': None}


def dns_ptr_query() -> bytes:
    labels = ['_services', '_dns-sd', '_udp', 'local']
    name = b''.join(bytes([len(label)]) + label.encode('ascii') for label in labels) + b'\0'
    # QU asks for unicast replies; on a routed subnet even this can be blocked.
    return b'\0\0\0\0\0\x01\0\0\0\0\0\0' + name + b'\0\x0c\x80\x01'


def coap_core_query() -> bytes:
    # Confirmable GET on /.well-known/core. Uri-Path option 11 followed by 11 chars,
    # then Uri-Path option 11 (delta 0) followed by 4 chars. No mutation.
    message_id = secrets.randbits(16)
    return bytes([0x40, 0x01]) + struct.pack('!H', message_id) + bytes([0xbb]) + b'.well-known' + bytes([4]) + b'core'


def udp_discoveries() -> dict[str, tuple[int, bytes]]:
    return {
        'mdns_unicast': (5353, dns_ptr_query()),
        'ssdp_unicast': (1900, b'M-SEARCH * HTTP/1.1\r\nHOST:239.255.255.250:1900\r\nMAN:"ssdp:discover"\r\nMX:1\r\nST:ssdp:all\r\n\r\n'),
        'coap_well_known_core': (5683, coap_core_query()),
    }


async def udp_probe(ip: str, port: int, payload: bytes) -> dict[str, Any]:
    loop = asyncio.get_running_loop()
    family = socket.AF_INET
    sock = socket.socket(family, socket.SOCK_DGRAM)
    sock.setblocking(False)
    sock.bind(('0.0.0.0', 0))
    try:
        await loop.sock_sendto(sock, payload, (ip, port))
        deadline = loop.time() + 2.0
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            try:
                data, address = await asyncio.wait_for(loop.sock_recvfrom(sock, 4096), remaining)
            except (OSError, asyncio.TimeoutError):
                break
            if address[0] != ip:
                continue  # Never attribute another IoT host to this thermostat.
            return {'response': True, 'response_bytes': len(data),
                    'first_byte_hex': f'{data[0]:02x}' if data else None}
        return {'response': False}
    finally:
        sock.close()


def mqtt_connect() -> bytes:
    # MQTT v3.1.1 anonymous CONNECT with clean session, keepalive=0.
    # No SUBSCRIBE, PUBLISH, auth, broker configuration, or device command.
    client = ('carrier-probe-' + secrets.token_hex(3)).encode('ascii')
    body = b'\x00\x04MQTT\x04\x02\x00\x00' + struct.pack('!H', len(client)) + client
    return b'\x10' + bytes([len(body)]) + body


async def mqtt_handshake(ip: str, port: int) -> dict[str, Any]:
    tls = port in (8883, 8884)
    ctx = None
    if tls:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(ip, port, ssl=ctx), 3)
        try:
            writer.write(mqtt_connect())
            await asyncio.wait_for(writer.drain(), 1)
            resp = await asyncio.wait_for(reader.readexactly(4), 2)
            if len(resp) == 4 and resp[0:3] == b'\x20\x02\x00':
                writer.write(b'\xe0\x00')  # Polite MQTT DISCONNECT; no publish.
                await asyncio.wait_for(writer.drain(), 1)
                return {'mqtt_connack': True, 'return_code': resp[3]}
            return {'mqtt_connack': False}
        finally:
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), 1)
            except (OSError, asyncio.TimeoutError):
                pass
    except (OSError, asyncio.TimeoutError, ssl.SSLError, asyncio.IncompleteReadError):
        return {'mqtt_connack': False}


async def run(ip: str, args: argparse.Namespace) -> dict[str, Any]:
    ports = scan_ports(args.full_tcp)
    print(f'=== TARGETED TCP SWEEP: {len(ports)} PORTS ===', flush=True)
    tcp = await tcp_sweep(ip, ports, concurrency=args.concurrency, timeout=args.tcp_timeout)
    opened = tcp['open_ports']
    print('=== TARGETED SERVICE FINGERPRINTS ===', flush=True)
    tls = {}
    http = {}
    mqtt = {}
    # Open ports outside known list are not given protocol payloads.
    for port in opened:
        if port in TLS_PORTS:
            tls[str(port)] = await tls_check(ip, port)
        if port in WEB_PORTS:
            # Only send HTTP after it is known to be a candidate web listener.
            is_tls = port in TLS_PORTS
            http[str(port)] = await http_head(ip, port, is_tls)
        if port in MQTT_PORTS:
            mqtt[str(port)] = await mqtt_handshake(ip, port)
    print('=== SINGLE-HOST UDP DISCOVERY (3 READ-ONLY QUERIES) ===', flush=True)
    udp = {}
    for name, (port, payload) in udp_discoveries().items():
        udp[name] = await udp_probe(ip, port, payload)
        print(f'  {name}: {"response" if udp[name]["response"] else "no response (inconclusive)"}', flush=True)
    return {'tcp': tcp, 'tls': tls, 'http': http, 'mqtt': mqtt, 'udp': udp}


def conclusions(result: dict[str, Any]) -> list[str]:
    found = result['tcp']['open_ports']
    lines = []
    if found:
        lines.append('OPEN TCP listeners confirmed on verified thermostat: ' + ', '.join(map(str, found)))
    else:
        lines.append('No TCP listeners responded to the tested connects; this does NOT exclude local control.')
    if any(x.get('handshake') for x in result['tls'].values()):
        lines.append('At least one TLS service answered. TLS alone does not prove a thermostat API.')
    if any(x.get('http_status') for x in result['http'].values()):
        lines.append('At least one HTTP HEAD received a status code. No control endpoint has been established.')
    if any(x.get('mqtt_connack') for x in result['mqtt'].values()):
        lines.append('A local MQTT CONNACK was received. No topics, credentials or commands were tested.')
    if any(x.get('response') for x in result['udp'].values()):
        lines.append('A targeted UDP service answered; response format needs further authorized analysis.')
    lines.append('No response may mean filtered/routed traffic, outbound-only cloud control, or a different protocol.')
    lines.append('Next phase: passive AP/gateway traffic metadata or an isolated, consented packet capture; no DNS interception.')
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--omada', type=Path, help='current connected-device ZIP; verifies MAC/IP')
    target.add_argument('--direct-ip', type=str, help='owner-authorized single known IP; NOT reverified against Omada')
    target.add_argument('--manual-ip', type=str, help='current connected-client IP, owner reads from live Omada UI')
    parser.add_argument('--suffix', default='', help='last 4 hex digits of MAC; Omada mode only')
    parser.add_argument('--accept-direct-risk', default='', help='exact acknowledgement of possible DHCP IP reassignment')
    parser.add_argument('--manual-mac', default='', help='current full MAC, used only to cross-check supplied suffix')
    parser.add_argument('--manual-confirm', default='', help='owner affirmation of current Omada connected-client screen')
    parser.add_argument('--max-age-minutes', type=int, default=30)
    parser.add_argument('--controller-utc-offset', type=int, choices=range(-12, 15))
    parser.add_argument('--full-tcp', action='store_true', help='scan all TCP ports 1..65535 (slower)')
    parser.add_argument('--concurrency', type=int, default=32)
    parser.add_argument('--tcp-timeout', type=float, default=0.45)
    parser.add_argument('--plan', action='store_true', help='offline verification; sends zero network packets')
    parser.add_argument('--output', type=Path, help='write redacted evidence JSON privately')
    args = parser.parse_args(argv)
    if not 1 <= args.concurrency <= 64 or not 0.2 <= args.tcp_timeout <= 2.0:
        parser.error('Concurrency must be 1-64; TCP timeout 0.2-2.0s')
    try:
        if args.direct_ip:
            if (args.suffix or args.controller_utc_offset is not None or
                    args.manual_mac or args.manual_confirm):
                raise ValueError('Direct-IP mode cannot be mixed with Omada selection arguments.')
            ip, identity = verify_direct_target(args.direct_ip, args.accept_direct_risk)
            fresh = None
        elif args.manual_ip:
            if args.accept_direct_risk or args.controller_utc_offset is not None:
                raise ValueError('Live Omada UI mode cannot use direct risk or ZIP clock flags.')
            ip, identity = verify_live_ui_selection(args.manual_ip, args.manual_mac,
                                                    args.suffix, args.manual_confirm)
            fresh = None
        else:
            if args.accept_direct_risk or args.manual_mac or args.manual_confirm:
                raise ValueError('ZIP selection cannot be combined with direct/manual selection.')
            fresh = verify_fresh_export(args.omada, args.max_age_minutes,
                                        clock_offset_hours=args.controller_utc_offset)
            ip, identity = verify_identity(read_archive(args.omada), args.suffix)
    except (ValueError, OSError, zipfile.BadZipFile) as exc:
        print('SAFE STOP:', str(exc), file=sys.stderr)
        print('No network traffic sent. Verify target selection.', file=sys.stderr)
        return 2
    print('CARRIER SMARTHOME | LOCAL PROPRIETARY PROTOCOL RECONNAISSANCE')
    if args.direct_ip:
        print('DIRECT IP: owner-authorized single target; current MAC/DHCP identity NOT VERIFIED.')
    elif args.manual_ip:
        print('LIVE UI: owner-attested Omada client; current MAC/IP not machine verified.')
    else:
        print('Fresh Omada online client: VERIFIED; unique active MAC/IP: VERIFIED')
        print('Controller timestamp interpreted as:', fresh['controller_clock'])
        print('Omada ZIP filename:', args.omada.name)
    print('Target IP/MAC/name withheld from report. Only one authorized host is probed.')
    if args.plan:
        print('PLAN ONLY: PASS, absolutely no network packets sent.')
        return 0
    try:
        results = asyncio.run(run(ip, args))
    except (OSError, KeyboardInterrupt) as exc:
        print('Probe interrupted; no thermostat control requests were sent.', file=sys.stderr)
        return 3
    findings = conclusions(results)
    print('\n=== EVIDENCE SUMMARY ===')
    for line in findings:
        print(' -', line)
    report = {'version': '0.5.4', 'at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
              'identity_verified': identity, 'export_freshness': fresh, 'scan_scope': ('single owner-authorized known IP; not independently verified' if args.direct_ip else ('single live UI owner-attested host' if args.manual_ip else 'single verified connected Omada thermostat')),
              'full_tcp': args.full_tcp, 'no_matter': True, 'no_hvac_commands': True,
              'results': results, 'interpretation': findings}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        # Redact all source path, IP, MAC, names, SSID, serial, DNS or certificates.
        args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print('Sanitized report saved in CarrierSmartHome-Research:', args.output.name)
    print('No Matter, cloud write, MQTT publish/subscribe, firmware/DNS changes or HVAC commands.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
