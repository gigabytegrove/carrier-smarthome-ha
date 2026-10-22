#!/usr/bin/env python3
"""Read-only observation of the two Carrier GraphQL views after an HA command.

Requests no mutations and prints no serials, MACs, tokens, usernames, locations,
private addresses, or raw response bodies. A disagreement is an OBSERVATION,
not permission to resend a thermostat command.
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import os
from pathlib import Path
import sys

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "carrier_smarthome"))
from api import CarrierAuthError, CarrierError, CarrierRateLimitError, CarrierSmartHomeClient
from models import connectivity_state, get_zone, zone_indices, zone_values

FIELDS = ("mode", "fan_mode", "heat_setpoint", "cool_setpoint", "temperature")


def safe_fields(zone: dict) -> dict:
    values = zone_values(zone)
    return {key: values.get(key) for key in FIELDS}


def format_sample(n: int, sample: dict) -> str:
    lines = [f"SAMPLE {n}: Carrier reported device {sample['connection']}"]
    for source in ("list", "detail"):
        value = sample.get(source)
        if value is None:
            lines.append(f"  {source}: detail unavailable")
            continue
        lines.append("  " + source + ": " + " ".join(f"{key}={value[key]}" for key in FIELDS))
    if sample["detail"] is not None and sample["list"] != sample["detail"]:
        lines.append("  DISAGREEMENT: the two Carrier cloud views are not yet synchronized")
    return "\n".join(lines)


async def observe(client: CarrierSmartHomeClient) -> dict:
    systems = await client.async_get_systems()
    if len(systems) != 1 or len(zone_indices(systems[0])) != 1:
        raise ValueError("Expected one thermostat with one zone; no device is guessed")
    system = systems[0]
    serial = system.get("serial")
    if not isinstance(serial, str) or not serial:
        raise ValueError("No verified Carrier device identity")
    zone_index = zone_indices(system)[0]
    listed = get_zone(system, zone_index)
    if listed is None:
        raise ValueError("No matching Carrier zone")
    try:
        detail = await client.async_get_system_detail(serial)
    except CarrierRateLimitError:
        raise
    except CarrierError:
        detail = None
    detail_zone = get_zone(detail, zone_index) if isinstance(detail, dict) and detail.get("serial") == serial else None
    return {"connection": connectivity_state(system),
            "list": safe_fields(listed),
            "detail": safe_fields(detail_zone) if detail_zone else None}


async def run(samples: int, interval: int) -> int:
    username = (os.environ.get("CARRIER_USERNAME") or input("Carrier account: ")).strip()
    password = os.environ.get("CARRIER_PASSWORD") or getpass.getpass("Carrier password (hidden): ")
    if not username or not password:
        print("Credentials required; nothing saved.", file=sys.stderr)
        return 2
    print("CARRIER NATIVE CLOUD POST-COMMAND READBACK (READ ONLY)")
    print("No HVAC changes, no Matter, no device identifiers printed.")
    try:
        async with aiohttp.ClientSession(trust_env=False) as session:
            client = CarrierSmartHomeClient(session, username, password)
            for n in range(1, samples + 1):
                if n != 1:
                    await asyncio.sleep(interval)
                print(format_sample(n, await observe(client)), flush=True)
    except CarrierRateLimitError as exc:
        print(f"Carrier rate limit: stop; try after {exc.retry_after:.0f} seconds.", file=sys.stderr)
        return 4
    except CarrierAuthError:
        print("Carrier authentication failed; credentials were not logged.", file=sys.stderr)
        return 3
    except (CarrierError, ValueError, aiohttp.ClientError, asyncio.TimeoutError):
        print("Carrier readback unavailable or device selection ambiguous; no HVAC commands issued.", file=sys.stderr)
        return 5
    print("Read-only observation complete. Compare values with official Carrier app.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--interval", type=int, default=15)
    args = parser.parse_args()
    if not 1 <= args.samples <= 12 or not 10 <= args.interval <= 300:
        parser.error("Use 1..12 samples and 10..300 seconds interval")
    try:
        return asyncio.run(run(args.samples, args.interval))
    except (KeyboardInterrupt, EOFError):
        print("Observation interrupted; no HVAC command sent.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
