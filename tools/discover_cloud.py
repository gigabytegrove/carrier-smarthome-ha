#!/usr/bin/env python3
"""Discover Carrier SmartHome cloud configuration without usernames, URLs or tokens.

Makes GET requests ONLY to public Carrier web portal pages and their same-origin
JavaScript assets. Does not log in, query an account, submit GraphQL, or POST.
Candidate addresses are classified as evidence, not validated APIs.
"""
from __future__ import annotations
import argparse
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import ssl
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, HTTPRedirectHandler, HTTPSHandler, build_opener

PORTALS = ('https://prod.consumerportal.carrier.com/login', 'https://my.carrier.com/login')
APPLICABLE_KEYS = ('API_URL', 'REST_API_URL', 'HASURA_API_URL', 'WEBSOCKET_API_URL',
                   'ENTRY_TIER_ENV_URL', 'OKTA_TOKEN_URL', 'ENTRA_TENANT_URL')
HTTP_URL = re.compile(r'(?i)(?:https?|wss?)://(?:[a-z0-9_-]+\.)+[a-z]{2,}(?::\d+)?(?:/[-a-z0-9_./~%?=&;:]*)?')
KEY_VALUE = re.compile(r'''(?i)["']?(API_URL|REST_API_URL|HASURA_API_URL|WEBSOCKET_API_URL|ENTRY_TIER_ENV_URL|OKTA_TOKEN_URL|ENTRA_TENANT_URL)["']?\s*[:=]\s*["'`]([^"'`\s<>{}]{4,300})''')


def carrier_https(value: str, origin: str | None = None) -> str | None:
    """Return normalized URL without query/userinfo/fragment only for Carrier domains."""
    try:
        url = urljoin(origin, value) if origin else value
        split = urlsplit(url)
        host = (split.hostname or '').lower()
        if (split.scheme not in ('https', 'wss') or
                not (host == 'carrier.com' or host.endswith('.carrier.com')) or
                split.username or split.password):
            return None
        if split.port is not None and split.port not in (443,):
            return None
        return f'{split.scheme}://{host}{split.path or "/"}'
    except ValueError:
        return None


class AssetParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == 'script':
            src = dict(attrs).get('src')
            if src:
                self.scripts.append(src)


class BlockRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def public_get(opener, url: str, limit: int, timeout: float) -> str:
    req = Request(url, headers={'User-Agent': 'CarrierSmartHomeHA-Research/0.2',
                                'Accept': 'text/html,application/javascript,text/javascript,*/*'})
    with opener.open(req, timeout=timeout) as response:
        # Prevent accidentally saving a ZIP, video, or other large application file.
        content_type = response.headers.get('Content-Type', '').lower()
        if not any(t in content_type for t in ('html', 'javascript', 'json', 'text/plain')):
            raise ValueError('Non-text response')
        data = response.read(limit + 1)
        if len(data) > limit:
            raise ValueError('Response exceeds size limit')
        return data.decode('utf-8', 'replace')


def public_evidence(text: str) -> dict:
    endpoints = set()
    configs = set()
    for match in HTTP_URL.finditer(text):
        clean = carrier_https(match.group())
        if clean:
            endpoints.add(clean)
    for match in KEY_VALUE.finditer(text):
        clean = carrier_https(match.group(2))
        if clean:
            configs.add((match.group(1).upper(), clean))
    return {'carrier_url_literals': sorted(endpoints),
            'embedded_api_config': [{'key': key, 'value': url} for key, url in sorted(configs)]}


def inspect_public_portals(portals=PORTALS, limit_assets=12, timeout=7.0):
    opener = build_opener(HTTPSHandler(context=ssl.create_default_context()), BlockRedirect())
    results = []
    for portal in portals:
        state = {'site': portal, 'status': 'unknown', 'scripts_examined': 0,
                 'carrier_url_literals': [], 'embedded_api_config': []}
        try:
            page = public_get(opener, portal, 2_000_000, timeout)
            parser = AssetParser()
            parser.feed(page)
            extracts = [public_evidence(page)]
            origin_host = urlsplit(portal).hostname
            assets = []
            for script in parser.scripts:
                full = urljoin(portal, script)
                if urlsplit(full).hostname == origin_host and urlsplit(full).scheme == 'https':
                    assets.append(full)
            for asset in dict.fromkeys(assets[:limit_assets]):
                try:
                    code = public_get(opener, asset, 6_000_000, timeout)
                    extracts.append(public_evidence(code))
                    state['scripts_examined'] += 1
                except (HTTPError, URLError, TimeoutError, ValueError, OSError):
                    continue
            state['status'] = 'public_html_retrieved'
            state['carrier_url_literals'] = sorted({x for entry in extracts for x in entry['carrier_url_literals']})
            state['embedded_api_config'] = [dict(key=k, value=v) for k,v in sorted({(c['key'], c['value']) for entry in extracts for c in entry['embedded_api_config']})]
        except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
            state['status'] = 'public_page_unavailable'
            state['error_type'] = type(exc).__name__
        results.append(state)
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offline', action='store_true', help='Report APK-derived candidates only, without any network')
    parser.add_argument('--output', type=Path, help='Private JSON evidence output')
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    native_path = root / 'research' / 'native-dex-findings.json'
    native = json.loads(native_path.read_text(encoding='utf-8')) if native_path.exists() else {}
    result = {
        'note': 'Addresses embedded in APK are candidate services; no login/control API is verified.',
        'cloud_endpoints_from_native_apk': native.get('embedded_carrier_endpoints', []),
        'graphql_route_literals': ['/graphql', '/graphql-no-auth'],
        'runtime_configuration_keys': list(APPLICABLE_KEYS),
        'public_portals': [] if args.offline else inspect_public_portals(),
        'cloud_authenticated': False,
        'model_backend_confirmed': False,
    }
    payload = json.dumps(result, indent=2) + '\n'
    print(payload, end='')
    if args.output:
        if args.output.is_symlink():
            parser.error('Refusing to overwrite a symlink')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        # Never record authenticated user sessions; the output contains only sanitized URLs.
        args.output.write_text(payload, encoding='utf-8')


if __name__ == '__main__':
    sys.exit(main())
