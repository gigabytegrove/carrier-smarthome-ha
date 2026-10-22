#!/usr/bin/env python3
"""Read-only native GraphQL confirmation of Carrier's current reported state.

Reads both account and serial-specific thermostat status. Compares caller-selected
expected setpoints/mode with both sources; reports only whitelisted fields. No
network identifiers, credentials, tokens, commands, Matter or automatic restore.
"""
from __future__ import annotations
import argparse
import asyncio
import getpass
import math
import os
from pathlib import Path
import sys

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'custom_components/carrier_smarthome'))
from api import CarrierAuthError, CarrierError, CarrierSmartHomeClient  # noqa: E402
from models import zone_indices  # noqa: E402

# Reuse the maintained privacy whitelist and identical two-query parsing.
import importlib.util
SOURCE = Path(__file__).with_name('Compare-AppChange.py')
spec = importlib.util.spec_from_file_location('carrier_app_compare', SOURCE)
compare = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = compare
spec.loader.exec_module(compare)


def compare_expectations(snapshot: dict, expected: dict) -> dict[str, list[str]]:
    """Return safe field names that disagree, for each readable GraphQL view."""
    result = {}
    for source in ('list', 'detail'):
        values = snapshot.get(source) or {}
        if not values:
            result[source] = ['source_unavailable']
            continue
        result[source] = [field for field, wanted in expected.items()
                          if values.get(field) is None or values[field] != wanted]
    return result


def expectation_values(args) -> dict:
    values = {}
    for key in ('heat_setpoint', 'cool_setpoint', 'mode', 'fan_mode'):
        value = getattr(args, key, None)
        if value is not None:
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError('Expected setpoints must be finite numbers')
            values[key] = value
    if getattr(args, 'schedule_enabled', None) is not None:
        values['schedule_enabled'] = args.schedule_enabled == 'enabled'
    return values


async def run(args) -> int:
    expected = expectation_values(args)
    username = (os.environ.get('CARRIER_USERNAME') or input('Carrier SmartHome account: ')).strip()
    password = os.environ.get('CARRIER_PASSWORD') or getpass.getpass('Carrier password (hidden): ')
    if not username or not password:
        print('Carrier credentials required. Nothing saved.')
        return 2
    async with aiohttp.ClientSession(trust_env=False) as session:
        client = CarrierSmartHomeClient(session, username, password)
        systems = await client.async_get_systems()
        if len(systems) != 1 or len(zone_indices(systems[0])) != 1:
            print('STOP: Expected one thermostat and one zone; no identity guesswork.')
            return 5
        serial = systems[0].get('serial')
        if not isinstance(serial, str) or not serial:
            print('STOP: Missing cloud thermostat identity.')
            return 5
        snapshot = await compare.read_pair(client, serial, zone_indices(systems[0])[0])
        print('CARRIER SMARTHOME | READ-ONLY CURRENT STATE CROSS-CHECK')
        print('Cloud-reported connection:', snapshot['connection'])
        for source in ('list', 'detail'):
            print(source + ':')
            for field in compare.DISPLAY_FIELDS:
                print('  ' + field + ': ' + str(snapshot[source].get(field, 'not returned')))
        print('Readings are cloud-reported; no device sample timestamp was supplied.')
        if not expected:
            print('No expected state requested. Read-only inspection completed.')
            return 0
        mismatches = compare_expectations(snapshot, expected)
        for source in ('list', 'detail'):
            if mismatches[source]:
                print(f'{source}: MISMATCH (' + ', '.join(mismatches[source]) + ')')
            else:
                print(f'{source}: ALL REQUESTED FIELDS MATCH')
        if any(mismatches.values()):
            print('EXPECTED STATE NOT CONFIRMED. Check the official app; no commands were sent.')
            return 7
        print('EXPECTED STATE MATCHED IN BOTH GRAPHQL VIEWS; no commands were sent.')
        return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--heat-setpoint', type=float)
    p.add_argument('--cool-setpoint', type=float)
    p.add_argument('--mode', choices=['off', 'heat', 'cool', 'auto', 'fanonly'])
    p.add_argument('--fan-mode', choices=['auto', 'off', 'low', 'med', 'high'])
    p.add_argument('--schedule-enabled', choices=['enabled', 'disabled'])
    args = p.parse_args()
    try:
        return asyncio.run(run(args))
    except ValueError as exc:
        print('Invalid expected values; no requests were made:', str(exc))
        return 2
    except CarrierAuthError:
        print('Carrier authentication failed. No sensitive details printed.')
        return 3
    except (CarrierError, aiohttp.ClientError, asyncio.TimeoutError):
        print('Carrier read-only cloud request failed; no settings were changed.')
        return 4
    except (KeyboardInterrupt, EOFError):
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
