#!/usr/bin/env python3
"""Audit native Android DEX strings in the user-supplied SmartHome APK.

Never writes APK contents, packaged credentials, or raw string tables to stdout.
It records only fixed known-safe URLs and protocol/feature symbol evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import zipfile

URL = re.compile(r'(?i)(?:https?|wss?)://[a-z0-9._-]+(?::\d+)?(?:/[-a-z0-9._/~%?=&;]*)?')
KEEP = ('carrier.com',)
FEATURE_PATTERNS = {
    'oauth': re.compile(r'oauth2|authorization|okta|openid|sso\.', re.I),
    'websocket': re.compile(r'websocket|realtime\.infinity', re.I),
    'matter': re.compile(r'(?:^|\W)matter(?:\W|$)|_matter[cdi]?\.', re.I),
    'mqtt': re.compile(r'mqtt|LocalControl|LocalControlReq', re.I),
    'graphql': re.compile(r'graphql|hasura', re.I),
    'ble': re.compile(r'bluetooth|ble|gatt', re.I),
}


def uleb(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    for i in range(5):
        if offset >= len(data):
            raise ValueError('truncated ULEB128')
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7f) << (i * 7)
        if not (byte & 0x80):
            return value, offset
    raise ValueError('ULEB128 too long')


def dex_strings(data: bytes):
    """Parse actual DEX string-id offsets rather than binary grep false positives."""
    if len(data) < 112 or not data.startswith(b'dex\n'):
        raise ValueError('not a DEX file')
    count, offset = struct.unpack_from('<II', data, 56)
    if count > 5_000_000 or offset < 112 or offset + count * 4 > len(data):
        raise ValueError('invalid DEX string identifiers')
    for i in range(count):
        pos = struct.unpack_from('<I', data, offset + i * 4)[0]
        if pos >= len(data):
            continue
        try:
            _, pos = uleb(data, pos)
        except ValueError:
            continue
        end = data.find(b'\0', pos, min(len(data), pos + 30000))
        if end > pos:
            yield data[pos:end].decode('utf-8', 'replace')


def inspect(apk: Path) -> dict:
    result = {'apk_sha256': hashlib.file_digest(apk.open('rb'), 'sha256').hexdigest(),
              'source': 'actual native DEX string tables', 'dex': [],
              'embedded_carrier_endpoints': [], 'feature_evidence': {name: [] for name in FEATURE_PATTERNS}}
    endpoints = set()
    features = {name: set() for name in FEATURE_PATTERNS}
    with zipfile.ZipFile(apk) as archive:
        names = sorted((name for name in archive.namelist() if re.fullmatch(r'classes\d*\.dex', name)),
                       key=lambda x: int(re.search(r'\d+', x).group()) if re.search(r'\d+', x) else 1)
        for name in names:
            count = 0
            for value in dex_strings(archive.read(name)):
                count += 1
                for match in URL.finditer(value):
                    url = match.group().rstrip('.,;')
                    from urllib.parse import urlsplit
                    parsed = urlsplit(url)
                    if parsed.hostname and (parsed.hostname == 'carrier.com' or parsed.hostname.endswith('.carrier.com')):
                        endpoints.add((name, url))
                for key, pat in FEATURE_PATTERNS.items():
                    if pat.search(value) and len(value) < 95 and not any(c in value for c in ('\n', '\r')):
                        features[key].add((name, value))
            result['dex'].append({'file': name, 'strings': count})
    result['embedded_carrier_endpoints'] = [{'dex': a, 'url': b} for a, b in sorted(endpoints)]
    for key in features:
        result['feature_evidence'][key] = [{'dex': a, 'symbol': b} for a, b in sorted(features[key])][:100]
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk', type=Path, help='Path to base APK extracted from XAPK')
    parser.add_argument('--output', type=Path, help='Where to save sanitized discovery data')
    args = parser.parse_args(argv)
    if not args.apk.is_file():
        parser.error('APK file not found')
    result = inspect(args.apk)
    output = json.dumps(result, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding='utf-8')
    print('Native DEX files inspected:', len(result['dex']))
    print('Carrier URL references:', len(result['embedded_carrier_endpoints']))
    print('Feature categories:', ', '.join(name for name, rows in result['feature_evidence'].items() if rows))
    if args.output:
        print('Sanitized report:', args.output)


if __name__ == '__main__':
    main()
