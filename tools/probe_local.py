#!/usr/bin/env python3
"""Read-only discovery of possible Carrier thermostat devices on a network you own.

Without --target/--scan, only neighbor cache and an mDNS query are used.
No credentials, control commands, firmware changes, or HTTP requests are sent.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import struct
import subprocess
import sys
import time

TCP_PORTS = (80, 443, 8080, 8443, 1883, 8883)
RFC1918 = tuple(ipaddress.ip_network(cidr) for cidr in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))


def is_rfc1918(ip: ipaddress.IPv4Address) -> bool:
    return any(ip in network for network in RFC1918)
SERVICE_TYPES = ("_services._dns-sd._udp.local", "_matter._tcp.local",
                 "_matterc._udp.local", "_matterd._udp.local")


def private_ip(value: str) -> ipaddress.IPv4Address:
    ip = ipaddress.ip_address(value)
    if not isinstance(ip, ipaddress.IPv4Address) or not is_rfc1918(ip):
        raise argparse.ArgumentTypeError("Provide a private IPv4 LAN address (not loopback/link-local)")
    return ip


def private_net(value: str) -> ipaddress.IPv4Network:
    net = ipaddress.ip_network(value, strict=False)
    if not isinstance(net, ipaddress.IPv4Network) or net.prefixlen < 24 or not all(is_rfc1918(address) for address in (net.network_address, net.broadcast_address)):
        raise argparse.ArgumentTypeError("Explicit scan range must be a private IPv4 /24 or smaller")
    return net


def neighbors() -> list[dict[str, str]]:
    """Read OS neighbor cache, never ARP-sweep or invent vendor/model from MAC."""
    commands = (["arp", "-a"],) if os.name == "nt" else (["ip", "neigh"], ["arp", "-an"])
    output = ""
    for cmd in commands:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5, check=False)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0:
            output = result.stdout
            break
    found: dict[str, dict[str, str]] = {}
    for line in output.splitlines():
        for text in re.findall(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])", line):
            try:
                ip = private_ip(text)
            except argparse.ArgumentTypeError:
                continue
            mac_match = re.search(r"(?i)(?<![a-f0-9])(?:[a-f0-9]{2}[:-]){5}[a-f0-9]{2}(?![a-f0-9])", line)
            if mac_match:
                found[str(ip)] = {"ip": str(ip), "mac": mac_match.group(0).lower().replace('-', ':')}
    return sorted(found.values(), key=lambda item: ipaddress.ip_address(item["ip"]))


def dns_name(name: str) -> bytes:
    result = bytearray()
    for label in name.rstrip('.').split('.'):
        encoded = label.encode('ascii')
        if not 0 < len(encoded) <= 63:
            raise ValueError('Invalid mDNS label')
        result += bytes([len(encoded)]) + encoded
    return bytes(result) + b'\x00'


def parse_name(packet: bytes, offset: int) -> tuple[str, int]:
    labels, next_offset, seen = [], None, set()
    for _ in range(128):
        if offset >= len(packet) or offset in seen:
            raise ValueError('Invalid DNS name or compression loop')
        seen.add(offset)
        length = packet[offset]
        if length & 0xc0 == 0xc0:
            if offset + 1 >= len(packet):
                raise ValueError('Truncated pointer')
            pointer = ((length & 0x3f) << 8) | packet[offset + 1]
            if next_offset is None:
                next_offset = offset + 2
            offset = pointer
            continue
        if length & 0xc0:
            raise ValueError('Invalid DNS label type')
        offset += 1
        if length == 0:
            return '.'.join(labels), (next_offset if next_offset is not None else offset)
        if offset + length > len(packet):
            raise ValueError('Truncated DNS label')
        labels.append(packet[offset:offset + length].decode('utf-8', 'replace'))
        offset += length
    raise ValueError('Too many DNS labels')


def parse_mdns(packet: bytes) -> list[dict[str, str | int]]:
    if len(packet) < 12:
        return []
    qd, an, ns, ar = struct.unpack_from('!HHHH', packet, 4)
    if qd + an + ns + ar > 512:
        return []
    records = []
    offset = 12
    try:
        for _ in range(qd):
            _, offset = parse_name(packet, offset)
            offset += 4
            if offset > len(packet):
                return []
        for _ in range(an + ns + ar):
            owner, offset = parse_name(packet, offset)
            if offset + 10 > len(packet):
                return records
            rtype, _, _, length = struct.unpack_from('!HHIH', packet, offset)
            offset += 10
            end = offset + length
            if end > len(packet):
                return records
            if rtype == 1 and length == 4:
                records.append({'service': owner, 'type': 'A', 'value': socket.inet_ntop(socket.AF_INET, packet[offset:end])})
            elif rtype == 28 and length == 16:
                records.append({'service': owner, 'type': 'AAAA', 'value': socket.inet_ntop(socket.AF_INET6, packet[offset:end])})
            elif rtype == 12:
                target, _ = parse_name(packet, offset)
                records.append({'service': owner, 'type': 'PTR', 'value': target})
            elif rtype == 33 and length >= 6:
                port = struct.unpack_from('!H', packet, offset + 4)[0]
                target, _ = parse_name(packet, offset + 6)
                records.append({'service': owner, 'type': 'SRV', 'value': target, 'port': port})
            offset = end
    except (ValueError, IndexError, struct.error, OSError):
        pass
    return records


def discover_mdns(duration: float) -> tuple[list[dict], list[str]]:
    result: dict[tuple, dict] = {}
    errors = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.settimeout(0.4)
            sock.bind(('', 5353))
            try:
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                                socket.inet_aton('224.0.0.251') + socket.inet_aton('0.0.0.0'))
            except OSError as exc:
                errors.append(f'Multicast join unavailable: {exc}')
            end = time.monotonic() + duration
            for service in SERVICE_TYPES:
                packet = struct.pack('!HHHHHH', 0, 0, 1, 0, 0, 0) + dns_name(service) + struct.pack('!HH', 12, 1)
                try:
                    sock.sendto(packet, ('224.0.0.251', 5353))
                except OSError as exc:
                    errors.append(f'mDNS query failed: {exc}')
            while time.monotonic() < end:
                try:
                    packet, _ = sock.recvfrom(9000)
                except socket.timeout:
                    continue
                except OSError as exc:
                    errors.append(f'mDNS read failed: {exc}')
                    break
                for record in parse_mdns(packet):
                    key = (record['service'], record['type'], record['value'])
                    result[key] = record
    except OSError as exc:
        errors.append(f'mDNS unavailable: {exc}')
    return sorted(result.values(), key=lambda x: (x['service'], x['type'], x['value'])), errors


def tcp_probe(address: str, port: int, timeout: float) -> dict[str, str | int | bool]:
    try:
        with socket.create_connection((address, port), timeout=timeout):
            return {'ip': address, 'port': port, 'reachable': True}
    except (OSError, TimeoutError):
        return {'ip': address, 'port': port, 'reachable': False}


def scan_hosts(addresses: list[str], timeout: float) -> list[dict]:
    reachable = []
    with ThreadPoolExecutor(max_workers=24) as executor:
        futures = [executor.submit(tcp_probe, ip, port, timeout) for ip in addresses for port in TCP_PORTS]
        for future in as_completed(futures):
            result = future.result()
            if result['reachable']:
                reachable.append(result)
    return sorted(reachable, key=lambda x: (ipaddress.ip_address(x['ip']), x['port']))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', type=private_ip, help='A known thermostat IP; only TCP connect to listed ports')
    parser.add_argument('--cidr', type=private_net, help='Authorized private /24-or-smaller subnet')
    parser.add_argument('--scan', action='store_true', help='Opt-in TCP discovery scan of --cidr')
    parser.add_argument('--timeout', type=float, default=0.35)
    parser.add_argument('--mdns-seconds', type=float, default=2.5)
    parser.add_argument('--output', type=Path, help='Optional private JSON output; never commit unredacted results')
    args = parser.parse_args(argv)
    if args.scan and not args.cidr:
        parser.error('--scan requires --cidr')
    if not 0.05 <= args.timeout <= 10 or not 0 <= args.mdns_seconds <= 15:
        parser.error('Timeout must be 0.05–10 seconds, and mDNS duration 0–15 seconds')
    report = {'timestamp_utc': datetime.now(timezone.utc).isoformat(),
              'method': 'neighbor-cache + read-only multicast DNS + optional TCP connect',
              'neighbors': neighbors(), 'mdns_records': [], 'open_tcp': [], 'warnings': []}
    if args.mdns_seconds:
        report['mdns_records'], report['warnings'] = discover_mdns(args.mdns_seconds)
    addresses = [str(args.target)] if args.target else []
    if args.scan:
        addresses = [str(ip) for ip in args.cidr.hosts()]
    if addresses:
        report['open_tcp'] = scan_hosts(addresses, args.timeout)
    print(json.dumps(report, indent=2))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        # Refuse to overwrite a symlink or create world-readable diagnostics on POSIX.
        if args.output.is_symlink():
            parser.error('Refusing symlink output')
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        fd = os.open(args.output, flags, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(report, stream, indent=2)
            stream.write('\n')
        if os.name == 'posix':
            os.chmod(args.output, 0o600)
    return 0


if __name__ == '__main__':
    sys.exit(main())
