#!/usr/bin/env python3
"""Create a non-secret, provenance-labelled transport inventory from SmartHome XAPK research.

Inputs are the separately extracted Hermes string-table JSONL and *sanitized*
native DEX findings. No network or Carrier account required. Not a runtime API detector.
Only publishes allowlisted Carrier domains, fixed path literals, and configuration keys.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

CARRIER_URL = re.compile(r'(?i)(?:https?|wss?)://(?:[a-z0-9-]+\.)*carrier\.com(?::\d+)?(?:/[^\s"\'`<>\\{}]*)?')
KEY_PATTERN = re.compile(r'^(?:API_URL|HASURA_API_URL|REST_API_URL|WEBSOCKET_API_URL|ENTRY_TIER_ENV_URL|OKTA_TOKEN_URL|OKTA_CLIENT_ID|ENTRA_CLIENT_ID|ENTRA_TENANT_URL|SOCIAL_LOGIN_ISSUER)$')
ROUTES = {'/graphql', '/graphql-no-auth'}
EVIDENCE = {'native_dex_urls': [], 'hermes_urls': [], 'hermes_environment_keys': [],
            'graphql_routes': [], 'local_protocol_symbols': [], 'counts': {}}
LOCAL_SYMBOL = re.compile(r'(?:LocalControl|SendLocalControl|MQTT|mqtt|_matter(?:c|d)?\.|^_matter)', re.I)


def normalize_url(raw: str) -> str | None:
    """Truncate at URL query and fragment so signed values cannot be committed."""
    try:
        parts = urlsplit(raw.rstrip('.,);'))
        host = (parts.hostname or '').lower()
        if (parts.scheme not in {'https', 'wss', 'http'} or not
                (host == 'carrier.com' or host.endswith('.carrier.com')) or
                parts.username or parts.password or parts.port not in (None, 443, 80)):
            return None
        path = parts.path or '/'
        # Only allow URL paths composed of ordinary static API/portal path characters.
        if not re.fullmatch(r'/[A-Za-z0-9_.~/%-]{0,200}', path):
            return None
        return f'{parts.scheme}://{host}{path}'
    except ValueError:
        return None


def generate(hermes: Path, native: Path) -> dict:
    data = {key: [] if key != 'counts' else {} for key in EVIDENCE}
    count = 0
    hurls: dict[str, set[int]] = {}
    keys: dict[str, set[int]] = {}
    routes: dict[str, set[int]] = {}
    local: dict[str, set[int]] = {}
    with hermes.open(encoding='utf-8') as stream:
        for line in stream:
            record = json.loads(line)
            value, idx = record.get('value'), record.get('id')
            if not isinstance(value, str) or not isinstance(idx, int):
                continue
            count += 1
            if len(value) > 100_000:
                continue
            if KEY_PATTERN.fullmatch(value):
                keys.setdefault(value, set()).add(idx)
            if value in ROUTES:
                routes.setdefault(value, set()).add(idx)
            if LOCAL_SYMBOL.search(value) and len(value) < 100 and '\n' not in value:
                local.setdefault(value, set()).add(idx)
            for match in CARRIER_URL.finditer(value):
                candidate = normalize_url(match.group())
                if candidate:
                    hurls.setdefault(candidate, set()).add(idx)
    native_json = json.loads(native.read_text(encoding='utf-8'))
    for entry in native_json.get('embedded_carrier_endpoints', []):
        candidate = normalize_url(entry.get('url', ''))
        if candidate:
            data['native_dex_urls'].append({'url': candidate, 'dex': entry.get('dex'),
                                            'status': 'string literal; runtime use unknown'})
    data['hermes_urls'] = [{'url': u, 'string_ids': sorted(ids)[:12],
                             'status': 'string literal; runtime use unknown'} for u, ids in sorted(hurls.items())]
    data['hermes_environment_keys'] = [{'key': k, 'string_ids': sorted(v)} for k, v in sorted(keys.items())]
    data['graphql_routes'] = [{'route': k, 'string_ids': sorted(v)} for k, v in sorted(routes.items())]
    data['local_protocol_symbols'] = [{'symbol': k, 'string_ids': sorted(v)[:12]}
                                      for k, v in sorted(local.items()) if k.lower().startswith(('localcontrol', 'sendlocalcontrol', '_matter', 'mqtt'))]
    data['counts'] = {'hermes_string_records': count, 'native_dex_files': len(native_json.get('dex', [])),
                      'carrier_url_literals_hermes': len(data['hermes_urls']),
                      'carrier_url_literals_native': len(data['native_dex_urls']),
                      'config_keys': len(data['hermes_environment_keys']),
                      'local_protocol_symbols': len(data['local_protocol_symbols'])}
    return data


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hermes', required=True, type=Path, help='Extracted Hermes JSONL, kept locally')
    parser.add_argument('--native', required=True, type=Path, help='Sanitized native DEX findings')
    parser.add_argument('--output', required=True, type=Path, help='Sanitized JSON file to write')
    args = parser.parse_args(argv)
    output = generate(args.hermes, args.native)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.is_symlink():
        parser.error('Refusing to write through symbolic link')
    args.output.write_text(json.dumps(output, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(output['counts'], indent=2))


if __name__ == '__main__':
    main()
