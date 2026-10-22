#!/usr/bin/env python3
"""Explicit, read-only GraphQL check. Requires user-supplied authorized endpoint/token.

Never auto-guesses Carrier hostnames, handles logins, or prints response values.
"""
from __future__ import annotations
import argparse
import getpass
import json
from pathlib import Path
import re
import ssl
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPHandler, HTTPSHandler, HTTPRedirectHandler


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def inspect_shape(value, depth=0):
    """Return types and keys only; no serials, email addresses or authentication values."""
    if depth >= 6:
        return 'maximum depth'
    if isinstance(value, dict):
        return {str(k): inspect_shape(v, depth + 1) for k, v in list(value.items())[:75]}
    if isinstance(value, list):
        return {'type': 'list', 'count': len(value), 'item': inspect_shape(value[0], depth + 1) if value else None}
    return type(value).__name__


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--endpoint', required=True, help='HTTPS GraphQL URL observed in the official app/browser')
    parser.add_argument('--query', required=True, type=Path, help='Read-only GraphQL query .graphql file')
    parser.add_argument('--variables', type=Path, help='JSON file of GraphQL variables (keep private)')
    parser.add_argument('--token-file', type=Path, help='Plain Bearer token file (keep private)')
    parser.add_argument('--prompt-token', action='store_true', help='Enter access token without echo')
    parser.add_argument('--timeout', type=float, default=12.0)
    args = parser.parse_args(argv)
    url = urlsplit(args.endpoint)
    if url.scheme != 'https' or not url.hostname or url.username or url.password or url.fragment:
        parser.error('Endpoint must be an HTTPS URL without embedded credentials or a fragment')
    if not 1 <= args.timeout <= 30:
        parser.error('--timeout must be 1–30 seconds')
    if bool(args.token_file) == bool(args.prompt_token):
        parser.error('Provide exactly one of --token-file or --prompt-token')
    try:
        query = args.query.read_text(encoding='utf-8')
        # Conservative enforcement. Prevent accidental mutation or introspection queries.
        compact = re.sub(r'(?m)^\s*#.*$', '', query).strip()
        if not re.match(r'^query\s+[A-Za-z_][A-Za-z_0-9]*\b', compact):
            parser.error('Only explicitly named query operations are supported')
        if re.search(r'\b(mutation|subscription|__schema|__type)\b', compact):
            parser.error('Mutation, subscription, and introspection documents are not supported')
        variables = json.loads(args.variables.read_text(encoding='utf-8')) if args.variables else {}
        if not isinstance(variables, dict):
            parser.error('Variables must be a JSON object')
        token = args.token_file.read_text(encoding='utf-8').strip() if args.token_file else getpass.getpass('Bearer token: ').strip()
        if not token or '\n' in token or '\r' in token:
            parser.error('A single-line Bearer token is required')
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        parser.error(f'Unable to read input: {type(exc).__name__}')
    payload = json.dumps({'query': query, 'variables': variables}).encode()
    request = Request(args.endpoint, data=payload, method='POST', headers={
        'Content-Type': 'application/json', 'Accept': 'application/json',
        'Authorization': f'Bearer {token}', 'User-Agent': 'carrier-smarthome-ha-research/0.1'})
    del token
    opener = build_opener(HTTPHandler, HTTPSHandler(context=ssl.create_default_context()), NoRedirect)
    try:
        with opener.open(request, timeout=args.timeout) as response:
            status = response.status
            content = response.read(1024 * 1024 + 1)
    except HTTPError as exc:
        print(json.dumps({'http_status': exc.code, 'authenticated': False,
                          'note': 'The server rejected the request; response intentionally omitted.'}, indent=2))
        return 1
    except (URLError, TimeoutError, OSError) as exc:
        print(json.dumps({'network_error': type(exc).__name__}, indent=2))
        return 1
    if len(content) > 1024 * 1024:
        print('{"error":"Response exceeded 1 MiB; not processed"}')
        return 1
    try:
        decoded = json.loads(content)
    except (UnicodeError, json.JSONDecodeError):
        print(json.dumps({'http_status': status, 'error': 'Non-JSON response'}, indent=2))
        return 1
    print(json.dumps({'http_status': status,
                      'graphql_errors': len(decoded.get('errors', [])) if isinstance(decoded, dict) else None,
                      'response_shape': inspect_shape(decoded)}, indent=2))
    return 0 if isinstance(decoded, dict) and not decoded.get('errors') else 1


if __name__ == '__main__':
    sys.exit(main())
