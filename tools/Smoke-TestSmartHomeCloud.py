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
from models import sanitize_device_summary, sanitize_telemetry  # noqa: E402


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
            details: list[tuple[str, dict | None]] = []
            # Cross-check the APK-derived detailed query for each discovered
            # device. A schema rejection does not invalidate the successful
            # device-list query. Never print raw API errors or serial numbers.
            for system in systems[:8]:
                serial = system.get('serial')
                if not isinstance(serial, str) or not serial:
                    details.append(('skipped', None))
                    continue
                try:
                    details.append(('pass', await client.async_get_system_detail(serial)))
                except (CarrierError, ValueError):
                    details.append(('not_available', None))
        summary = sanitize_device_summary(systems)
        print('\nCARRIER SMARTHOME NATIVE CLOUD VERIFICATION')
        print('Authentication: PASS')
        print('Entry-level devices: ' + str(summary['entry_level_count']))
        print('Connected devices: ' + str(summary['online_count']))
        print('Offline devices: ' + str(summary['offline_count']))
        print('Unknown connection state: ' + str(summary['unknown_connection_count']))
        print('Thermostat zones: ' + str(summary['zone_count']))
        print('Reported models: ' + (', '.join(summary['models']) or '(none)'))
        print('\nREAD-ONLY THERMOSTAT DATA (may be stale if offline)')
        for number, device in enumerate(sanitize_telemetry(systems), 1):
            print('Device ' + str(number) + ': model=' + device['model'] +
                  ' connection=' + device['cloud_connection'] +
                  ' unit=' + device['temperature_unit'])
            for zone in device['zones']:
                def fmt(value):
                    return 'unknown' if value is None else str(value)
                print('  Zone ' + str(zone['index']) + ': mode=' + zone['mode'] +
                      ' room=' + fmt(zone['room_temperature']) +
                      ' heat=' + fmt(zone['heat_setpoint']) +
                      ' cool=' + fmt(zone['cool_setpoint']) +
                      ' humidity=' + fmt(zone['humidity_percent']) +
                      ' outside=' + fmt(zone['outside_temperature']))
        print('\nAPK DETAIL QUERY CROSS-CHECK')
        for number, (state, detail) in enumerate(details, 1):
            label = {'pass': 'PASS', 'not_available': 'NOT AVAILABLE (schema/permissions/connectivity)',
                     'skipped': 'SKIPPED'}.get(state, 'UNKNOWN')
            print('Device ' + str(number) + ': ' + label)
            if detail is not None:
                sanitized = sanitize_telemetry([detail])[0]
                print('  Detail model=' + sanitized['model'] +
                      ' connection=' + sanitized['cloud_connection'] +
                      ' zones=' + str(len(sanitized['zones'])))
        print('No thermostat commands were sent. No identifiers, names, tokens or passwords were printed.')
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
