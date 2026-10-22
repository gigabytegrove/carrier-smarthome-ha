#!/usr/bin/env python3
"""Summarize an owner-generated browser HAR without exposing credentials or account data.

Never uploads the HAR, never makes network requests, never prints headers or body
values. Only Carrier-domain request hosts, benign path *patterns*, method,
authentication mechanism, GraphQL operation names, and variable KEY names are kept.
The source HAR may contain sensitive login and thermostat data. Do not commit it.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit

OP = re.compile(r'\b(?:query|mutation|subscription)\s+([A-Za-z_][A-Za-z_0-9]*)\b')
KNOWN_SEGMENTS = {'graphql', 'graphql-no-auth', 'oauth2', 'default', 'v1', 'token',
                  'authorize', 'login', 'auth', 'authentication', 'connect', 'api',
                  'userinfo', 'refresh', 'device', 'devices', 'consumer', 'sso'}


def carrier_host(url: str):
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or '').lower()
        if (parsed.scheme not in ('https', 'wss') or parsed.username or parsed.password or
                not (host == 'carrier.com' or host.endswith('.carrier.com'))):
            return None
        return host, parsed.path or '/'
    except ValueError:
        return None


def sanitized_path(path: str):
    # Retain only known fixed endpoint words, no opaque IDs, emails, serials, UUIDs.
    return '/' + '/'.join(s if s.lower() in KNOWN_SEGMENTS else '{segment}'
                          for s in path.strip('/').split('/') if s) if path != '/' else '/'


def auth_shape(headers: list[dict]) -> dict:
    present = {str(h.get('name', '')).lower(): str(h.get('value', '')) for h in headers if isinstance(h, dict)}
    authorization = present.get('authorization', '').strip()
    scheme = authorization.split(' ', 1)[0].lower()
    # Header *names* only, never values; omit arbitrary app-specific names.
    return {'authorization': (scheme if scheme in ('bearer', 'basic', 'digest') else
                              ('other' if authorization else 'absent')),
            'cookie_present': 'cookie' in present, 'api_key_header_present':
            any(k in present for k in ('x-api-key', 'api-key', 'x-hasura-admin-secret'))}


def graphql_shape(entry: dict) -> dict:
    raw = entry.get('postData') or {}
    body = raw.get('text', '') if isinstance(raw, dict) else ''
    if not isinstance(body, str) or len(body) > 2_000_000:
        return {'operation': None, 'variable_keys': []}
    try:
        parsed = json.loads(body)
    except (ValueError, TypeError):
        parsed = None
    if isinstance(parsed, dict):
        name = parsed.get('operationName')
        query = parsed.get('query', '')
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]{0,127}', name):
            match = OP.search(query) if isinstance(query, str) else None
            name = match.group(1) if match else None
        variables = parsed.get('variables')
        return {'operation': name, 'variable_keys': sorted(k for k in variables
                if isinstance(k, str) and re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]{0,80}', k))
                if isinstance(variables, dict) else []}
    match = OP.search(body)
    return {'operation': match.group(1) if match else None, 'variable_keys': []}


def summarize_har(document: dict) -> dict:
    entries = document.get('log', {}).get('entries', [])
    if not isinstance(entries, list):
        raise ValueError('HAR log.entries must be an array')
    seen = Counter()
    records: dict[tuple, dict] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get('request'), dict):
            continue
        request = entry['request']
        target = carrier_host(request.get('url', ''))
        if not target:
            continue
        host, path = target
        method = str(request.get('method', '')).upper()
        if method not in {'GET', 'POST', 'OPTIONS', 'PUT', 'PATCH', 'DELETE'}:
            continue
        kind = ('graphql' if 'graphql' in path.lower() else
                'authentication_candidate' if any(s in path.lower() for s in ('oauth', 'token', 'login', 'authorize'))
                else 'other')
        # Avoid publishing arbitrary paths and counts containing unique account IDs.
        op = graphql_shape(request) if kind == 'graphql' else {'operation': None, 'variable_keys': []}
        key = (host, sanitized_path(path), method, kind, op['operation'],
               tuple(op['variable_keys']))
        seen[key] += 1
        if key not in records:
            records[key] = {'host': host, 'path_pattern': key[1], 'method': method,
                            'category': kind, 'graphql_operation': op['operation'],
                            'variable_keys': op['variable_keys'],
                            'authentication_headers': auth_shape(request.get('headers') or [])}
    safe = sorted(records.values(), key=lambda d: (d['host'], d['path_pattern'], d['method'], d['graphql_operation'] or ''))
    for item in safe:
        item['observations'] = seen[(item['host'], item['path_pattern'], item['method'], item['category'],
                                     item['graphql_operation'], tuple(item['variable_keys']))]
    return {'carrier_requests': sum(seen.values()), 'unique_request_shapes': len(safe),
            'records': safe, 'source': 'offline HAR metadata; request/response values omitted',
            'secret_values_exported': False}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('har', type=Path, help='A HAR from YOUR Carrier SmartHome portal session')
    parser.add_argument('--output', type=Path, help='Private redacted JSON report')
    args = parser.parse_args(argv)
    try:
        document = json.loads(args.har.read_text(encoding='utf-8'))
        result = summarize_har(document)
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        parser.error(f'Cannot parse HAR: {type(exc).__name__}')
    output = json.dumps(result, indent=2) + '\n'
    print(output, end='')
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if args.output.is_symlink():
            parser.error('Refusing to write to symbolic-link output')
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as file:
            file.write(output)
        if os.name == 'posix':
            os.chmod(args.output, 0o600)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
