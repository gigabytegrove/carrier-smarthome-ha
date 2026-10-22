#!/usr/bin/env python3
"""Read-only A/B test: compare Carrier GraphQL with changes made in official phone app.

The Python tool NEVER changes the thermostat. An owner may make and then restore
one reversible setpoint adjustment in Carrier's official app. Cloud reads are
matched by serial only in memory. No serial, MAC, username, password, network
address, token, device name, or device identifier is logged or saved.

An "offline" isConnected flag is displayed as Carrier-reported metadata; it
is NOT used to claim the physical device is unreachable. A successful change
proves the GraphQL view can reflect an app edit, not that values are always fresh.
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import os
from pathlib import Path
import sys
from typing import Any

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "carrier_smarthome"))
from api import (  # noqa: E402
    CarrierAuthError,
    CarrierError,
    CarrierRateLimitError,
    CarrierSmartHomeClient,
)
from models import connectivity_state, get_zone, zone_indices, zone_values  # noqa: E402

# Only whitelisted, control-relevant fields can appear on screen.
TARGET_FIELDS = ("heat_setpoint", "cool_setpoint")
DISPLAY_FIELDS = TARGET_FIELDS + ("mode", "fan_mode", "schedule_enabled")


def clean_values(raw_zone: dict[str, Any]) -> dict[str, Any]:
    """Whitelist normalized fields: do not emit upstream GraphQL dictionaries."""
    data = zone_values(raw_zone)
    return {name: data.get(name) for name in DISPLAY_FIELDS}


def changed_targets(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    """Find a changed setpoint; neither clock time nor Carrier's status flag qualifies."""
    return [key for key in TARGET_FIELDS if before.get(key) is not None
            and after.get(key) is not None and before[key] != after[key]]


def matches_baseline(original: dict[str, Any], current: dict[str, Any], fields: list[str]) -> bool:
    """Restore confirmation requires a known baseline for every modified field."""
    return bool(fields) and all(original.get(k) is not None
                                and current.get(k) == original.get(k) for k in fields)


def interpretation(before: dict[str, Any], middle: dict[str, Any] | None,
                   restored: dict[str, Any] | None) -> str:
    """Strictly classify what the GraphQL pair actually demonstrated."""
    if middle is None:
        return "NO_SETPOINT_CHANGE_OBSERVED"
    changes = changed_targets(before, middle)
    if not changes:
        return "NO_SETPOINT_CHANGE_OBSERVED"
    if restored is None or not matches_baseline(before, restored, changes):
        return "SETPOINT_CHANGE_OBSERVED_RESTORE_NOT_CONFIRMED"
    return "APP_TO_GRAPHQL_CHANGE_AND_RESTORE_CONFIRMED"


def display(label: str, snapshot: dict[str, Any]) -> None:
    """Print safe field values for listing and detail; no raw response objects."""
    print(label)
    print("  Carrier connection field:", snapshot["connection"])
    for source in ("list", "detail"):
        values = snapshot[source]
        text = " ".join(f"{key}={values.get(key)}" for key in DISPLAY_FIELDS)
        print(f"  {source}: {text}" if values else f"  {source}: unavailable")


def evaluate_source_changes(baseline: dict[str, Any], current: dict[str, Any]) -> dict[str, list[str]]:
    return {source: changed_targets(baseline[source], current[source])
            for source in ("list", "detail")}


async def read_pair(client: CarrierSmartHomeClient, serial: str, index: int) -> dict[str, Any]:
    """Two independent READ ONLY GraphQL paths, same known serial and zone."""
    systems = await client.async_get_systems()
    matching = [s for s in systems if s.get("serial") == serial]
    if len(matching) != 1:
        raise ValueError("The original thermostat is no longer uniquely available in Carrier's account listing")
    system = matching[0]
    list_zone = get_zone(system, index)
    if list_zone is None:
        raise ValueError("The original zone no longer exists in Carrier's account listing")
    detail = None
    try:
        detail = await client.async_get_system_detail(serial)
    except CarrierAuthError:
        raise
    except CarrierRateLimitError:
        raise
    except CarrierError:
        pass  # The proven listing still works even when detail is unavailable.
    detail_zone = get_zone(detail, index) if isinstance(detail, dict) else None
    return {
        "connection": connectivity_state(system),
        "list": clean_values(list_zone),
        "detail": clean_values(detail_zone) if detail_zone else {},
    }


async def read_sequence(client: CarrierSmartHomeClient, serial: str, index: int,
                        baseline: dict[str, Any], *, attempts: int, interval: int,
                        label: str, changed: dict[str, list[str]] | None = None) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Bounded, per-phase polling. No changes ever sent to thermostat."""
    last: dict[str, Any] = baseline
    observed: dict[str, Any] | None = None
    for step in range(attempts):
        if step:
            await asyncio.sleep(interval)
        try:
            last = await read_pair(client, serial, index)
        except CarrierRateLimitError:
            raise  # Respect Carrier's limit instead of hammering its endpoint.
        display(f"{label}: cloud read {step + 1}/{attempts}", last)
        if changed is None:
            changes = evaluate_source_changes(baseline, last)
            if changes["list"] or changes["detail"]:
                print("  Setpoint changed in:", ", ".join(source for source, fields in changes.items() if fields))
                observed = last
                break
        else:
            if all(matches_baseline(baseline[source], last[source], fields)
                   for source, fields in changed.items() if fields):
                print("  Original setpoint restored in every changed GraphQL source.")
                observed = last
                break
    return observed, last


def prompt_step(message: str) -> bool:
    print("\n" + message)
    return input("Press Enter after completing that step (or type Q to stop): ").strip().lower() != "q"


async def exercise(args: argparse.Namespace) -> int:
    username = (os.environ.get("CARRIER_USERNAME") or input("Carrier account: ")).strip()
    password = os.environ.get("CARRIER_PASSWORD") or getpass.getpass("Carrier password (hidden): ")
    if not username or not password:
        print("Carrier account credentials required; nothing was saved.")
        return 2
    print("\nCARRIER SMARTHOME | OFFICIAL APP ↔ NATIVE GRAPHQL TEST")
    print("This script sends READS ONLY. It cannot change or restore HVAC settings.")
    print("If you make a change in the app, manually restore it even if this test fails.")
    async with aiohttp.ClientSession(trust_env=False) as session:
        client = CarrierSmartHomeClient(session, username, password)
        systems = await client.async_get_systems()
        if len(systems) != 1:
            print("STOP: Expected exactly one account thermostat; no guessing which to test.")
            return 5
        system = systems[0]
        serial = system.get("serial")
        if not isinstance(serial, str) or not serial:
            print("STOP: Carrier did not supply a usable private device identity.")
            return 5
        indices = zone_indices(system)
        if len(indices) != 1:
            print("STOP: Expected exactly one thermostat zone; avoid changing the wrong one.")
            return 5
        index = indices[0]
        baseline = await read_pair(client, serial, index)
        display("BASELINE — BEFORE PHONE APP CHANGE", baseline)
        if not all(baseline["list"].get(field) is not None for field in TARGET_FIELDS):
            print("STOP: Carrier did not provide both setpoints; cannot verify restoration.")
            return 5
        print("\nRecord BOTH original setpoints displayed above.")
        print("In the official Carrier SmartHome app, change ONE setpoint by 1 degree")
        print("(prefer cooling) and verify the app accepts it. Do not change HVAC mode.")
        print("Only do this if you can safely restore the original setting.")
        if not prompt_step("STEP 1 — Make the small setpoint change using the OFFICIAL APP only."):
            print("No app change confirmed; no thermostat writes were issued.")
            return 0
        changed_read, last_changed = await read_sequence(
            client, serial, index, baseline, attempts=args.samples, interval=args.interval,
            label="AFTER APP CHANGE",
        )
        observed = changed_read or last_changed
        found = evaluate_source_changes(baseline, observed)
        changed = sorted(set(found["list"] + found["detail"]))
        print("\nCHANGE RESULT:", ", ".join(
            f"{source}={','.join(changes) if changes else 'no_change'}" for source, changes in found.items()))
        print("IMPORTANT: Restore the original setpoint in the official app NOW, regardless of the result.")
        if not prompt_step("STEP 2 — Restore the exact original app setpoint and confirm in the app."):
            print("RESTORE NOT VERIFIED — manually check the official Carrier app.")
            return 6
        # Do not claim restoration when there is no observed intermediate change.
        restored_read: dict[str, Any] | None = None
        if changed:
            restored_read, _ = await read_sequence(
                client, serial, index, baseline, attempts=args.samples, interval=args.interval,
                label="AFTER APP RESTORE", changed=found,
            )
        else:
            restored_read, _ = await read_sequence(
                client, serial, index, baseline, attempts=1, interval=args.interval,
                label="AFTER APP RESTORE", changed={},
            )
        # Evaluate restoration only for sources where a change was actually seen.
        classifications = {}
        for source in ("list", "detail"):
            classifications[source] = interpretation(
                baseline[source],
                observed[source] if found[source] else None,
                restored_read[source] if restored_read else None,
            )
        print("\nFINAL READ-ONLY RESULTS")
        for source, result in classifications.items():
            print(f"  {source}: {result}")
        print("  GraphQL status flag (not physical connectivity):", last_changed["connection"])
        print("  No mutation or Matter request was sent; credentials and serial were sent only to Carrier for login/reads.")
        print("  No account identifiers, passwords, tokens, hardware IDs or device names were printed or saved.")
        if changed and not restored_read:
            print("WARNING: Cloud restoration was NOT confirmed. Check the original targets in the app.")
        if not changed:
            print("The phone app may use a different backend, or these GraphQL views may cache the values.")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=6, help="Reads per phase, 1–12")
    parser.add_argument("--interval", type=int, default=20, help="Seconds between reads, 15–300")
    args = parser.parse_args()
    if not 1 <= args.samples <= 12 or not 15 <= args.interval <= 300:
        parser.error("Use --samples 1..12 and --interval 15..300 seconds")
    try:
        return asyncio.run(exercise(args))
    except CarrierRateLimitError as exc:
        print(f"Carrier rate limit: stop testing; retry after at least {exc.retry_after:.0f} seconds.")
        print("If you changed a setting, restore it directly in the official Carrier app.")
        return 4
    except CarrierAuthError:
        print("Carrier login was rejected; no sensitive values were printed.")
        return 3
    except (CarrierError, aiohttp.ClientError, asyncio.TimeoutError, ValueError):
        print("Carrier read-only GraphQL check failed; never assume any app-side change was restored.")
        return 5
    except (KeyboardInterrupt, EOFError):
        print("Interrupted. Check and restore your original setpoint in the phone app.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
