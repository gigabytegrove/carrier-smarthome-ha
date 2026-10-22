#!/usr/bin/env python3
"""Minimal secure GraphQL transport for owner-authorized Carrier SmartHome research.

Production login and TSTATCCEWF-01 backend mapping remain unresolved. This
transport can be tested offline and can issue READ-ONLY queries once session
credentials are established; it never automates or guesses authentication.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
import ssl
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, HTTPSHandler, HTTPRedirectHandler, build_opener

MAX_RESPONSE_BYTES = 1_048_576
QUERY = re.compile(r'^\s*query\s+([A-Za-z_][A-Za-z0-9_]*)\b', re.S)
MUTATION = re.compile(r'^\s*mutation\s+([A-Za-z_][A-Za-z0-9_]*)\b', re.S)


class CarrierCloudError(Exception):
    """Base cloud error (never contains credentials or response body)."""


class CarrierAuthenticationError(CarrierCloudError):
    """Server reports expired or unauthorized authentication."""


class CarrierNetworkError(CarrierCloudError):
    """Network/HTTP failure."""


class CarrierGraphQLError(CarrierCloudError):
    """Server returned GraphQL errors; raw errors intentionally not exposed."""


@dataclass(frozen=True)
class GraphQLOperation:
    name: str
    document: str
    readonly: bool


def parse_operation(document: str) -> GraphQLOperation:
    if not isinstance(document, str) or len(document) > 250_000:
        raise ValueError('Invalid GraphQL document')
    cleaned = re.sub(r'(?m)^\s*#[^\n]*$', '', document).strip()
    query = QUERY.match(cleaned)
    mutation = MUTATION.match(cleaned)
    if not (query or mutation):
        raise ValueError('Only a single named query or mutation is accepted')
    # Avoid appended operations: no multi-operation ambiguous requests.
    # Avoid string literals containing these words by first parsing safely only as
    # a repository-controlled document. Auth/session material never enters here.
    if re.search(r'(?m)^\s*(?:query|mutation|subscription)\s+[A-Za-z_]',
                 cleaned[(query or mutation).end():]):
        raise ValueError('Multiple operations are not permitted')
    return GraphQLOperation((query or mutation).group(1), cleaned, bool(query))


def validate_carrier_endpoint(endpoint: str) -> str:
    try:
        parts = urlsplit(endpoint)
        hostname = (parts.hostname or '').lower()
        if (parts.scheme != 'https' or not hostname or parts.username or parts.password or parts.fragment or
                parts.port not in (None, 443) or
                not (hostname == 'carrier.com' or hostname.endswith('.carrier.com'))):
            raise ValueError('Expected a Carrier-owned HTTPS endpoint')
        if not re.fullmatch(r'/[A-Za-z0-9/_-]+', parts.path) or not parts.path.endswith(('graphql', 'graphql-no-auth')):
            raise ValueError('Expected an observed Carrier GraphQL endpoint')
        if parts.query:
            raise ValueError('Query strings not supported in endpoint')
        return endpoint
    except ValueError as exc:
        raise ValueError('Untrusted GraphQL endpoint') from exc


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class CarrierCloudTransport:
    def __init__(self, endpoint: str, token_provider: Callable[[], str], timeout: float = 12.0):
        self.endpoint = validate_carrier_endpoint(endpoint)
        if not callable(token_provider):
            raise TypeError('token_provider must be callable')
        if not 1 <= timeout <= 30:
            raise ValueError('Timeout must be in 1–30 seconds')
        self._token_provider = token_provider
        self._timeout = timeout
        self._opener = build_opener(HTTPSHandler(context=ssl.create_default_context()), _NoRedirect())

    def execute(self, operation: GraphQLOperation, variables: dict | None = None) -> dict:
        if not operation.readonly:
            raise PermissionError('Write operations disabled until live input schema is verified')
        if not isinstance(variables if variables is not None else {}, dict):
            raise ValueError('Variables must be a JSON dictionary')
        token = self._token_provider()
        if not isinstance(token, str) or not token.strip() or any(x in token for x in '\r\n'):
            raise CarrierAuthenticationError('Authorization token unavailable')
        body = json.dumps({'operationName': operation.name, 'query': operation.document,
                           'variables': variables or {}}, separators=(',', ':')).encode('utf-8')
        request = Request(self.endpoint, data=body, method='POST', headers={
            'Content-Type': 'application/json', 'Accept': 'application/json',
            'Authorization': f'Bearer {token}', 'User-Agent': 'carrier-smarthome-ha/research'})
        del token
        try:
            with self._opener.open(request, timeout=self._timeout) as response:
                payload = response.read(MAX_RESPONSE_BYTES + 1)
        except HTTPError as exc:
            if exc.code in (401, 403):
                raise CarrierAuthenticationError(f'HTTP {exc.code}; credentials required/expired') from None
            raise CarrierNetworkError(f'HTTP {exc.code}') from None
        except (URLError, TimeoutError, OSError):
            raise CarrierNetworkError('Network failure calling Carrier endpoint') from None
        if len(payload) > MAX_RESPONSE_BYTES:
            raise CarrierNetworkError('Response too large')
        try:
            result = json.loads(payload)
        except (UnicodeError, ValueError):
            raise CarrierNetworkError('Non-JSON response') from None
        if not isinstance(result, dict):
            raise CarrierNetworkError('Invalid response envelope')
        if result.get('errors'):
            raise CarrierGraphQLError('GraphQL returned an error (details redacted)')
        if 'data' not in result:
            raise CarrierNetworkError('GraphQL response missing data')
        return result['data']
