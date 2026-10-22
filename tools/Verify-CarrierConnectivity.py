#!/usr/bin/env python3
"""Triangulate native Carrier cloud connection flags and hardware identity.

All raw MAC, serial, username, device IDs and tokens are memory-only.
No mutation, Matter command, network scan or JSON report file is generated.
An API status of 'offline' does not prove the app/device cannot communicate.
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import os
from pathlib import Path
import sys

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'custom_components' / 'carrier_smarthome'))
from api import CarrierAuthError, CarrierError, CarrierSmartHomeClient  # noqa: E402
from models import connectivity_state, hardware_identity_match, normalize_hardware_id, zone_indices  # noqa: E402


def readable_connection(device: dict | None) -> str:
    """Unknown/unavailable is different from a Carrier false flag."""
    return connectivity_state(device) if isinstance(device, dict) else 'not_available'


def analyze(systems: list[dict], details: list[dict | None],
            app_inventory: list[dict] | None, expected_mac: str | None) -> list[dict]:
    """Safe output: never returns account, serial, MAC, device ID, SSID or name."""
    app_map: dict[str, dict] = {}
    if app_inventory is not None:
        for entry in app_inventory:
            if isinstance(entry, dict) and isinstance(entry.get('serial'), str):
                app_map[entry['serial']] = entry
    result = []
    for idx, system in enumerate(systems):
        serial = system.get('serial')
        detail = details[idx] if idx < len(details) else None
        app = app_map.get(serial, {}) if isinstance(serial, str) else {}
        app_con = app.get('connection') if isinstance(app, dict) else None
        record = {
            'device': idx + 1,
            'model_from_cloud': system.get('model') if isinstance(system.get('model'), str) else 'unknown',
            'zones': len(zone_indices(system)),
            'entry_level_list': readable_connection(system),
            'apk_device_detail': readable_connection(detail),
            'apk_user_location': readable_connection({'connection': app_con}) if app else ('query_unavailable' if app_inventory is None else 'not_listed'),
            'identity_from_app_mac': hardware_identity_match(expected_mac, app_con.get('macaddress')) if isinstance(app_con, dict) else ('unverified' if expected_mac else 'not_checked'),
            'identity_from_cloud_serial': 'matched' if expected_mac and normalize_hardware_id(serial) == normalize_hardware_id(expected_mac) else 'unverified',
            'model_matches_physical_label': system.get('model') == 'TSTATCCEWF-01',
        }
        # App MAC identity is stronger than arbitrary serial pattern matching.
        record['identity_to_physical_thermostat'] = (
            'matched' if 'matched' in (record['identity_from_app_mac'], record['identity_from_cloud_serial'])
            else ('different_mac' if record['identity_from_app_mac'] == 'different_mac' else 'unverified')
        )
        result.append(record)
    return result


def render(records: list[dict], app_state: str) -> str:
    lines = [
        'CARRIER SMARTHOME | CONNECTION SOURCE CROSS-CHECK (READ ONLY)',
        'Carrier cloud GraphQL only. No Matter. No thermostat writes.',
        f'Account-location query: {app_state}',
        f'Devices in authenticated listing: {len(records)}',
    ]
    for r in records:
        lines.extend([
            f"Device {r['device']}: cloud_model={r['model_from_cloud']} zones={r['zones']}",
            f"  entryLevelSystems.connection.isConnected: {r['entry_level_list']}",
            f"  entryLevelSystem.connection.isConnected: {r['apk_device_detail']}",
            f"  user.locations.entryLevels.connection.isConnected: {r['apk_user_location']}",
            f"  Physical MAC identity: {r['identity_to_physical_thermostat']}",
            f"  Cloud model matches printed TSTATCCEWF-01: {'yes' if r['model_matches_physical_label'] else 'no (mapping unverified)'}",
        ])
    lines += [
        'INTERPRETATION: A false Carrier status flag is not proof of no real device control.',
        'If the phone app works, use a reversible app-side setpoint change and compare',
        'two subsequent cloud reads before calling any value fresh.',
        'No account identifiers, MACs, device serials, location names or tokens were printed.',
    ]
    return '\n'.join(lines)


async def run(expected_mac: str | None) -> tuple[str, list[dict]]:
    username = (os.environ.get('CARRIER_USERNAME') or input('Carrier account: ')).strip()
    password = os.environ.get('CARRIER_PASSWORD') or getpass.getpass('Carrier password (hidden): ')
    if not username or not password:
        raise ValueError('Carrier account credentials required')
    async with aiohttp.ClientSession(trust_env=False) as session:
        client = CarrierSmartHomeClient(session, username, password)
        systems = await client.async_get_systems()
        details = []
        for system in systems[:20]:
            try:
                details.append(await client.async_get_system_detail(system['serial']))
            except CarrierAuthError:
                raise
            except (CarrierError, KeyError, ValueError):
                details.append(None)
        # Query is independent and may be disabled on an account. It is NOT a
        # dependency for the previously working authenticated thermostat reads.
        app_state = 'pass'
        try:
            inventory = await client.async_get_user_connection_inventory()
        except CarrierAuthError:
            raise
        except CarrierError:
            app_state = 'not_available'
            inventory = None
        return app_state, analyze(systems[:20], details, inventory, expected_mac)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-mac', help='Optional physical device MAC; used in memory only, never printed')
    args = parser.parse_args()
    if args.expected_mac is not None and normalize_hardware_id(args.expected_mac) is None:
        parser.error('Expected MAC must be 12 hex digits, with optional colon or dash separators')
    try:
        state, records = asyncio.run(run(args.expected_mac))
    except CarrierAuthError:
        print('Carrier authentication rejected; no sensitive details printed.', file=sys.stderr)
        return 3
    except (CarrierError, aiohttp.ClientError, asyncio.TimeoutError, ValueError):
        print('Carrier read-only connectivity check unavailable.', file=sys.stderr)
        return 4
    print(render(records, state))
    return 0 if records else 5


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (KeyboardInterrupt, EOFError):
        raise SystemExit(130) from None
