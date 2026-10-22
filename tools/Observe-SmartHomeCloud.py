#!/usr/bin/env python3
"""Owner-side native-cloud telemetry observer (read-only, no Matter).

Runs a bounded number of Carrier GraphQL reads using a single authenticated
client session; prints only sanitized thermostat readings and change summaries.
Offline values are NEVER presented as fresh. Credentials are not logged/saved.
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
from api import CarrierAuthError, CarrierError, CarrierRateLimitError, CarrierSmartHomeClient  # noqa: E402
from models import sanitize_device_summary, sanitize_telemetry  # noqa: E402


def snapshot(systems: list[dict]) -> dict:
    """Whitelisted fields only; no hardware/account/network identifiers."""
    return {"at_utc": datetime.now(timezone.utc).isoformat(timespec='seconds'),
            "summary": sanitize_device_summary(systems),
            "devices": sanitize_telemetry(systems)}


def compare(before: dict | None, after: dict) -> list[str]:
    """Describe changes by anonymous device index rather than serial number."""
    if before is None:
        return ['First sample; no previous cloud observation for comparison']
    changes = []
    previous = before.get('devices', [])
    current = after.get('devices', [])
    if len(previous) != len(current):
        changes.append(f'Device count changed: {len(previous)} to {len(current)}')
    for index, (old, new) in enumerate(zip(previous, current), 1):
        if old.get('cloud_connection') != new.get('cloud_connection'):
            changes.append(f'Device {index} cloud state: {old.get("cloud_connection")} -> {new.get("cloud_connection")}')
        for zidx, (oz, nz) in enumerate(zip(old.get('zones', []), new.get('zones', []))):
            for field in ('mode', 'room_temperature', 'heat_setpoint', 'cool_setpoint', 'humidity_percent', 'outside_temperature', 'fan_mode', 'stage_status', 'schedule_enabled', 'heat_max', 'cool_min'):
                if oz.get(field) != nz.get(field):
                    changes.append(f'Device {index} zone {nz.get("index", zidx)} {field} changed')
    return changes or ['No changed telemetry fields since the prior sample; this alone does not prove data are stale']


async def run(args) -> int:
    username = os.environ.get('CARRIER_USERNAME') or input('Carrier SmartHome account: ').strip()
    password = os.environ.get('CARRIER_PASSWORD') or getpass.getpass('Carrier password (hidden): ')
    if not username or not password:
        print('ERROR: Carrier account credentials are required.', file=sys.stderr)
        return 2
    results = []
    try:
        async with aiohttp.ClientSession(trust_env=False) as session:
            client = CarrierSmartHomeClient(session, username, password)
            previous = None
            for i in range(args.samples):
                if i:
                    await asyncio.sleep(args.interval)
                try:
                    systems = await client.async_get_systems()
                except CarrierRateLimitError as exc:
                    print(f'Carrier rate limit: pause further reads for at least {exc.retry_after:.0f}s.')
                    return 5
                result = snapshot(systems)
                results.append(result)
                print(f'\nSAMPLE {i + 1}/{args.samples} — {result["at_utc"]}')
                print('Devices:', result['summary']['entry_level_count'],
                      '| Online:', result['summary']['online_count'],
                      '| Offline:', result['summary']['offline_count'])
                for device_number, item in enumerate(result['devices'], 1):
                    print(f'Device {device_number}: model={item["model"]} cloud={item["cloud_connection"]} unit={item["temperature_unit"]}')
                    for zone in item['zones']:
                        print(f'  Zone {zone["index"]}: mode={zone["mode"]} room={zone["room_temperature"]} '
                              f'heat={zone["heat_setpoint"]} cool={zone["cool_setpoint"]} RH={zone["humidity_percent"]} '
                              f'outside={zone["outside_temperature"]} fan={zone["fan_mode"]} '
                              f'stage={zone["stage_status"]} schedule={zone["schedule_enabled"]}')
                print('CHANGES:', '; '.join(compare(previous, result)))
                if result['summary']['offline_count']:
                    print('WARNING: Carrier marked a device OFFLINE; temperatures may be cached.')
                previous = result
    except CarrierAuthError:
        print('Carrier authentication was refused or needs renewal.', file=sys.stderr)
        return 3
    except (CarrierError, aiohttp.ClientError, asyncio.TimeoutError):
        print('Carrier cloud telemetry could not be read; no account information was printed.', file=sys.stderr)
        return 4
    if args.output:
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps({'samples': results}, indent=2) + '\n', encoding='utf-8')
            print('Sanitized local report:', args.output)
        except OSError:
            print('WARNING: Could not save the optional sanitized output.', file=sys.stderr)
            return 6
    print('\nAll observations were READ ONLY. Offline data are not confirmed current.')
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--samples', type=int, default=3, help='Number of samples (1-12)')
    parser.add_argument('--interval', type=int, default=60, help='Seconds between samples (20-3600)')
    parser.add_argument('--output', type=Path, help='Optional local privacy-minimized JSON report')
    args = parser.parse_args()
    if not 1 <= args.samples <= 12 or not 20 <= args.interval <= 3600:
        parser.error('Require 1-12 samples and an interval of 20-3600 seconds')
    try:
        return asyncio.run(run(args))
    except (KeyboardInterrupt, EOFError):
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
