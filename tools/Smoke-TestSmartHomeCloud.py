#!/usr/bin/env python3
"""Read-only Carrier SmartHome login/device check. No URLs or IPs required.

Run from this repository with Python 3.11+ and `pip install aiohttp`.
Account credentials are entered locally, never printed, written, or committed.
"""
from __future__ import annotations

import asyncio
import getpass
import os
import sys
from pathlib import Path

try:
    import aiohttp
except ImportError:
    print('ERROR: aiohttp is missing. Install with: py -m pip install aiohttp', file=sys.stderr)
    raise SystemExit(2)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'custom_components' / 'carrier_smarthome'))
from api import CarrierAuthError, CarrierError, CarrierSmartHomeClient  # noqa: E402
from models import sanitize_device_summary  # noqa: E402


async def main() -> int:
    username = os.environ.get('CARRIER_USERNAME') or input('Carrier SmartHome email/username: ').strip()
    password = os.environ.get('CARRIER_PASSWORD') or getpass.getpass('Carrier SmartHome password (hidden): ')
    if not username or not password:
        print('ERROR: Account credentials are required.')
        return 2
    try:
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout, trust_env=False) as session:
            client = CarrierSmartHomeClient(session, username, password)
            systems = await client.async_get_systems()
        summary = sanitize_device_summary(systems)
        print('\nCARRIER SMARTHOME NATIVE CLOUD VERIFICATION')
        print('Authentication: PASS')
        print('Entry-level devices: ' + str(summary['entry_level_count']))
        print('Connected devices: ' + str(summary['online_count']))
        print('Thermostat zones: ' + str(summary['zone_count']))
        print('Reported models: ' + (', '.join(summary['models']) or '(none)'))
        print('No thermostat commands were sent. No identifiers or tokens were printed.')
        return 0 if summary['entry_level_count'] else 3
    except CarrierAuthError:
        print('Authentication: FAIL (Carrier rejected credentials or this login flow)')
        return 4
    except CarrierError:
        print('Cloud API: FAIL (endpoint, GraphQL response, or connectivity)')
        return 5


if __name__ == '__main__':
    try:
        raise SystemExit(asyncio.run(main()))
    except (KeyboardInterrupt, EOFError):
        raise SystemExit(130) from None
