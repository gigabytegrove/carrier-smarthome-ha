#!/usr/bin/env python3
"""Read-only Carrier SmartHome cloud feature-capability probe.

Queries APK-recovered schedules, reminders and notification-preference operations
for devices already authenticated to the owner's Carrier account. Reports only
availability and record counts. Never prints or saves schedule contents,
reminder messages, device serials, locations, email addresses or tokens.
"""
import asyncio
import getpass
import os
from pathlib import Path
import sys

import aiohttp
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'custom_components' / 'carrier_smarthome'))
from api import CarrierAuthError, CarrierError, CarrierSmartHomeClient  # noqa: E402


async def main():
    username = os.environ.get('CARRIER_USERNAME') or input('Carrier account: ').strip()
    password = os.environ.get('CARRIER_PASSWORD') or getpass.getpass('Carrier password (hidden): ')
    if not username or not password:
        return 2
    async with aiohttp.ClientSession(trust_env=False) as session:
        client = CarrierSmartHomeClient(session, username, password)
        try:
            systems = await client.async_get_systems()
        except CarrierAuthError:
            print('Authentication: FAILED (no account details printed)')
            return 3
        except CarrierError:
            print('Device enumeration failed (no server response printed)')
            return 4
        print(f'Authentication: PASS | Entry-level devices: {len(systems)}')
        for index, system in enumerate(systems[:8], 1):
            serial = system.get('serial')
            if not isinstance(serial, str) or not serial:
                continue
            print(f'Device {index} — read-only capability checks:')
            for key in ('schedules', 'reminders', 'notification_prefs'):
                try:
                    result = await client.async_get_entry_level_feature(serial, key)
                except CarrierAuthError:
                    print(f'  {key}: auth expired')
                    return 3
                except CarrierError:
                    print(f'  {key}: not available / query rejected')
                else:
                    if isinstance(result, list):
                        print(f'  {key}: supported response (record count {len(result)})')
                    else:
                        print(f'  {key}: supported response (object)')
    print('No schedules, reminder contents, credentials, or device identifiers were printed.')
    print('No thermostat controls were exercised; no Matter was used.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(asyncio.run(main()))
    except (EOFError, KeyboardInterrupt):
        raise SystemExit(130) from None
