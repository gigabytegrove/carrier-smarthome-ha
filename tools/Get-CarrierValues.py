#!/usr/bin/env python3
"""Read-only cloud field inventory to guide Home Assistant entity development.

No passwords, tokens, serials, MACs, SSIDs, device IDs, names, or addresses
are printed or saved. Baseline query is already owner-verified; extended detail
query is experimental and failure does not invalidate the baseline result.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import getpass
import json
import os
from pathlib import Path
import sys

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'custom_components' / 'carrier_smarthome'))
from api import CarrierAuthError, CarrierError, CarrierSmartHomeClient  # noqa: E402
from models import sanitize_device_summary, sanitize_telemetry  # noqa: E402


def build_report(systems: list[dict], extras: list[dict | None], statuses: list[str]) -> dict:
    devices = sanitize_telemetry(systems)
    for device, extra in zip(devices, extras):
        if not extra:
            continue
        # The serial is validated BEFORE calling this function and never exported.
        sanitized_extra = sanitize_telemetry([extra])[0]
        if device['model'] != sanitized_extra['model']:
            continue
        extra_zones = {z['index']: z for z in sanitized_extra['zones']}
        for zone in device['zones']:
            enriched = extra_zones.get(zone['index'], {})
            # Additional data only. Never overwrite values obtained from baseline.
            for field in ('current_scene',):
                if enriched.get(field) is not None:
                    zone[field] = enriched[field]
    return {
        'observed_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'transport': 'Carrier native cloud GraphQL (not Matter)',
        'reading_freshness': 'not_verifiable_without_thermostat_timestamp',
        'summary': sanitize_device_summary(systems),
        'extended_detail_status': statuses,
        'devices': devices,
    }


def format_values(report: dict) -> str:
    lines = [
        'CARRIER SMARTHOME | READ-ONLY CLOUD FIELD INVENTORY',
        'Carrier native GraphQL; no Matter; no HVAC writes',
        'Observed: ' + report['observed_utc'],
        'Cloud devices: ' + str(report['summary']['entry_level_count']),
        'ONLINE=' + str(report['summary']['online_count']) +
        ' OFFLINE=' + str(report['summary']['offline_count']) +
        ' UNKNOWN=' + str(report['summary']['unknown_connection_count']),
    ]
    for i, device in enumerate(report['devices'], 1):
        detail = report['extended_detail_status'][i - 1]
        lines.append(f'Device {i}: model={device["model"]} carrier_connection={device["cloud_connection"]} ' +
                     f'unit={device["temperature_unit"]} detailed_query={detail}')
        for z in device['zones']:
            lines.append(f'  Zone {z["index"]}:')
            for key, value in z.items():
                if key != 'index':
                    lines.append(f'    {key}: {value if value is not None else "not reported"}')
    lines.append('WARNING: OFFLINE cloud readings can be cached; no device sample timestamp available.')
    lines.append('No credentials, serials, MACs, network details, or control commands included.')
    return '\n'.join(lines)


async def collect(username: str, password: str) -> dict:
    async with aiohttp.ClientSession(trust_env=False) as session:
        client = CarrierSmartHomeClient(session, username, password)
        systems = await client.async_get_systems()
        extras, statuses = [], []
        for system in systems[:20]:
            serial = system.get('serial')
            if not isinstance(serial, str) or not serial:
                extras.append(None)
                statuses.append('skipped_no_identity')
                continue
            try:
                extended = await client.async_get_extended_detail(serial)
            except CarrierAuthError:
                raise
            except CarrierError:
                extras.append(None)
                statuses.append('not_available_baseline_preserved')
            else:
                extras.append(extended)
                statuses.append('pass')
        # Extend to account-level devices beyond probe cap (sanitizer itself max 20).
        return build_report(systems, extras, statuses)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='Optional local sanitized JSON snapshot')
    args = parser.parse_args()
    username = (os.environ.get('CARRIER_USERNAME') or input('Carrier SmartHome email/username: ')).strip()
    password = os.environ.get('CARRIER_PASSWORD') or getpass.getpass('Carrier password (hidden): ')
    if not username or not password:
        print('Account credentials required (nothing saved).', file=sys.stderr)
        return 2
    try:
        report = asyncio.run(collect(username, password))
    except CarrierAuthError:
        print('Authentication rejected/expired. No sensitive information printed.', file=sys.stderr)
        return 3
    except (CarrierError, aiohttp.ClientError, asyncio.TimeoutError):
        print('Carrier API not available. No response bodies printed.', file=sys.stderr)
        return 4
    print(format_values(report))
    if args.output:
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        except OSError:
            print('Could not save local sanitized report.', file=sys.stderr)
            return 5
        print('Sanitized local snapshot:', args.output)
    return 0 if report['summary']['entry_level_count'] else 6


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (KeyboardInterrupt, EOFError):
        raise SystemExit(130) from None
